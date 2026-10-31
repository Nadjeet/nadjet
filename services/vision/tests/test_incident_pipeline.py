"""Triggers wired into the per-frame pipeline: candidate at once, evidence once the post-roll
is buffered, restart handling (FR-VIS-005, FR-VIS-006, FR-VIS-010, SC-001)."""

from collections.abc import Sequence

import numpy as np
import pytest

from nadjet_shared import IncidentCandidate, TriggerType
from nadjet_shared.catalogue import Camera, Frame, GeoPoint, Zones
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detection
from nadjet_vision.health import WorkerState
from nadjet_vision.ingest import Packet, PacketRing, SampledFrame, StreamInfo
from nadjet_vision.pipeline import CameraPipeline, build_pipeline
from nadjet_vision.track import Tracked
from nadjet_vision.triggers import TriggerConfig, TriggerEngine, TriggerEvent

ZONES = Zones(
    frame=Frame(width=160, height=90),
    live_lanes=[[(0, 30), (160, 30), (160, 90), (0, 90), (0, 30)]],
    carriageway=[(0, 20), (160, 20), (160, 90), (0, 90), (0, 20)],
)
INFO = StreamInfo("h264", 160, 90, b"", 90000)
WALL0 = 1_800_000_000.0


def camera(**extra: object) -> Camera:
    return Camera(
        id="cam-a1-pk42",
        name="A1 PK42",
        video="a.mp4",
        clip_id="demo-crash-01",
        geo=GeoPoint(lat=36.648, lon=3.329),
        road="A1",
        pk_km=42,
        wilaya="Boumerdès",
        zones=ZONES,
        **extra,  # type: ignore[arg-type]
    )


class PersonDetector:
    """A person standing on the carriageway in every frame."""

    model_id = "fake-detector"

    def detect(self, frame: np.ndarray) -> list[Detection]:  # type: ignore[type-arg]
        return [Detection((70, 40, 80, 70), 1, "person", 0.9)]


class PassThroughTracker:
    def update(self, detections: list[Detection]) -> list[Tracked]:
        return [Tracked(5, d) for d in detections]


class FakeSink:
    def __init__(self) -> None:
        self.candidates: list[tuple[IncidentCandidate, str]] = []
        self.evidence: list[tuple[str, TriggerEvent, list[Packet], StreamInfo | None]] = []

    def publish_candidate(
        self, candidate: IncidentCandidate, key: str, verify: object = None
    ) -> None:
        self.candidates.append((candidate, key))

    def submit_evidence(
        self,
        key: str,
        event: TriggerEvent,
        packets: Sequence[Packet],
        info: StreamInfo | None,
    ) -> None:
        self.evidence.append((key, event, list(packets), info))


def sampled(pts: float) -> SampledFrame:
    return SampledFrame(
        pts, np.zeros((90, 160, 3), dtype=np.uint8), decode_ms=3.0, captured_at=WALL0 + pts
    )


def make(sink: FakeSink | None, ring: PacketRing | None = None) -> CameraPipeline:
    return CameraPipeline(
        zones=ZONES,
        detector=PersonDetector(),
        tracker=PassThroughTracker(),
        state=WorkerState("cam-a1-pk42", VisionSettings(), lambda: 0, "fake-detector"),
        camera=camera(),
        triggers=TriggerEngine(TriggerConfig()),
        sink=sink,
        ring=ring,
        evidence_after_s=5.0,
    )


def fill_ring(seconds: int) -> PacketRing:
    ring = PacketRing(window_s=20)
    ring.stream = INFO
    for t in range(seconds * 5):
        ring.append(Packet(t / 5, t % 25 == 0, b"x"))
    return ring


def test_candidate_is_published_at_once_with_the_camera_registry_location() -> None:
    sink = FakeSink()
    pipeline = make(sink, fill_ring(20))
    fired = [pipeline.process(sampled(i * 0.2)).events for i in range(20)]
    assert [len(e) for e in fired].count(1) == 1
    [(candidate, key)] = sink.candidates
    assert candidate.trigger is TriggerType.PEDESTRIAN_ON_ROAD
    assert candidate.camera_id == "cam-a1-pk42"
    assert (candidate.location.road, candidate.location.pk_km) == ("A1", 42)
    assert candidate.signals["person_on_road"] == 1.0
    assert candidate.event_time.timestamp() == pytest.approx(WALL0)  # the first frame on the road
    assert key.startswith("cam-a1-pk42-")


def test_evidence_follows_only_when_the_post_roll_is_in_the_ring() -> None:
    sink = FakeSink()
    ring = fill_ring(20)
    pipeline = make(sink, ring)
    for i in range(int(2.4 / 0.2) + 1):
        pipeline.process(sampled(i * 0.2))  # trigger fires at ~2 s
    assert len(sink.candidates) == 1 and not sink.evidence
    for i in range(14, int(5.0 / 0.2)):
        pipeline.process(sampled(i * 0.2))  # still before peak (0 s) + 5 s
    assert not sink.evidence
    pipeline.process(sampled(5.0))
    [(key, event, packets, info)] = sink.evidence
    assert key == sink.candidates[0][1]
    assert event.evidence_t == 0.0
    assert info is INFO
    assert packets and packets[0].keyframe
    pipeline.process(sampled(5.2))
    assert len(sink.evidence) == 1  # handed over once


def test_stream_restart_hands_over_what_the_ring_still_has() -> None:
    sink = FakeSink()
    pipeline = make(sink, fill_ring(20))
    for i in range(15):
        pipeline.process(sampled(i * 0.2))
    assert len(sink.candidates) == 1 and not sink.evidence
    pipeline.process(sampled(0.0))  # the looped clip starts over
    assert len(sink.evidence) == 1


def test_no_sink_means_no_publishing_and_no_failure() -> None:
    pipeline = make(None)
    results = [pipeline.process(sampled(i * 0.2)) for i in range(20)]
    assert sum(len(r.events) for r in results) == 1  # still detected, just not published


def test_build_pipeline_applies_settings_cooldown_and_camera_overrides() -> None:
    settings = VisionSettings(trigger_cooldown_s=60.0, evidence_after_s=7.0)
    state = WorkerState("cam-a1-pk42", settings, lambda: 0, "fake-detector")
    pipeline = build_pipeline(
        camera(triggers={"stalled_s": 12, "confirm_frames": 4, "cooldown_s": 30}),
        settings,
        PersonDetector(),
        PassThroughTracker(),
        state,
        publisher=None,
        sink=None,
        ring=PacketRing(),
    )
    assert pipeline.triggers is not None
    config = pipeline.triggers.config
    assert (config.stalled_s, config.confirm_frames) == (12.0, 4)
    assert config.cooldown_s == 30.0  # the camera wins over the global setting
    assert config.pedestrian_s == 2.0  # untouched default
    assert pipeline.zones is ZONES


def test_build_pipeline_uses_the_settings_cooldown_by_default() -> None:
    settings = VisionSettings(trigger_cooldown_s=60.0)
    pipeline = build_pipeline(
        camera(),
        settings,
        PersonDetector(),
        PassThroughTracker(),
        WorkerState("cam-a1-pk42", settings, lambda: 0, "fake-detector"),
        publisher=None,
        sink=None,
        ring=PacketRing(),
    )
    assert pipeline.triggers is not None
    assert pipeline.triggers.config.cooldown_s == 60.0


def test_unknown_camera_threshold_fails_when_the_worker_is_built() -> None:
    settings = VisionSettings()
    with pytest.raises(ValueError, match="unknown trigger threshold"):
        build_pipeline(
            camera(triggers={"stalled": 12}),
            settings,
            PersonDetector(),
            PassThroughTracker(),
            WorkerState("cam-a1-pk42", settings, lambda: 0, "fake-detector"),
            publisher=None,
            sink=None,
            ring=PacketRing(),
        )
