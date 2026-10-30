"""Worker of the public "try it yourself" sandbox (PRD FR-CIT-002..005, doc 11 TD-23, TD-40).

Two jobs, both on the same Brev pipeline as the real cameras and both talking to the API only
over HTTP:

- uploaded clips: claim a job, run detector, tracker and trigger rules over the clip for the
  annotated video and the rule timeline, then the two-pass AI analysis (pass 1 scans the whole
  clip at 1-2 fps, pass 2 looks at the found moment at 4 fps; the correction is damped and
  capped; the detector only snaps the result onto vehicles);
- live phone cameras: attach to ``live/<session>`` like a CCTV feed with an AI check every 4 s.

Results never go to ``/internal/candidates``: a sandbox incident is a field of the job result.
If the AI is down the rule-based analysis is still returned and says so (FR-CIT-005).
"""

import asyncio
import contextlib
import logging
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx

from nadjet_shared import AiStatus, TriggerType, VerifierResult
from nadjet_shared.catalogue import Camera, GeoPoint
from nadjet_shared.tryit import (
    Box,
    SandboxIncident,
    SessionEvent,
    TimelineEntry,
    TryAiReport,
    TryJobClaim,
    TryJobFailure,
    TryProgress,
    TryResult,
    TrySessionRef,
)
from nadjet_vision.annotate import draw
from nadjet_vision.clipvideo import Mp4Writer, decode_nearest
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detection, Detector
from nadjet_vision.evidence import plan_clip
from nadjet_vision.ingest import (
    BgrFrame,
    FrameSampler,
    Packet,
    PacketRing,
    StreamInfo,
    iter_frames,
)
from nadjet_vision.pipeline import CameraPipeline, build_pipeline
from nadjet_vision.publish import IncidentPublisher, VerifyContext
from nadjet_vision.replay import CollectingSink
from nadjet_vision.status import StatusThresholds, classify
from nadjet_vision.track import Tracker
from nadjet_vision.triggers import TriggerEvent
from nadjet_vision.verifier import AiVerifier
from nadjet_vision.worker import check_api

log = logging.getLogger("nadjet_vision.tryit")

MAX_CLIP_S = 60.0
CORRECTION_DAMPING = 0.35  # doc 11 §6: pass-2 correction damped x0.35 ...
CORRECTION_CAP_S = 1.5  # ... and capped at +-1.5 s
TRIGGER_NEAR_S = 5.0
VEHICLES = frozenset({"car", "motorcycle", "bus", "truck"})
COLLISION_RULES = frozenset({TriggerType.COLLISION_CANDIDATE, TriggerType.HARD_STOP})
STATUS_EVERY_S = 10.0
LIVE_LAT, LIVE_LON = 36.7538, 3.0588  # a demo camera has no real place (not shown as one)


class ClipRejected(Exception):
    """The file is not a usable video: nothing was analysed (PRD E-12)."""


# --------------------------------------------------------------------------- pure logic


def damped_time(scan_t: float, refine_t: float | None) -> float:
    """Pass-1 time corrected by pass 2: x0.35 of the difference, at most +-1.5 s (TD-23)."""
    if refine_t is None:
        return scan_t
    correction = CORRECTION_DAMPING * (refine_t - scan_t)
    return scan_t + max(-CORRECTION_CAP_S, min(CORRECTION_CAP_S, correction))


def _centre(d: Detection) -> tuple[float, float]:
    return d.centre


def snap_vehicles(detections: Sequence[Detection], count: int) -> list[Detection]:
    """The ``count`` vehicles that sit closest together (the ones the AI says were involved).

    The detector never decides whether there was a collision, it only places the AI's answer on
    vehicles (TD-23): all vehicles when there are not more than ``count``.
    """
    vehicles = [d for d in detections if d.label in VEHICLES]
    count = max(1, count)
    if len(vehicles) <= count:
        return vehicles
    pair = min(
        ((a, b) for i, a in enumerate(vehicles) for b in vehicles[i + 1 :]),
        key=lambda p: (
            (_centre(p[0])[0] - _centre(p[1])[0]) ** 2 + (_centre(p[0])[1] - _centre(p[1])[1]) ** 2
        ),
    )
    chosen = list(pair)
    while len(chosen) < count:
        cx = sum(_centre(d)[0] for d in chosen) / len(chosen)
        cy = sum(_centre(d)[1] for d in chosen) / len(chosen)
        rest = [d for d in vehicles if d not in chosen]
        chosen.append(
            min(rest, key=lambda d: (_centre(d)[0] - cx) ** 2 + (_centre(d)[1] - cy) ** 2)
        )
    return chosen[:count]


def to_box(detection: Detection) -> Box:
    x1, y1, x2, y2 = detection.box
    return Box(x1=x1, y1=y1, x2=x2, y2=y2, label=detection.label)


def verdict_label(result: VerifierResult) -> str:
    if not result.available:
        return "AI unavailable"
    return {
        "yes": "collision visible",
        "no": "no collision visible",
        "cannot_judge": "cannot judge",
    }.get(result.collision_visible or "", "no verdict")


def build_incident(
    *,
    triggers: Sequence[tuple[TriggerType, float]],
    scan: VerifierResult | None,
    refine: VerifierResult | None,
    event_t: float | None,
    vehicles: Sequence[Box],
    thresholds: StatusThresholds,
) -> SandboxIncident | None:
    """The sandbox incident an operator would have seen: rules and AI together (FR-VIS-007).

    ``triggers`` are (rule, clip seconds). ``confirmed`` (type ``collision``) needs both a
    collision rule near the moment and an AI verdict of high probability; AI alone or rules
    alone never confirm.
    """
    verdict = refine if refine is not None and refine.available else scan
    ai_yes = event_t is not None
    collision_rules = [(t, s) for t, s in triggers if t in COLLISION_RULES]
    if not ai_yes and not collision_rules:
        return None
    moment = event_t if event_t is not None else min(s for _, s in collision_rules)
    near = [t for t, s in collision_rules if abs(s - moment) <= TRIGGER_NEAR_S]
    status = classify(
        rule_fired=bool(near),
        verifier=verdict if verdict is not None else VerifierResult(available=False),
        thresholds=thresholds,
    )
    return SandboxIncident(
        type="collision" if status is AiStatus.CONFIRMED else "possible_incident",
        ai_status=status,
        event_time_s=max(moment, 0.0),
        trigger=near[0].value if near else None,
        vehicles=list(vehicles),
        description_fr=verdict.description_fr if verdict else None,
        description_ar=verdict.description_ar if verdict else None,
    )


# --------------------------------------------------------------------------- clip analysis


def probe_clip(path: Path, max_seconds: float = MAX_CLIP_S) -> float:
    """Duration of the clip; raises ``ClipRejected`` for no video stream or too long (E-12)."""
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise ClipRejected("No video stream in the file")
            seconds = float(container.duration) / 1_000_000 if container.duration else 0.0
    except av.error.FFmpegError as exc:
        raise ClipRejected("The file could not be read as a video") from exc
    if seconds > max_seconds + 0.5:
        raise ClipRejected(f"Longer than {max_seconds:.0f} s")
    return seconds


@dataclass
class Analysed:
    result: TryResult
    video: Path | None


def detect_pass(
    path: Path,
    *,
    settings: VisionSettings,
    detector: Detector,
    tracker: Tracker,
    ring: PacketRing,
    video_path: Path,
    on_progress: Callable[[float], None],
    duration_s: float,
    draw_frame: Callable[..., BgrFrame] = draw,
) -> tuple[list[TriggerEvent], int, float, float]:
    """Run the real pipeline over the clip (blocking): returns trigger events, frame count and
    the first and last stream times. Boxes are drawn into ``video_path``."""
    camera = Camera(
        id="try-upload",
        name="Try upload",
        video="upload",
        clip_id="upload",
        geo=GeoPoint(lat=LIVE_LAT, lon=LIVE_LON),
        road="upload",
        wilaya="-",
    )
    sink = CollectingSink()
    from nadjet_vision.health import WorkerState

    state = WorkerState(camera.id, settings, lambda: 0, detector.model_id)
    pipeline: CameraPipeline = build_pipeline(
        camera, settings, detector, tracker, state, publisher=None, sink=sink, ring=ring
    )
    writer = Mp4Writer(str(video_path), settings.sample_fps)
    frames = iter_frames(
        str(path),
        lambda: False,
        sampler=FrameSampler(settings.sample_fps),
        ring=ring,
        options={},
        open_timeout=None,
    )
    first: float | None = None
    last = 0.0
    count = 0
    try:
        for frame in frames:
            first = frame.pts_s if first is None else first
            last = frame.pts_s
            # The header may give no duration (fragmented MP4, WebM): enforce E-12 on the
            # decoded stream itself, or a 2 h file would hold the single job loop for hours.
            if last - first > MAX_CLIP_S + 0.5:
                raise ClipRejected(f"Longer than {MAX_CLIP_S:.0f} s")
            outcome = pipeline.process(frame)
            writer.write(draw_frame(frame.image, outcome.tracked, outcome.speeds, None))
            count += 1
            if count % 5 == 0 and duration_s > 0:
                on_progress(min(1.0, (last - first) / duration_s))
    finally:
        writer.close()
    return [c.event for c in sink.captured], count, first or 0.0, last


async def analyse_clip(
    path: Path,
    video_path: Path,
    *,
    settings: VisionSettings,
    detector: Detector,
    tracker: Tracker,
    verifier: AiVerifier | None,
    report: Callable[[str, float], None],
    draw_frame: Callable[..., BgrFrame] = draw,
) -> Analysed:
    """Both passes on one clip. ``report(stage, progress)`` is called from any thread."""
    duration = probe_clip(path)
    ring = PacketRing(window_s=10 * MAX_CLIP_S, max_packets=int(MAX_CLIP_S * 130))
    report("detect", 0.0)
    events, frames, first, last = await asyncio.to_thread(
        detect_pass,
        path,
        settings=settings,
        detector=detector,
        tracker=tracker,
        ring=ring,
        video_path=video_path,
        on_progress=lambda f: report("detect", 0.6 * f),
        duration_s=duration,
        draw_frame=draw_frame,
    )
    if frames == 0:
        raise ClipRejected("No frames could be decoded")
    packets, info = ring.snapshot(), ring.stream
    span = last - first
    timeline = [
        TimelineEntry(
            t=max(e.t_peak - first, 0.0),
            kind="trigger",
            label=e.trigger.value,
            source=f"rule:{e.trigger.value}",
            detail=", ".join(f"{k}={v:.2f}" for k, v in e.signals.items()),
        )
        for e in events
    ]
    scan = refine = None
    scan_t = event_t = None
    if verifier is not None and settings.verify_candidates:
        report("ai_scan", 0.65)
        scan = await verifier.scan(packets, info, first, last)
        if scan.available:
            timeline.append(_ai_entry("ai_scan", scan.t_contact, scan, span))
        if scan.available and scan.collision_visible == "yes" and scan.t_contact is not None:
            scan_t = first + max(0.0, min(span, scan.t_contact))
            report("ai_refine", 0.8)
            refine = await verifier.verify_event(packets, info, scan_t, TriggerType.AI_SWEEP)
            refine_t = None
            if refine.available and refine.collision_visible == "yes":
                if refine.t_contact is not None:
                    refine_t = scan_t + refine.t_contact
                event_t = damped_time(scan_t, refine_t)
            if refine.available:
                timeline.append(
                    _ai_entry(
                        "ai_refine",
                        None if event_t is None else event_t - first,
                        refine,
                        span,
                    )
                )
    vehicles: list[Box] = []
    if event_t is not None:
        count = (refine.vehicles_involved if refine else None) or 2
        vehicles = await asyncio.to_thread(_snap_at, detector, packets, info, event_t, count)
    thresholds = StatusThresholds(settings.status_confirmed, settings.status_probable)
    incident = build_incident(
        triggers=[(e.trigger, e.t_peak - first) for e in events],
        scan=scan,
        refine=refine,
        event_t=None if event_t is None else event_t - first,
        vehicles=vehicles,
        thresholds=thresholds,
    )
    result = TryResult(
        duration_s=span,
        frames_analysed=frames,
        ai_available=bool(scan and scan.available),
        scan=scan,
        refine=refine,
        scan_t_s=None if scan_t is None else scan_t - first,
        event_t_s=None if event_t is None else max(event_t - first, 0.0),
        timeline=sorted(timeline, key=lambda t: t.t),
        sandbox_incident=incident,
        models={
            "detector": detector.model_id,
            **({"verifier": scan.model} if scan and scan.model else {}),
        },
    )
    return Analysed(result, video_path if await anyio.Path(video_path).is_file() else None)


def _ai_entry(kind: str, at: float | None, result: VerifierResult, span: float) -> TimelineEntry:
    return TimelineEntry(
        t=max(0.0, min(span, at if at is not None else 0.0)),
        kind=kind,
        label=verdict_label(result),
        source=result.model or "ai",
        detail=result.description_fr,
    )


def _snap_at(
    detector: Detector,
    packets: Sequence[Packet],
    info: StreamInfo | None,
    at_s: float,
    count: int,
) -> list[Box]:
    if info is None:
        return []
    plan = plan_clip(packets, at_s, before_s=15.0, after_s=0.0)
    if plan is None:
        return []
    frames = decode_nearest(plan.packets, info, [at_s])
    if not frames:
        return []
    image: BgrFrame = frames[-1][1].to_ndarray(format="bgr24")
    return [to_box(d) for d in snap_vehicles(detector.detect(image), count)]


# --------------------------------------------------------------------------- API client


class TryApi:
    """The worker's side of ``/internal/try``."""

    def __init__(
        self, settings: VisionSettings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        headers = {}
        if settings.ingest_token is not None:
            headers["Authorization"] = f"Bearer {settings.ingest_token.get_secret_value()}"
        self._client = httpx.AsyncClient(
            base_url=str(settings.api_url).rstrip("/") + "/internal/try",
            headers=headers,
            timeout=60.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def claim(self) -> TryJobClaim | None:
        response = await self._client.post("/claim")
        response.raise_for_status()
        return None if response.status_code == 204 else TryJobClaim.model_validate(response.json())

    async def download(self, job_id: str, dest: Path) -> None:
        async with self._client.stream("GET", f"/jobs/{job_id}/file") as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                async for chunk in response.aiter_bytes(1 << 20):
                    handle.write(chunk)

    async def progress(self, job_id: str, stage: str, progress: float) -> None:
        body = TryProgress(stage=stage, progress=round(progress, 3))
        await self._client.post(
            f"/jobs/{job_id}/progress",
            content=body.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )

    async def upload_video(self, job_id: str, path: Path) -> None:
        data = await anyio.Path(path).read_bytes()
        response = await self._client.put(f"/jobs/{job_id}/video", content=data)
        response.raise_for_status()

    async def result(self, job_id: str, result: TryResult) -> None:
        response = await self._client.post(
            f"/jobs/{job_id}/result",
            content=result.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    async def fail(self, job_id: str, error: str, *, rejected: bool = False) -> None:
        body = TryJobFailure(error=error[:300], rejected=rejected)
        await self._client.post(
            f"/jobs/{job_id}/fail",
            content=body.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )

    async def sessions(self) -> list[TrySessionRef]:
        response = await self._client.get("/sessions")
        response.raise_for_status()
        return [TrySessionRef.model_validate(r) for r in response.json()]

    async def session_event(self, session_id: str, event: SessionEvent) -> None:
        await self._client.post(
            f"/sessions/{session_id}/events",
            content=event.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )

    async def report_ai(self, available: bool) -> None:
        body = TryAiReport(ai_available=available)
        await self._client.post(
            "/status", content=body.model_dump_json(), headers={"Content-Type": "application/json"}
        )


# --------------------------------------------------------------------------- upload worker


async def process_job(
    api: TryApi,
    claim: TryJobClaim,
    *,
    settings: VisionSettings,
    detector: Detector,
    make_tracker: Callable[[], Tracker],
    verifier: AiVerifier | None,
    draw_frame: Callable[..., BgrFrame] = draw,
) -> None:
    loop = asyncio.get_running_loop()

    def report(stage: str, progress: float) -> None:
        asyncio.run_coroutine_threadsafe(api.progress(claim.id, stage, progress), loop)

    with tempfile.TemporaryDirectory(prefix="nadjet-try-") as tmp:
        source = Path(tmp) / "upload"
        video = Path(tmp) / "annotated.mp4"
        try:
            await api.download(claim.id, source)
            analysed = await analyse_clip(
                source,
                video,
                settings=settings,
                detector=detector,
                tracker=make_tracker(),
                verifier=verifier,
                report=report,
                draw_frame=draw_frame,
            )
            if analysed.video is not None:
                await api.upload_video(claim.id, analysed.video)
            await api.result(claim.id, analysed.result)
        except ClipRejected as exc:
            await api.fail(claim.id, str(exc), rejected=True)
        except Exception:
            log.exception("try job %s failed", claim.id)
            await api.fail(claim.id, "The analysis failed")


async def report_ai_loop(
    api: TryApi, client: Any, stop: asyncio.Event, every_s: float = STATUS_EVERY_S
) -> None:
    """Tell the API whether the Brev AI answers, so the page can say "AI unavailable"."""
    while not stop.is_set():
        available = False
        with contextlib.suppress(Exception):
            await client.check()
            available = True
        with contextlib.suppress(Exception):
            await api.report_ai(available)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=every_s)


async def job_loop(
    api: TryApi,
    stop: asyncio.Event,
    *,
    settings: VisionSettings,
    detector: Detector,
    make_tracker: Callable[[], Tracker],
    verifier: AiVerifier | None,
    draw_frame: Callable[..., BgrFrame] = draw,
) -> None:
    while not stop.is_set():
        claim: TryJobClaim | None = None
        try:
            claim = await api.claim()
        except httpx.HTTPError as exc:
            log.warning("try-it API unreachable: %s", exc)
        if claim is not None:
            await process_job(
                api,
                claim,
                settings=settings,
                detector=detector,
                make_tracker=make_tracker,
                verifier=verifier,
                draw_frame=draw_frame,
            )
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.try_poll_s)


# --------------------------------------------------------------------------- live phones


class SandboxPublisher(IncidentPublisher):
    """Publisher of a live phone session: results go to the session, never to the incident
    queue (``/internal/candidates``), and there is no evidence to store."""

    def __init__(
        self,
        settings: VisionSettings,
        loop: asyncio.AbstractEventLoop,
        api: TryApi,
        session_id: str,
        *,
        verifier: AiVerifier | None,
    ) -> None:
        super().__init__(settings, loop, verifier=verifier)
        self._api = api
        self._session_id = session_id

    async def _emit(self, event: SessionEvent) -> None:
        with contextlib.suppress(httpx.HTTPError):
            await self._api.session_event(self._session_id, event)

    async def _send_candidate(
        self, candidate: Any, key: str, verify: VerifyContext | None = None
    ) -> None:
        if verify is not None and self._verifier is not None:
            candidate = await self._verified(candidate, verify)
        await self._emit(
            SessionEvent(
                at=datetime.now(UTC),
                kind="trigger",
                label=candidate.trigger.value,
                source=f"rule:{candidate.trigger.value}",
                ai_status=candidate.ai_status,
                verifier=candidate.verifier,
            )
        )
        self.stats.candidates_sent += 1

    def submit_evidence(self, key: str, event: TriggerEvent, packets: Any, info: Any) -> None:
        return None

    def record_check(self, result: VerifierResult, wall: float) -> None:
        """One AI check of the live stream (every 4 s), whatever it says."""
        self._spawn(
            self._emit(
                SessionEvent(
                    at=datetime.now(UTC),
                    kind="ai_check",
                    label=verdict_label(result),
                    source=result.model or "ai",
                    verifier=result,
                )
            )
        )


def live_camera(ref: TrySessionRef) -> Camera:
    code = ref.path.removeprefix("live/")
    return Camera(
        id=f"live-{code}",
        name=f"Live demo ({code})",
        video="live",
        clip_id="live",
        geo=GeoPoint(lat=LIVE_LAT, lon=LIVE_LON),
        road="live demo",
        wilaya="-",
    )


async def live_watcher(
    api: TryApi,
    stop: asyncio.Event,
    *,
    settings: VisionSettings,
    detector: Detector,
    make_tracker: Callable[[], Tracker],
    verifier: AiVerifier | None,
    run_session: Callable[..., Any] | None = None,
) -> None:
    """Attach a worker to every live session the API lists, detach when it disappears."""
    from nadjet_vision.pipeline import run_worker

    runner = run_session or run_worker
    live_settings = settings.model_copy(
        update={
            "sweep_enabled": True,
            "sweep_every_s": settings.live_check_s,
            "metrics_port": None,
            "publish_candidates": True,
        }
    )
    running: dict[str, tuple[asyncio.Event, asyncio.Task[None]]] = {}
    loop = asyncio.get_running_loop()
    try:
        while not stop.is_set():
            try:
                refs = {r.id: r for r in await api.sessions()}
            except httpx.HTTPError as exc:
                log.warning("try-it API unreachable: %s", exc)
                refs = {r_id: TrySessionRef(id=r_id, path="") for r_id in running}
            for session_id, (event, task) in list(running.items()):
                if session_id not in refs or task.done():
                    event.set()
                    if task.done() and session_id in refs:
                        log.warning("live session %s worker ended", session_id)
                    running.pop(session_id)
            for session_id, ref in refs.items():
                if session_id in running or not ref.path:
                    continue
                sink = SandboxPublisher(live_settings, loop, api, session_id, verifier=verifier)
                session_stop = asyncio.Event()
                camera = live_camera(ref)

                async def attach(
                    ref: TrySessionRef = ref,
                    camera: Camera = camera,
                    sink: SandboxPublisher = sink,
                    session_stop: asyncio.Event = session_stop,
                ) -> None:
                    try:
                        await runner(
                            camera.id,
                            live_settings,
                            session_stop,
                            detector=detector,
                            tracker=make_tracker(),
                            sink=sink,
                            verifier=verifier,
                            camera=camera,
                            stream_path=ref.path,
                            push_health=False,
                            on_check=sink.record_check,
                        )
                    finally:
                        await sink.aclose()

                running[session_id] = (session_stop, asyncio.create_task(attach()))
                log.info("attached to live session %s (%s)", session_id, ref.path)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.try_poll_s)
    finally:
        for event, _task in running.values():
            event.set()
        await asyncio.gather(*(t for _, t in running.values()), return_exceptions=True)


# --------------------------------------------------------------------------- entry point


class LockedDetector:
    """One detector shared by concurrent sessions and jobs: calls are serialised."""

    def __init__(self, detector: Detector) -> None:
        self._detector = detector
        self.model_id = detector.model_id
        import threading

        self._lock = threading.Lock()

    def detect(self, frame: Any) -> list[Detection]:
        with self._lock:
            return self._detector.detect(frame)


async def run_try_worker(settings: VisionSettings, stop: asyncio.Event) -> None:
    """Upload jobs, live sessions and the AI status flag, until ``stop``."""
    from nadjet_vision.detect import load_detector
    from nadjet_vision.inference import BrevVlmClient
    from nadjet_vision.track import ByteTrackTracker

    detector = LockedDetector(load_detector(settings))
    client = BrevVlmClient(settings)  # refuses any endpoint that is not Brev
    verifier = AiVerifier(
        client,
        settings.vlm_model,
        budget_s=settings.vlm_budget_s,
        backoff_s=settings.vlm_backoff_s,
    )
    api = TryApi(settings)

    def make_tracker() -> Tracker:
        return ByteTrackTracker(settings.sample_fps, settings.detector_threshold)

    await check_api(settings)
    tasks = [
        asyncio.create_task(report_ai_loop(api, client, stop)),
        asyncio.create_task(
            job_loop(
                api,
                stop,
                settings=settings,
                detector=detector,
                make_tracker=make_tracker,
                verifier=verifier,
            )
        ),
        asyncio.create_task(
            live_watcher(
                api,
                stop,
                settings=settings,
                detector=detector,
                make_tracker=make_tracker,
                verifier=verifier,
            )
        ),
    ]
    try:
        await stop.wait()
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        await api.aclose()
        await client.aclose()
