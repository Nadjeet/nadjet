"""Fault state machine, stage latency, /metrics and health push (FR-CAM-005, US-13)."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from nadjet_vision.config import VisionSettings
from nadjet_vision.health import (
    FaultTracker,
    StageTimers,
    WorkerState,
    push_once,
    render_prometheus,
    serve_metrics,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_silence_over_ten_seconds_is_a_stall_when_the_stream_is_open() -> None:
    clock = Clock()
    faults = FaultTracker(stall_s=10, clock=clock)
    faults.set_connected(True)
    faults.frame_received()
    clock.now += 9.9
    assert faults.evaluate() is None
    clock.now += 0.2
    assert faults.evaluate() == "stall"


def test_silence_without_a_stream_is_a_disconnect_and_the_reason_sticks() -> None:
    clock = Clock()
    faults = FaultTracker(stall_s=10, clock=clock)
    faults.set_connected(False)
    clock.now += 11
    assert faults.evaluate() == "disconnect"
    faults.set_connected(True)  # reconnected but still no frame: still faulty, same reason
    assert faults.evaluate() == "disconnect"


def test_a_frame_clears_the_fault() -> None:
    clock = Clock()
    faults = FaultTracker(stall_s=10, clock=clock)
    clock.now += 20
    assert faults.evaluate() == "disconnect"
    faults.frame_received()
    assert faults.evaluate() is None
    clock.now += 5
    assert faults.evaluate() is None


def test_startup_silence_counts_from_start() -> None:
    clock = Clock()
    faults = FaultTracker(stall_s=10, clock=clock)
    assert faults.evaluate() is None
    clock.now += 10.5
    assert faults.evaluate() is not None


def test_stage_latency_is_the_median_and_empty_stages_are_none() -> None:
    timers = StageTimers()
    for ms in (10, 12, 100):  # one outlier
        timers.record("detect", ms)
    latency = timers.latency()
    assert latency.detect == 12
    assert latency.decode is None


def make_state(clock: Clock | None = None) -> WorkerState:
    return WorkerState(
        "cam-a1-pk42", VisionSettings(), queue_depth=lambda: 1, detector="rf-detr-medium",
        clock=clock or Clock(),
    )  # fmt: skip


def test_report_carries_fps_latency_queue_and_detector() -> None:
    clock = Clock()
    state = make_state(clock)
    state.faults.set_connected(True)
    for _ in range(11):
        state.analysed()
        clock.now += 0.2
    state.timers.record("detect", 30.0)
    state.camera_moving = True
    report = state.report()
    assert report.fps == pytest.approx(5.0, abs=0.1)
    assert report.queue_depth == 1
    assert report.latency_ms.detect == 30.0
    assert report.camera_moving
    assert report.detector == "rf-detr-medium"
    assert not report.fault
    assert report.last_frame_at is not None


def test_prometheus_text_has_one_sample_per_metric() -> None:
    state = make_state()
    state.timers.record("detect", 31.5)
    text = render_prometheus(state.report())
    assert 'nadjet_camera_fps{camera="cam-a1-pk42"} 0.0' in text
    assert 'nadjet_stage_latency_ms{camera="cam-a1-pk42",stage="detect"} 31.5' in text
    assert 'stage="decode"' not in text  # no sample yet: omitted, not zero


async def test_metrics_endpoint_serves_prometheus_text() -> None:
    state = make_state()
    server = await serve_metrics(0, state.report, host="127.0.0.1")
    port = server.sockets[0].getsockname()[1]
    async with httpx.AsyncClient() as client:
        ok = await client.get(f"http://127.0.0.1:{port}/metrics")
        missing = await client.get(f"http://127.0.0.1:{port}/other")
    server.close()
    await server.wait_closed()
    assert ok.status_code == 200
    assert "nadjet_camera_connected" in ok.text
    assert missing.status_code == 404


async def test_push_posts_the_report_with_the_service_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"status": "online", "transition": None})

    settings = VisionSettings(ingest_token=SecretStr("tok"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await push_once(client, settings, make_state().report())
    assert str(seen[0].url) == "http://127.0.0.1:8080/internal/camera-health"
    assert seen[0].headers["authorization"] == "Bearer tok"
    assert b'"camera_id":"cam-a1-pk42"' in seen[0].content


async def test_push_failure_is_reported_not_raised() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    settings = VisionSettings(ingest_token=SecretStr("tok"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        assert not await push_once(client, settings, make_state().report())
    async with httpx.AsyncClient() as client:
        assert not await push_once(client, VisionSettings(), make_state().report())  # no token
    await asyncio.sleep(0)
