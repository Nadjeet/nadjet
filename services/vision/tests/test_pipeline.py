"""Per-frame pipeline with a fake detector/tracker, annotation helpers, supervisor policy."""

import asyncio

import numpy as np
import pytest

from nadjet_vision.annotate import annotated_url, ffmpeg_command, format_label
from nadjet_vision.config import VisionSettings
from nadjet_vision.detect import Detection
from nadjet_vision.health import WorkerState
from nadjet_vision.ingest import LatestFrameQueue, SampledFrame
from nadjet_vision.pipeline import CameraPipeline, analysis_loop
from nadjet_vision.supervisor import (
    HEALTHY_AFTER_S,
    restart_delay,
    supervise_camera,
    worker_command,
)
from nadjet_vision.track import Tracked


class FakeDetector:
    model_id = "fake-detector"

    def __init__(self) -> None:
        self.calls = 0

    def detect(self, frame: np.ndarray) -> list[Detection]:  # type: ignore[type-arg]
        self.calls += 1
        x = 10.0 * self.calls
        return [Detection((x, 20, x + 40, 60), 3, "car", 0.9)]


class FakeTracker:
    def update(self, detections: list[Detection]) -> list[Tracked]:
        return [Tracked(7, d) for d in detections]


class FakePublisher:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []  # type: ignore[type-arg]
        self.closed = False

    def write(self, frame: np.ndarray) -> bool:  # type: ignore[type-arg]
        self.frames.append(frame)
        return True

    def close(self) -> None:
        self.closed = True


def frame(pts: float) -> SampledFrame:
    return SampledFrame(pts, np.zeros((90, 160, 3), dtype=np.uint8), decode_ms=4.0)


def make_pipeline(publisher: FakePublisher | None = None) -> CameraPipeline:
    state = WorkerState("cam-a1-pk42", VisionSettings(), lambda: 0, "fake-detector")
    return CameraPipeline(
        zones=None,
        detector=FakeDetector(),
        tracker=FakeTracker(),
        state=state,
        publisher=publisher,
        draw_frame=lambda image, tracked, speeds, zones: image,
    )


def test_process_tracks_measures_speed_and_records_every_stage() -> None:
    publisher = FakePublisher()
    pipeline = make_pipeline(publisher)
    results = [pipeline.process(frame(i * 0.2)) for i in range(4)]
    assert results[0].speeds[7] is None  # first sample: no speed yet
    assert results[-1].speeds[7] == pytest.approx(10 / 40 / 0.2)  # 10 px per 0.2 s, 40 px tall
    assert len(publisher.frames) == 4
    latency = pipeline.state.report().latency_ms
    assert None not in (latency.decode, latency.detect, latency.track, latency.annotate)
    assert pipeline.state.report().last_frame_at is not None


def test_without_a_publisher_nothing_is_annotated() -> None:
    pipeline = make_pipeline()
    result = pipeline.process(frame(0.0))
    assert result.annotated is None
    assert pipeline.state.report().latency_ms.annotate is None


def test_analysis_loop_survives_a_failing_frame() -> None:
    pipeline = make_pipeline()
    queue: LatestFrameQueue[SampledFrame] = LatestFrameQueue()
    boom = {"n": 0}
    real = pipeline.process

    def flaky(item: SampledFrame):  # type: ignore[no-untyped-def]
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("bad frame")
        return real(item)

    pipeline.process = flaky  # type: ignore[method-assign]
    queue.put(frame(0.0))
    queue.put(frame(0.2))
    handled = {"stop": False}

    def stopper() -> bool:
        handled["stop"] = handled["stop"] or boom["n"] >= 2
        return handled["stop"]

    analysis_loop(pipeline, queue, stopper)
    assert boom["n"] == 2
    assert pipeline.state.report().last_frame_at is not None


def test_annotated_stream_url_and_labels() -> None:
    assert annotated_url("rtsp://h:8554/", "cam-a1-pk42") == "rtsp://h:8554/cam-a1-pk42_ai"
    item = Tracked(7, Detection((0, 0, 1, 1), 3, "car", 0.9))
    assert format_label(item, 1.234) == "#7 car 1.2h/s"
    assert format_label(item, None) == "#7 car"


def test_ffmpeg_command_uses_nvenc_for_the_gpu_and_pipes_raw_frames() -> None:
    command = ffmpeg_command("rtsp://h/x_ai", 1280, 720, 5, "h264_nvenc")
    assert command[command.index("-c:v") + 1] == "h264_nvenc"
    assert "1280x720" in command
    assert command[-1] == "rtsp://h/x_ai"
    assert "p1" in command
    cpu = ffmpeg_command("rtsp://h/x_ai", 640, 360, 5, "libx264")
    assert "zerolatency" in cpu


def test_restart_backoff_doubles_to_thirty_seconds_and_resets_after_a_long_run() -> None:
    delay, seen = 0.5, []
    for _ in range(8):
        delay = restart_delay(1.0, delay)
        seen.append(delay)
    assert seen == [1, 2, 4, 8, 16, 30, 30, 30]
    assert restart_delay(HEALTHY_AFTER_S, 30) == 1.0


def test_worker_command_runs_one_inline_camera_with_its_metrics_port() -> None:
    command = worker_command("cam-a1-pk42", 9101)
    assert command[-6:] == ["camera", "--id", "cam-a1-pk42", "--inline", "--metrics-port", "9101"]


class FakeProcess:
    def __init__(self, exit_after: float | None) -> None:
        self._exit_after = exit_after
        self._done = asyncio.Event()
        self.terminated = False

    async def wait(self) -> int:
        if self._exit_after is not None:
            await asyncio.sleep(self._exit_after)
            return 1
        await self._done.wait()
        return 0

    def terminate(self) -> None:
        self.terminated = True
        self._done.set()


async def test_a_crashing_worker_is_restarted_and_stop_terminates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nadjet_vision.supervisor.restart_delay", lambda uptime, prev: 0.01)
    spawned: list[FakeProcess] = []

    async def spawn(camera_id: str, port: int | None) -> FakeProcess:
        process = FakeProcess(exit_after=0.01 if len(spawned) < 2 else None)
        spawned.append(process)
        return process

    stop = asyncio.Event()
    task = asyncio.create_task(supervise_camera("cam-a1-pk42", 9100, stop, spawn))
    for _ in range(200):
        if len(spawned) >= 3:
            break
        await asyncio.sleep(0.01)
    assert len(spawned) == 3  # two crashes, two restarts
    stop.set()
    await asyncio.wait_for(task, 2)
    assert spawned[-1].terminated


def test_dead_ffmpeg_backs_off_and_falls_back_from_nvenc(monkeypatch: pytest.MonkeyPatch) -> None:
    """No NVENC: ffmpeg dies at once. Never respawn on every frame; retry later with libx264."""
    import subprocess

    import numpy as np

    from nadjet_vision import annotate

    started: list[list[str]] = []

    class DeadFfmpeg:
        def __init__(self, command: list[str], **_: object) -> None:
            started.append(command)
            self.returncode = 1

            class Pipe:
                def write(self, _data: bytes) -> None:
                    raise BrokenPipeError

                def flush(self) -> None: ...

                def close(self) -> None: ...

            self.stdin = Pipe()

        def poll(self) -> int:
            return 1

        def terminate(self) -> None: ...

        def wait(self, timeout: float) -> int:
            return 1

    monkeypatch.setattr(subprocess, "Popen", DeadFfmpeg)
    now = [0.0]
    publisher = annotate.AnnotatedPublisher("rtsp://h/x_ai", 5, "h264_nvenc", clock=lambda: now[0])
    frame = np.zeros((36, 64, 3), dtype=np.uint8)
    assert not publisher.write(frame)
    for _ in range(20):  # 4 s of frames inside the 1 s back-off... no new ffmpeg
        assert not publisher.write(frame)
    assert len(started) == 1
    now[0] = 1.5  # back-off elapsed: one retry, now with libx264
    publisher.write(frame)
    assert len(started) == 2
    assert "libx264" in started[1]
