"""Incident candidates and evidence to the coordination API (PRD FR-VIS-006, FR-VIS-009).

A fired trigger becomes an ``IncidentCandidate`` and is posted at once, so the incident reaches
the operator without waiting for the clip (SC-001). The evidence clip and keyframes follow when
the ring holds the 5 s after the peak; they are tied to the incident by the candidate's
idempotency key. Posting retries with back-off and never blocks or stops the analysis thread.
"""

import asyncio
import hashlib
import logging
import tempfile
from collections.abc import Sequence
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from nadjet_shared import (
    AiStatus,
    CandidateSource,
    GeoLocation,
    IncidentCandidate,
    VerifierResult,
)
from nadjet_shared.catalogue import Camera
from nadjet_vision.config import VisionSettings
from nadjet_vision.evidence import EvidenceFiles, build_evidence
from nadjet_vision.ingest import Packet, StreamInfo
from nadjet_vision.status import StatusThresholds, classify
from nadjet_vision.triggers import TriggerEvent
from nadjet_vision.verifier import AiVerifier

log = logging.getLogger("nadjet_vision.publish")

RETRY_DELAYS_S = (0.5, 1.0, 2.0, 4.0, 8.0)  # then give up (logged, counted)
EVIDENCE_RETRY_DELAYS_S = (1.0, 2.0, 4.0, 8.0, 8.0)
CANDIDATE_NOT_PERSISTED = 409  # /internal/evidence before the stream consumer saved the incident


def wall_time(epoch_s: float) -> datetime:
    return datetime.fromtimestamp(epoch_s, UTC)


def candidate_key(camera_id: str, event: TriggerEvent) -> str:
    """Deterministic idempotency key: re-sending the same event never makes a second incident."""
    ids = ",".join(str(i) for i in event.track_ids)
    raw = f"{camera_id}|{event.trigger.value}|{round(event.peak_wall * 1000)}|{ids}"
    return f"{camera_id}-{hashlib.sha256(raw.encode()).hexdigest()[:40]}"


def build_candidate(
    camera: Camera,
    event: TriggerEvent,
    verifier: VerifierResult | None = None,
    ai_status: AiStatus | None = None,
) -> IncidentCandidate:
    """Candidate from a trigger. Without a verifier result it is unavailable (FR-VIS-009), so
    the status is whatever ``classify`` makes of a rule alone; sweep candidates pass both."""
    verifier = verifier or VerifierResult(available=False)
    if ai_status is None:
        ai_status = classify(rule_fired=True, verifier=verifier)
    return IncidentCandidate(
        source=CandidateSource.CAMERA,
        camera_id=camera.id,
        location=GeoLocation(
            lat=camera.geo.lat,
            lon=camera.geo.lon,
            road=camera.road,
            pk_km=camera.pk_km,
            wilaya=camera.wilaya,
        ),
        trigger=event.trigger,
        event_time=wall_time(event.peak_wall),
        detected_at=wall_time(event.fire_wall),
        track_ids=list(event.track_ids),
        signals=event.signals,
        verifier=verifier,
        ai_status=ai_status,
    )


def _log_failure(future: "Future[None]") -> None:
    """Background posts never raise into analysis, but a bug in them must not vanish."""
    if not future.cancelled() and future.exception() is not None:
        log.error("background publish failed", exc_info=future.exception())


@dataclass(frozen=True)
class VerifyContext:
    """What the AI verifier needs to look at a rule candidate: the ring at the moment it fired."""

    event: TriggerEvent
    packets: Sequence[Packet]
    info: StreamInfo | None


class IncidentSink(Protocol):
    """What the pipeline needs from a publisher (a fake in unit tests)."""

    def publish_candidate(
        self, candidate: IncidentCandidate, key: str, verify: VerifyContext | None = None
    ) -> None: ...

    def submit_evidence(
        self,
        key: str,
        event: TriggerEvent,
        packets: Sequence[Packet],
        info: StreamInfo | None,
    ) -> None: ...


@dataclass
class PublishStats:
    candidates_sent: int = 0
    candidates_failed: int = 0
    evidence_sent: int = 0
    evidence_failed: int = 0
    hash_mismatches: int = 0


class IncidentPublisher:
    """Async HTTP publisher; ``publish_candidate``/``submit_evidence`` are thread-safe."""

    def __init__(
        self,
        settings: VisionSettings,
        loop: asyncio.AbstractEventLoop,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delays_s: Sequence[float] = RETRY_DELAYS_S,
        evidence_retry_delays_s: Sequence[float] = EVIDENCE_RETRY_DELAYS_S,
        verifier: AiVerifier | None = None,
    ) -> None:
        self.settings = settings
        self._verifier = verifier
        self._thresholds = StatusThresholds(settings.status_confirmed, settings.status_probable)
        self.stats = PublishStats()
        self._loop = loop
        self._delays = tuple(retry_delays_s)
        self._evidence_delays = tuple(evidence_retry_delays_s)
        headers: dict[str, str] = {}
        if settings.ingest_token is not None:
            headers["Authorization"] = f"Bearer {settings.ingest_token.get_secret_value()}"
        self._client = httpx.AsyncClient(
            base_url=str(settings.api_url).rstrip("/"),
            headers=headers,
            timeout=30.0,
            transport=transport,
        )
        self._pending: set[Future[None]] = set()

    # ------------------------------------------------------------------ thread-safe

    def publish_candidate(
        self, candidate: IncidentCandidate, key: str, verify: VerifyContext | None = None
    ) -> None:
        self._spawn(self._send_candidate(candidate, key, verify))

    def submit_evidence(
        self,
        key: str,
        event: TriggerEvent,
        packets: Sequence[Packet],
        info: StreamInfo | None,
    ) -> None:
        self._spawn(self._send_evidence(key, event, list(packets), info))

    def _spawn(self, coroutine: Any) -> None:
        future: Future[None] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)
        future.add_done_callback(_log_failure)

    async def aclose(self, timeout_s: float = 30.0) -> None:
        """Wait for queued posts (bounded), then close the HTTP client."""
        pending = [asyncio.wrap_future(f) for f in list(self._pending)]
        if pending:
            await asyncio.wait(pending, timeout=timeout_s)
        await self._client.aclose()

    # ------------------------------------------------------------------ posting

    async def _post(
        self, path: str, delays: Sequence[float], retry_on: frozenset[int], **kwargs: Any
    ) -> httpx.Response | None:
        for delay in (*delays, None):
            try:
                response = await self._client.post(path, **kwargs)
            except httpx.HTTPError as exc:
                log.warning("POST %s failed: %s", path, exc)
            else:
                if response.status_code < 400:
                    return response
                if response.status_code < 500 and response.status_code not in retry_on:
                    log.error("POST %s rejected: %s %s", path, response.status_code, response.text)
                    return None
                log.warning("POST %s returned %s", path, response.status_code)
            if delay is None:
                return None
            await asyncio.sleep(delay)
        return None

    async def _verified(
        self, candidate: IncidentCandidate, verify: VerifyContext
    ) -> IncidentCandidate:
        """Ask the AI about a rule candidate; any failure leaves it unavailable, never blocks
        or drops it (FR-VIS-009)."""
        assert self._verifier is not None
        event = verify.event
        try:
            result = await self._verifier.verify_event(
                verify.packets, verify.info, event.evidence_t, event.trigger
            )
        except Exception:
            log.exception("verifier failed for %s", event.trigger.value)
            result = VerifierResult(available=False)
        status = classify(rule_fired=True, verifier=result, thresholds=self._thresholds)
        return candidate.model_copy(update={"verifier": result, "ai_status": status})

    async def _send_candidate(
        self, candidate: IncidentCandidate, key: str, verify: VerifyContext | None = None
    ) -> None:
        if verify is not None and self._verifier is not None:
            candidate = await self._verified(candidate, verify)
        if self.settings.ingest_token is None:
            log.warning("NADJET_INGEST_TOKEN is not set: candidate %s not published", key)
            self.stats.candidates_failed += 1
            return
        response = await self._post(
            "/internal/candidates",
            self._delays,
            frozenset(),
            content=candidate.model_dump_json(),
            headers={"Idempotency-Key": key, "Content-Type": "application/json"},
        )
        if response is None:
            self.stats.candidates_failed += 1
            log.error("candidate %s could not be published", key)
        else:
            self.stats.candidates_sent += 1
            log.info("candidate %s published (%s)", key, candidate.trigger.value)

    async def _send_evidence(
        self, key: str, event: TriggerEvent, packets: list[Packet], info: StreamInfo | None
    ) -> None:
        if info is None or self.settings.ingest_token is None:
            log.warning("evidence for %s skipped: no stream info or no token", key)
            self.stats.evidence_failed += 1
            return
        with tempfile.TemporaryDirectory(prefix="nadjet-evidence-") as tmp:
            try:
                files = await asyncio.to_thread(
                    build_evidence,
                    packets,
                    info,
                    event.evidence_t,
                    Path(tmp),
                    before_s=self.settings.evidence_before_s,
                    after_s=self.settings.evidence_after_s,
                    keyframes=self.settings.evidence_keyframes,
                )
            except Exception:
                log.exception("evidence for %s could not be cut", key)
                files = None
            if files is None:
                self.stats.evidence_failed += 1
                return
            if files.plan.pre_s < self.settings.evidence_before_s:
                log.warning(
                    "evidence for %s holds %.1f s before the peak (wanted %.1f s)",
                    key,
                    files.plan.pre_s,
                    self.settings.evidence_before_s,
                )
            await self._upload_files(key, event, files)

    async def _upload_files(self, key: str, event: TriggerEvent, files: EvidenceFiles) -> None:
        offset = event.fire_wall - event.t_fire  # stream clock -> wall clock
        start = files.plan.start_pts + offset
        end = max(p.pts_s for p in files.plan.packets) + offset
        uploads = [(files.clip, "clip", "video/mp4", start, end)] + [
            (path, "keyframe", "image/jpeg", None, None) for path in files.keyframes
        ]
        for path, kind, content_type, start_wall, end_wall in uploads:
            data: dict[str, str] = {"kind": kind, "idempotency_key": key}
            if start_wall is not None and end_wall is not None:
                data["start_ts"] = wall_time(start_wall).isoformat()
                data["end_ts"] = wall_time(end_wall).isoformat()
            response = await self._post(
                "/internal/evidence",
                self._evidence_delays,
                frozenset({CANDIDATE_NOT_PERSISTED}),
                data=data,
                files={"file": (path.name, path.read_bytes(), content_type)},
            )
            if response is None:
                self.stats.evidence_failed += 1
                log.error("evidence %s of %s could not be uploaded", path.name, key)
                continue
            stored = response.json().get("sha256")
            if stored != files.sha256[path.name]:
                self.stats.hash_mismatches += 1
                log.error("evidence %s of %s was altered in transfer", path.name, key)
            self.stats.evidence_sent += 1
