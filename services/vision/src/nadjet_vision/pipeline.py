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

from nadjet_shared.catalogue import Zones, load_catalogue
from nadjet_vision.annotate import AnnotatedPublisher, annotated_url, draw
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detector, load_detector
from nadjet_vision.health import WorkerState, push_loop, serve_metrics
from nadjet_vision.ingest import (
    BgrFrame,
    FrameSampler,
    LatestFrameQueue,
    PacketRing,
    SampledFrame,
    iter_frames,
)
from nadjet_vision.track import (
    ByteTrackTracker,
    CameraMotionDetector,
    Tracked,
    Tracker,
    TrackHistory,
    ZoneMembership,
    zone_membership,
)
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
    ) -> None:
        self.zones = zones
        self.detector = detector
        self.tracker = tracker
        self.state = state
        self.publisher = publisher
        self._draw = draw_frame
        self.history = history or TrackHistory()
        self.motion = motion or CameraMotionDetector()

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
        membership = {t.track_id: zone_membership(t.detection.anchor, self.zones) for t in tracked}
        moving = self.motion.update(frame.image)
        timers.record("track", (time.perf_counter() - started) * 1000)

        annotated: BgrFrame | None = None
        if self.publisher is not None:
            started = time.perf_counter()
            annotated = self._draw(frame.image, tracked, speeds, self.zones)
            self.publisher.write(annotated)
            timers.record("annotate", (time.perf_counter() - started) * 1000)

        self.state.camera_moving = moving
        self.state.analysed()
        return FrameResult(frame.pts_s, tracked, speeds, membership, moving, annotated)


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


async def run_worker(
    camera_id: str,
    settings: VisionSettings,
    stop: asyncio.Event,
    *,
    detector: Detector | None = None,
    tracker: Tracker | None = None,
    frames: Callable[[str, Callable[[], bool]], Iterator[Any]] | None = None,
    publisher: FramePublisher | None = None,
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
    pipeline = CameraPipeline(
        zones=camera.zones, detector=detector, tracker=tracker, state=state, publisher=publisher
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
