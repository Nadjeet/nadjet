"""Candidate building, keys, retrying posts and evidence upload (FR-VIS-006, FR-VIS-009)."""

import asyncio
import hashlib
import json
from email.parser import BytesParser
from email.policy import HTTP

import httpx
import pytest
from pydantic import SecretStr

from nadjet_shared import AiStatus, IncidentCandidate, TriggerType
from nadjet_shared.catalogue import Camera, GeoPoint
from nadjet_vision.config import VisionSettings
from nadjet_vision.publish import (
    IncidentPublisher,
    build_candidate,
    candidate_key,
)
from nadjet_vision.triggers import TriggerEvent

from .conftest import StreamFactory

WALL = 1_800_000_000.0


def camera() -> Camera:
    return Camera(
        id="cam-a1-pk42",
        name="A1 PK42",
        video="a.mp4",
        clip_id="demo-crash-01",
        geo=GeoPoint(lat=36.648, lon=3.329),
        road="A1",
        pk_km=42,
        wilaya="Boumerdès",
    )


def event(**overrides: object) -> TriggerEvent:
    data: dict[str, object] = {
        "trigger": TriggerType.COLLISION_CANDIDATE,
        "t_start": 9.0,
        "t_peak": 10.0,
        "t_fire": 14.0,
        "evidence_t": 10.0,
        "track_ids": (1, 2),
        "signals": {"vehicle_count": 2.0, "overlap_iou": 0.2},
        "peak_wall": WALL + 10.0,
        "fire_wall": WALL + 14.0,
    }
    data.update(overrides)
    return TriggerEvent(**data)  # type: ignore[arg-type]


def settings(token: str | None = "secret") -> VisionSettings:
    return VisionSettings(ingest_token=SecretStr(token) if token else None)


def test_candidate_carries_the_registry_location_and_the_rule_signals() -> None:
    candidate = build_candidate(camera(), event())
    assert candidate.camera_id == "cam-a1-pk42"
    assert (candidate.location.lat, candidate.location.lon) == (36.648, 3.329)
    assert (candidate.location.road, candidate.location.pk_km) == ("A1", 42)
    assert candidate.location.wilaya == "Boumerdès"
    assert candidate.trigger is TriggerType.COLLISION_CANDIDATE
    assert candidate.track_ids == [1, 2]
    assert candidate.signals == {"vehicle_count": 2.0, "overlap_iou": 0.2}
    assert candidate.event_time.timestamp() == pytest.approx(WALL + 10.0)
    assert candidate.detected_at.timestamp() == pytest.approx(WALL + 14.0)
    assert candidate.event_time.utcoffset() is not None


def test_candidate_without_a_verifier_is_probable_never_confirmed() -> None:
    """FR-VIS-009 and FR-VIS-007: rules alone, verifier unavailable."""
    candidate = build_candidate(camera(), event())
    assert candidate.verifier.available is False
    assert candidate.ai_status is AiStatus.PROBABLE


def test_candidate_key_is_stable_and_distinguishes_events() -> None:
    a = candidate_key("cam-a1-pk42", event())
    assert a == candidate_key("cam-a1-pk42", event())
    assert a != candidate_key("cam-a1-pk42", event(peak_wall=WALL + 11.0))
    assert a != candidate_key("cam-a1-pk42", event(track_ids=(1, 3)))
    assert a != candidate_key("cam-other", event())
    assert a != candidate_key("cam-a1-pk42", event(trigger=TriggerType.HARD_STOP))
    assert 1 <= len(a) <= 128  # the API's Idempotency-Key limit


class Api:
    """A fake coordination API recording what it receives."""

    def __init__(self, candidate_statuses: tuple[int, ...] = (202,), evidence_early: int = 0):
        self.candidate_statuses = list(candidate_statuses)
        self.evidence_early = evidence_early  # 409s before the incident exists
        self.candidates: list[tuple[dict[str, str], IncidentCandidate]] = []
        self.uploads: list[dict[str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/candidates":
            status = self.candidate_statuses.pop(0) if self.candidate_statuses else 202
            if status == 202:
                self.candidates.append(
                    (
                        dict(request.headers),
                        IncidentCandidate.model_validate_json(request.content),
                    )
                )
            return httpx.Response(status, json={"stream_id": "1-0"})
        if request.url.path == "/internal/evidence":
            if self.evidence_early > 0:
                self.evidence_early -= 1
                return httpx.Response(409, json={"detail": "Candidate not persisted yet"})
            message = BytesParser(policy=HTTP).parsebytes(
                b"Content-Type: "
                + request.headers["content-type"].encode()
                + b"\r\n\r\n"
                + request.content
            )
            fields: dict[str, object] = {}
            sha = ""
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                payload = part.get_payload(decode=True)
                if name == "file":
                    sha = hashlib.sha256(payload).hexdigest()
                    fields["content_type"] = part.get_content_type()
                    fields["filename"] = part.get_filename()
                else:
                    fields[str(name)] = payload.decode()
            self.uploads.append(fields)
            return httpx.Response(201, json={"sha256": sha})
        return httpx.Response(404)


def publisher(api: Api, token: str | None = "secret") -> IncidentPublisher:
    return IncidentPublisher(
        settings(token),
        asyncio.get_running_loop(),
        transport=httpx.MockTransport(api),
        retry_delays_s=(0.0, 0.0, 0.0),
        evidence_retry_delays_s=(0.0, 0.0, 0.0),
    )


async def test_candidate_is_posted_with_token_and_idempotency_key() -> None:
    api = Api()
    sink = publisher(api)
    candidate = build_candidate(camera(), event())
    key = candidate_key("cam-a1-pk42", event())
    sink.publish_candidate(candidate, key)
    await sink.aclose()
    [(headers, received)] = api.candidates
    assert headers["authorization"] == "Bearer secret"
    assert headers["idempotency-key"] == key
    assert received == candidate
    assert sink.stats.candidates_sent == 1


async def test_candidate_post_is_retried_on_server_errors() -> None:
    api = Api(candidate_statuses=(503, 500, 202))
    sink = publisher(api)
    sink.publish_candidate(build_candidate(camera(), event()), "k")
    await sink.aclose()
    assert len(api.candidates) == 1
    assert sink.stats.candidates_sent == 1


async def test_candidate_post_gives_up_and_counts_the_failure() -> None:
    api = Api(candidate_statuses=(503,) * 10)
    sink = publisher(api)
    sink.publish_candidate(build_candidate(camera(), event()), "k")
    await sink.aclose()
    assert not api.candidates
    assert (sink.stats.candidates_sent, sink.stats.candidates_failed) == (0, 1)


async def test_rejected_candidate_is_not_retried() -> None:
    api = Api(candidate_statuses=(422, 202))
    sink = publisher(api)
    sink.publish_candidate(build_candidate(camera(), event()), "k")
    await sink.aclose()
    assert not api.candidates  # the 202 was never requested
    assert sink.stats.candidates_failed == 1


async def test_without_a_token_nothing_is_sent_and_it_is_counted() -> None:
    api = Api()
    sink = publisher(api, token=None)
    sink.publish_candidate(build_candidate(camera(), event()), "k")
    await sink.aclose()
    assert not api.candidates
    assert sink.stats.candidates_failed == 1


async def test_evidence_uploads_clip_and_six_keyframes_after_waiting_for_the_incident(
    synthetic_stream: StreamFactory,
) -> None:
    packets, info = synthetic_stream()
    api = Api(evidence_early=2)
    sink = publisher(api)
    key = "cam-a1-pk42-abc"
    sink.submit_evidence(key, event(t_peak=14.0, t_fire=18.0, evidence_t=14.0), packets, info)
    await sink.aclose()

    kinds = [u["kind"] for u in api.uploads]
    assert kinds == ["clip"] + ["keyframe"] * 6
    assert {u["idempotency_key"] for u in api.uploads} == {key}
    clip = api.uploads[0]
    assert (clip["content_type"], clip["filename"]) == ("video/mp4", "clip.mp4")
    assert "start_ts" in clip and "end_ts" in clip
    assert api.uploads[1]["content_type"] == "image/jpeg"
    assert sink.stats.evidence_sent == 7
    assert (sink.stats.evidence_failed, sink.stats.hash_mismatches) == (0, 0)


async def test_evidence_without_a_stream_description_is_counted_not_raised() -> None:
    api = Api()
    sink = publisher(api)
    sink.submit_evidence("k", event(), [], None)
    await sink.aclose()
    assert not api.uploads
    assert sink.stats.evidence_failed == 1


async def test_evidence_with_no_keyframe_before_the_peak_is_counted() -> None:
    from nadjet_vision.ingest import Packet, StreamInfo

    api = Api()
    sink = publisher(api)
    info = StreamInfo("h264", 160, 96, b"", 90000)
    sink.submit_evidence("k", event(evidence_t=1.0), [Packet(5.0, True, b"x")], info)
    await sink.aclose()
    assert not api.uploads
    assert sink.stats.evidence_failed == 1


async def test_a_hash_that_differs_from_the_local_one_is_reported(
    synthetic_stream: StreamFactory,
) -> None:
    packets, info = synthetic_stream(seconds=14)

    def tampering(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, content=json.dumps({"sha256": "0" * 64}))

    sink = IncidentPublisher(
        settings(), asyncio.get_running_loop(), transport=httpx.MockTransport(tampering)
    )
    sink.submit_evidence("k", event(t_peak=11.0, t_fire=12.0, evidence_t=11.0), packets, info)
    await sink.aclose()
    assert sink.stats.hash_mismatches == 7
