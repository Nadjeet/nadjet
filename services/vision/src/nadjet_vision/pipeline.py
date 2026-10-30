"""One camera worker: ingest thread, analysis thread, annotated stream, health (FR-VIS-001..011).

``CameraPipeline.process`` is the per-frame logic with injected parts (detector, tracker,
publisher), so it is unit-tested with fakes; ``run_worker`` wires the real ones.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from nadjet_shared.catalogue import Camera, Zones, load_catalogue
from nadjet_vision.annotate import AnnotatedPublisher, annotated_url, draw
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detector, load_detector
from nadjet_vision.health import WorkerState, push_loop, serve_metrics
from nadjet_vision.inference import BrevVlmClient
from nadjet_vision.ingest import (
    BgrFrame,
    FrameSampler,
    LatestFrameQueue,
    PacketRing,
    SampledFrame,
    iter_frames,
)
from nadjet_vision.publish import (
    IncidentPublisher,
    IncidentSink,
    VerifyContext,
    build_candidate,
    candidate_key,
)
from nadjet_vision.status import StatusThresholds
from nadjet_vision.sweep import Sweeper, SweepTracker
from nadjet_vision.track import (
    ByteTrackTracker,
    CameraMotionDetector,
    Tracked,
    Tracker,
    TrackHistory,
    ZoneMembership,
    zone_membership,
)
from nadjet_vision.triggers import Observation, TriggerConfig, TriggerEngine, TriggerEvent
from nadjet_vision.verifier import AiVerifier
from nadjet_vision.worker import check_api, run_camera

log = logging.getLogger("nadjet_vision.pipeline")


class FramePublisher(Protocol):
    def write(self, frame: BgrFrame) -> bool: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class FrameResult:
    pts_s: float
    tracked: list[Tracked]
    speeds: dict[int, float | None]
    zones: dict[int, ZoneMembership]
    camera_moving: bool
    annotated: BgrFrame | None = field(default=None, repr=False)
    events: list[TriggerEvent] = field(default_factory=list)


@dataclass(frozen=True)
class _PendingEvidence:
    key: str
    event: TriggerEvent
    ready_pts: float  # stream time at which the ring holds the clip's post-roll


class CameraPipeline:
    def __init__(
        self,
        *,
        zones: Zones | None,
        detector: Detector,
        tracker: Tracker,
        state: WorkerState,
        publisher: FramePublisher | None = None,
        draw_frame: Callable[..., BgrFrame] = draw,
        history: TrackHistory | None = None,
        motion: CameraMotionDetector | None = None,
        camera: Camera | None = None,
        triggers: TriggerEngine | None = None,
        sink: IncidentSink | None = None,
        ring: PacketRing | None = None,
        evidence_after_s: float = 5.0,
        sweeper: Sweeper | None = None,
    ) -> None:
        self.zones = zones
        self.detector = detector
        self.tracker = tracker
        self.state = state
        self.publisher = publisher
        self._draw = draw_frame
        self.history = history or TrackHistory()
        self.motion = motion or CameraMotionDetector()
        self.camera = camera
        self.triggers = triggers
        self.sink = sink
        self.ring = ring
        self._evidence_after_s = evidence_after_s
        self.sweeper = sweeper
        self._pending: list[_PendingEvidence] = []
        self._last_pts: float | None = None

    def process(self, frame: SampledFrame) -> FrameResult:
        timers = self.state.timers
        timers.record("decode", frame.decode_ms)

        started = time.perf_counter()
        detections = self.detector.detect(frame.image)
        timers.record("detect", (time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        tracked = self.tracker.update(detections)
        self.history.update(frame.pts_s, tracked)
        speeds = {t.track_id: self.history.speed(t.track_id) for t in tracked}
        size = (frame.image.shape[1], frame.image.shape[0])
        membership = {
            t.track_id: zone_membership(t.detection.anchor, self.zones, size) for t in tracked
        }
        moving = self.motion.update(frame.image)
        events: list[TriggerEvent] = []
        if self.triggers is not None:
            events = self.triggers.update(
                Observation(frame.pts_s, frame.captured_at, tracked, speeds, membership, moving)
            )
            for event in events:
                self._publish(event)
        self._flush_evidence(frame.pts_s)
        if self.sweeper is not None and self.ring is not None and not moving:
            self.sweeper.maybe_start(frame.pts_s, frame.captured_at, self.ring)
        timers.record("track", (time.perf_counter() - started) * 1000)

        annotated: BgrFrame | None = None
        if self.publisher is not None:
            started = time.perf_counter()
            annotated = self._draw(frame.image, tracked, speeds, self.zones)
            self.publisher.write(annotated)
            timers.record("annotate", (time.perf_counter() - started) * 1000)

        self.state.camera_moving = moving
        self.state.analysed()
        return FrameResult(frame.pts_s, tracked, speeds, membership, moving, annotated, events)

    def _publish(self, event: TriggerEvent) -> None:
        """Post the candidate now; the clip follows once its post-roll is in the ring."""
        if self.sink is None or self.camera is None:
            return
        key = candidate_key(self.camera.id, event)
        context = VerifyContext(
            event,
            self.ring.snapshot() if self.ring else [],
            self.ring.stream if self.ring else None,
        )
        self.sink.publish_candidate(build_candidate(self.camera, event), key, context)
        self._pending.append(
            _PendingEvidence(key, event, event.evidence_t + self._evidence_after_s)
        )
        log.info(
            "camera=%s trigger=%s tracks=%s peak=%.2f signals=%s",
            self.camera.id,
            event.trigger.value,
            list(event.track_ids),
            event.t_peak,
            event.signals,
        )

    def _flush_evidence(self, pts_s: float) -> None:
        """Hand the ring to the sink for every event whose post-roll has arrived (or when the
        stream clock restarted: the ring is about to be replaced)."""
        restarted = self._last_pts is not None and pts_s < self._last_pts - 0.5
        self._last_pts = pts_s
        if self.sink is None or self.ring is None or not self._pending:
            return
        due = [p for p in self._pending if restarted or pts_s >= p.ready_pts]
        for item in due:
            self.sink.submit_evidence(item.key, item.event, self.ring.snapshot(), self.ring.stream)
        self._pending = [p for p in self._pending if p not in due]


def analysis_loop(
    pipeline: CameraPipeline, queue: LatestFrameQueue[SampledFrame], stop: Callable[[], bool]
) -> None:
    """Blocking analysis thread: latest frame wins; a failing frame never stops the camera."""
    while not stop():
        frame = queue.get(timeout=0.5)
        if frame is None:
            continue
        try:
            pipeline.process(frame)
        except Exception:
            log.exception("frame analysis failed")


def build_pipeline(
    camera: Camera,
    settings: VisionSettings,
    detector: Detector,
    tracker: Tracker,
    state: WorkerState,
    *,
    publisher: FramePublisher | None,
    sink: IncidentSink | None,
    ring: PacketRing,
    verifier: AiVerifier | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> CameraPipeline:
    """The camera's pipeline: thresholds are the doc 11 defaults, the settings' cooldown and the
    camera's own ``triggers`` overrides, in that order (FR-VIS-004, FR-VIS-010)."""
    thresholds = {"cooldown_s": settings.trigger_cooldown_s, **camera.triggers}
    engine = TriggerEngine(TriggerConfig.with_overrides(thresholds))
    sweeper: Sweeper | None = None
    if settings.sweep_enabled and verifier is not None and sink is not None and loop is not None:
        sweeper = Sweeper(
            camera,
            verifier,
            sink,
            loop,
            every_s=settings.sweep_every_s,
            cooldown_s=engine.config.cooldown_s,
            tracker=SweepTracker(settings.sweep_yes_threshold),
            thresholds=StatusThresholds(settings.status_confirmed, settings.status_probable),
            rule_cooling_down=engine.in_cooldown,
        )
    return CameraPipeline(
        zones=camera.zones,
        detector=detector,
        tracker=tracker,
        state=state,
        publisher=publisher,
        camera=camera,
        triggers=engine,
        sink=sink,
        ring=ring,
        evidence_after_s=settings.evidence_after_s,
        sweeper=sweeper,
    )


async def run_worker(
    camera_id: str,
    settings: VisionSettings,
    stop: asyncio.Event,
    *,
    detector: Detector | None = None,
    tracker: Tracker | None = None,
    frames: Callable[[str, Callable[[], bool]], Iterator[Any]] | None = None,
    publisher: FramePublisher | None = None,
    sink: IncidentSink | None = None,
    verifier: AiVerifier | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Run one camera until ``stop``: reconnecting reader, analysis thread, health, metrics."""
    camera = next(c for c in load_catalogue(settings.cameras_file).cameras if c.id == camera_id)
    detector = detector or load_detector(settings)
    tracker = tracker or ByteTrackTracker(settings.sample_fps, settings.detector_threshold)
    sampler = FrameSampler(settings.sample_fps)
    ring = PacketRing(settings.evidence_buffer_s)
    queue: LatestFrameQueue[SampledFrame] = LatestFrameQueue()
    state = WorkerState(camera_id, settings, lambda: len(queue), detector.model_id)
    if publisher is None and settings.annotate:
        url = annotated_url(settings.rtsp_base, camera_id)
        publisher = AnnotatedPublisher(url, settings.sample_fps, settings.annotated_encoder)
    vlm: BrevVlmClient | None = None
    if verifier is None and (settings.verify_candidates or settings.sweep_enabled):
        vlm = BrevVlmClient(settings)  # refuses any endpoint that is not Brev
        verifier = AiVerifier(
            vlm,
            settings.vlm_model,
            budget_s=settings.vlm_budget_s,
            backoff_s=settings.vlm_backoff_s,
        )
        try:
            await vlm.check()
        except Exception as exc:
            log.warning("AI unavailable: %s (candidates go out with the rules only)", exc)
    incidents: IncidentPublisher | None = None
    if sink is None and settings.publish_candidates:
        incidents = IncidentPublisher(
            settings,
            asyncio.get_running_loop(),
            transport=api_transport,
            verifier=verifier if settings.verify_candidates else None,
        )
        sink = incidents
    pipeline = build_pipeline(
        camera,
        settings,
        detector,
        tracker,
        state,
        publisher=publisher,
        sink=sink,
        ring=ring,
        verifier=verifier,
        loop=asyncio.get_running_loop(),
    )
    if frames is None:

        def frames(url: str, should_stop: Callable[[], bool]) -> Iterator[Any]:
            return iter_frames(
                url,
                should_stop,
                sampler=sampler,
                ring=ring,
                on_open=lambda: state.faults.set_connected(True),
            )

    loop = asyncio.get_running_loop()
    background = [
        asyncio.create_task(push_loop(settings, state.report, stop, api_transport)),
    ]
    server = None
    if settings.metrics_port is not None:
        server = await serve_metrics(settings.metrics_port, state.report)
    await check_api(settings)
    analysis = loop.run_in_executor(None, analysis_loop, pipeline, queue, stop.is_set)
    try:
        await run_camera(
            camera_id,
            settings,
            stop,
            frames=frames,
            on_frame=queue.put,
            on_state=state.faults.set_connected,
            report_every_s=5.0,
        )
    finally:
        stop.set()
        await asyncio.gather(*background, analysis, return_exceptions=True)
        if server is not None:
            server.close()
        if publisher is not None:
            publisher.close()
        if incidents is not None:
            await incidents.aclose()
        if vlm is not None:
            await vlm.aclose()
