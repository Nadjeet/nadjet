"""Replay one clip through the real per-frame pipeline and collect its alerts (doc 04 §5).

The same ``CameraPipeline`` that runs on a camera processes the frames (detector, tracker,
trigger rules, packet ring). Time is the stream clock: the cooldown runs on a virtual wall clock
equal to the clip's timestamps, so a replay behaves the same at any speed. The AI verifier and
sweep are asked after the clip, one call at a time, on exactly the ring snapshots the live
worker would have used; their latencies are recorded.
"""

import dataclasses
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from nadjet_shared import IncidentCandidate, VerifierResult
from nadjet_shared.catalogue import Camera
from nadjet_shared.evaluation import AlertRecord
from nadjet_vision.clipvideo import SWEEP_WINDOW_S
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detector
from nadjet_vision.health import WorkerState
from nadjet_vision.ingest import Packet, PacketRing, SampledFrame, StreamInfo
from nadjet_vision.pipeline import build_pipeline
from nadjet_vision.publish import VerifyContext
from nadjet_vision.status import StatusThresholds, classify
from nadjet_vision.sweep import SweepTracker, should_emit, sweep_event
from nadjet_vision.track import Tracker
from nadjet_vision.triggers import TriggerEvent
from nadjet_vision.verifier import AiVerifier

VIRTUAL_EPOCH = 1_000_000_000.0


@dataclass
class _Captured:
    candidate: IncidentCandidate
    event: TriggerEvent
    packets: Sequence[Packet]
    info: StreamInfo | None


class CollectingSink:
    """Keeps what the pipeline would have published; nothing leaves the process."""

    def __init__(self) -> None:
        self.captured: list[_Captured] = []

    def publish_candidate(
        self, candidate: IncidentCandidate, key: str, verify: VerifyContext | None = None
    ) -> None:
        assert verify is not None  # the pipeline always passes the ring at fire time
        self.captured.append(_Captured(candidate, verify.event, verify.packets, verify.info))

    def submit_evidence(self, key: str, event: TriggerEvent, packets: object, info: object) -> None:
        return None


@dataclass
class ReplayResult:
    duration_s: float
    alerts: list[AlertRecord]
    frame_ms: list[float] = field(default_factory=list)
    verify_ms: list[float] = field(default_factory=list)
    sweep_ms: list[float] = field(default_factory=list)


def _record(
    event: TriggerEvent,
    source: Literal["rule", "sweep"],
    result: VerifierResult | None,
    status: str,
) -> AlertRecord:
    return AlertRecord(
        source=source,
        trigger=event.trigger.value,
        t_fire=event.t_fire,
        t_peak=event.t_peak,
        ai_status=status,
        collision_visible=result.collision_visible if result else None,
        verifier_available=bool(result and result.available),
    )


async def replay_clip(
    frames: Iterable[SampledFrame],
    *,
    camera: Camera,
    settings: VisionSettings,
    detector: Detector,
    tracker: Tracker,
    ring: PacketRing,
    verifier: AiVerifier | None = None,
) -> ReplayResult:
    """Run ``frames`` (a fresh ``iter_frames`` over the clip, filling ``ring``) and score nothing:
    the alerts are returned for ``evaluation.evaluate``."""
    sink = CollectingSink()
    state = WorkerState(camera.id, settings, lambda: 0, detector.model_id)
    pipeline = build_pipeline(
        camera, settings, detector, tracker, state, publisher=None, sink=sink, ring=ring
    )
    result = ReplayResult(0.0, [])
    sweeps: list[tuple[float, list[Packet], StreamInfo]] = []
    first_pts: float | None = None
    last_pts = 0.0
    last_sweep: float | None = None
    for frame in frames:
        frame = dataclasses.replace(frame, captured_at=VIRTUAL_EPOCH + frame.pts_s)
        first_pts = frame.pts_s if first_pts is None else first_pts
        last_pts = frame.pts_s
        started = time.perf_counter()
        pipeline.process(frame)
        result.frame_ms.append((time.perf_counter() - started) * 1000)
        due = last_sweep is None or frame.pts_s - last_sweep >= settings.sweep_every_s
        if (
            settings.sweep_enabled
            and verifier is not None
            and due
            and ring.stream is not None
            and ring.duration_s() >= SWEEP_WINDOW_S / 2
        ):
            last_sweep = frame.pts_s
            sweeps.append((frame.pts_s, ring.snapshot(), ring.stream))
    result.duration_s = last_pts - (first_pts or 0.0)

    thresholds = StatusThresholds(settings.status_confirmed, settings.status_probable)
    rule_walls: list[float] = []
    for item in sink.captured:
        verdict: VerifierResult | None = None
        status = item.candidate.ai_status.value
        if verifier is not None and settings.verify_candidates:
            started = time.perf_counter()
            verdict = await verifier.verify_event(
                item.packets, item.info, item.event.evidence_t, item.event.trigger
            )
            result.verify_ms.append((time.perf_counter() - started) * 1000)
            status = classify(rule_fired=True, verifier=verdict, thresholds=thresholds).value
        result.alerts.append(_record(item.event, "rule", verdict, status))
        rule_walls.append(item.event.fire_wall)

    if verifier is not None:
        await _sweep_alerts(result, sweeps, rule_walls, settings, verifier, thresholds)
    result.alerts.sort(key=lambda a: a.t_fire)
    return result


async def _sweep_alerts(
    result: ReplayResult,
    sweeps: list[tuple[float, list[Packet], StreamInfo]],
    rule_walls: list[float],
    settings: VisionSettings,
    verifier: AiVerifier,
    thresholds: StatusThresholds,
) -> None:
    tracker = SweepTracker(settings.sweep_yes_threshold)
    last_emit: float | None = None
    cooldown = settings.trigger_cooldown_s
    for end_s, packets, info in sweeps:
        started = time.perf_counter()
        verdict = await verifier.sweep(packets, info, end_s)
        result.sweep_ms.append((time.perf_counter() - started) * 1000)
        hits = tracker.record(verdict)
        if not hits:
            continue
        wall = VIRTUAL_EPOCH + end_s
        cooling = any(0 <= wall - w < cooldown for w in rule_walls) or (
            last_emit is not None and wall - last_emit < cooldown
        )
        if not should_emit(hits, cooling):
            continue
        last_emit = wall
        event = sweep_event(verdict, end_s, wall, hits)
        status = classify(
            rule_fired=False, verifier=verdict, consecutive_sweep_hits=hits, thresholds=thresholds
        )
        result.alerts.append(_record(event, "sweep", verdict, status.value))
