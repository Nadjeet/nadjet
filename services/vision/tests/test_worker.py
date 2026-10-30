import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from nadjet_vision import worker
from nadjet_vision.cli import main
from nadjet_vision.config import VisionSettings

ROOT = Path(__file__).resolve().parents[3]


def test_rtsp_url_joins_base_and_camera_id() -> None:
    assert worker.rtsp_url("rtsp://127.0.0.1:18554/", "cam-a1-pk42") == (
        "rtsp://127.0.0.1:18554/cam-a1-pk42"
    )


def test_camera_ids_come_from_the_catalogue() -> None:
    ids = worker.camera_ids(ROOT / "data" / "cameras.yaml")
    assert "cam-a1-pk42" in ids
    assert len(ids) == len(set(ids))


def test_backoff_doubles_up_to_thirty_seconds() -> None:
    value, seen = worker.BACKOFF_START_S, []
    for _ in range(7):
        seen.append(value)
        value = worker.next_backoff(value)
    assert seen == [1, 2, 4, 8, 16, 30, 30]


def test_fps_meter_measures_rate_and_forgets_old_frames() -> None:
    now = [0.0]
    meter = worker.FpsMeter(window_s=5.0, clock=lambda: now[0])
    assert meter.fps() == 0.0
    for _ in range(11):  # 11 frames over 1 s -> 10 fps
        meter.tick()
        now[0] += 0.1
    now[0] -= 0.1
    assert meter.fps() == pytest.approx(10.0)
    now[0] += 60
    assert meter.fps() == 0.0


async def test_check_api_ok_and_unreachable() -> None:
    settings = VisionSettings()
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"}))
    assert await worker.check_api(settings, transport=ok)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert not await worker.check_api(settings, transport=httpx.MockTransport(down))


async def test_run_camera_logs_fps_and_reconnects_after_error(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "BACKOFF_START_S", 0.01)
    stop = asyncio.Event()
    calls: list[str] = []

    def frames(url: str, should_stop: Callable[[], bool]) -> Iterator[None]:
        calls.append(url)
        if len(calls) == 1:
            raise OSError("connection refused")
        for _ in range(50):
            yield None
        stop.set()

    caplog.set_level("INFO", logger="nadjet_vision.worker")
    settings = VisionSettings(rtsp_base="rtsp://127.0.0.1:18554")
    await asyncio.wait_for(
        worker.run_camera("cam-a1-pk42", settings, stop, frames=frames, report_every_s=0), 5
    )
    assert calls == ["rtsp://127.0.0.1:18554/cam-a1-pk42"] * 2
    assert "stream error" in caplog.text
    assert "retry in" in caplog.text
    assert "camera=cam-a1-pk42 fps=" in caplog.text


def test_camera_command_requires_a_target() -> None:
    with pytest.raises(SystemExit):
        main(["camera"])


def test_read_frames_sets_a_socket_timeout_ffmpeg_understands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frozen camera must raise, not block: `stimeout` is ignored by FFmpeg >= 5."""
    import sys
    import types

    opened: dict[str, object] = {}

    class Container:
        def __enter__(self) -> "Container":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def decode(self, video: int) -> Iterator[object]:
            return iter([object()])

    def fake_open(url: str, **kwargs: object) -> Container:
        opened.update(kwargs, url=url)
        return Container()

    monkeypatch.setitem(sys.modules, "av", types.SimpleNamespace(open=fake_open))
    assert list(worker.read_frames("rtsp://h/cam", lambda: False)) == [None]
    options = opened["options"]
    assert isinstance(options, dict)
    assert options["timeout"] == "5000000" and "stimeout" not in options
    assert opened["timeout"] == (5.0, 5.0)


async def test_backoff_resets_after_a_stream_that_delivered_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    real_wait_for = asyncio.wait_for

    async def record_wait(awaitable: object, timeout: float) -> object:  # noqa: ASYNC109
        waits.append(timeout)
        return await real_wait_for(awaitable, 0.001)  # type: ignore[arg-type]

    monkeypatch.setattr(asyncio, "wait_for", record_wait)
    stop = asyncio.Event()
    calls = 0

    def frames(url: str, should_stop: Callable[[], bool]) -> Iterator[None]:
        nonlocal calls
        calls += 1
        if calls in (1, 2):
            raise OSError("refused")  # back-off grows: 1 s, then 2 s
        if calls == 3:
            yield None
            raise OSError("dropped after frames")  # healthy stream: reset to 1 s
        stop.set()
        return

    settings = VisionSettings(rtsp_base="rtsp://127.0.0.1:18554")
    await real_wait_for(worker.run_camera("cam", settings, stop, frames=frames), 5)
    assert waits == [1.0, 2.0, 1.0]
