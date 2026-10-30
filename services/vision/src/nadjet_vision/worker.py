"""Vision worker skeleton: connect to a camera stream and log the frame rate.

Detection and tracking come with the detection issue; this module only proves the runtime
(image, GPU host, tunnels) can read a stream and reach the API (PRD NFR-PERF-001).
"""

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx

from nadjet_shared.catalogue import load_catalogue
from nadjet_vision.config import VisionSettings

log = logging.getLogger("nadjet_vision.worker")

BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0  # doc 11: reconnect back-off 1 s to 30 s


def rtsp_url(base: str, camera_id: str) -> str:
    """Stream URL of one camera under an RTSP base URL."""
    return f"{base.rstrip('/')}/{camera_id}"


def camera_ids(cameras_file: Path) -> list[str]:
    """Ids of every camera in the catalogue."""
    return [camera.id for camera in load_catalogue(cameras_file).cameras]


def next_backoff(current: float) -> float:
    return min(current * 2, BACKOFF_MAX_S)


class FpsMeter:
    """Frames per second over a sliding time window."""

    def __init__(self, window_s: float = 5.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._window_s = window_s
        self._clock = clock
        self._ticks: deque[float] = deque()

    def tick(self) -> None:
        now = self._clock()
        self._ticks.append(now)
        self._trim(now)

    def fps(self) -> float:
        now = self._clock()
        self._trim(now)
        if len(self._ticks) < 2:
            return 0.0
        span = self._ticks[-1] - self._ticks[0]
        return (len(self._ticks) - 1) / span if span > 0 else 0.0

    def _trim(self, now: float) -> None:
        while self._ticks and now - self._ticks[0] > self._window_s:
            self._ticks.popleft()


async def check_api(
    settings: VisionSettings, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    """GET ``/health`` on the coordination API; log the outcome."""
    url = f"{str(settings.api_url).rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("API %s unreachable: %s", url, exc)
        return False
    log.info("API %s reachable", url)
    return True


def read_frames(url: str, stop: Callable[[], bool]) -> Iterator[None]:
    """Yield once per decoded video frame until ``stop()``; blocking, run in a thread."""
    import av  # gpu extra, imported lazily so local tools and tests do not need it

    with av.open(url, options={"rtsp_transport": "tcp", "stimeout": "5000000"}) as container:
        for _ in container.decode(video=0):
            if stop():
                return
            yield None


async def run_camera(
    camera_id: str,
    settings: VisionSettings,
    stop: asyncio.Event,
    *,
    frames: Callable[[str, Callable[[], bool]], Iterator[None]] = read_frames,
    report_every_s: float = 1.0,
) -> None:
    """Read one camera until ``stop`` is set, reconnecting with back-off, logging FPS."""
    url = rtsp_url(settings.rtsp_base, camera_id)
    meter = FpsMeter()
    backoff = BACKOFF_START_S
    loop = asyncio.get_running_loop()

    def consume() -> None:
        last_report = time.monotonic()
        for _ in frames(url, stop.is_set):
            meter.tick()
            if time.monotonic() - last_report >= report_every_s:
                last_report = time.monotonic()
                log.info("camera=%s fps=%.1f", camera_id, meter.fps())

    while not stop.is_set():
        log.info("camera=%s connecting %s", camera_id, url)
        try:
            await loop.run_in_executor(None, consume)
            backoff = BACKOFF_START_S
        except Exception as exc:  # stream errors are many; always reconnect
            log.warning("camera=%s stream error: %s (retry in %.0fs)", camera_id, exc, backoff)
        if stop.is_set():
            break
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=backoff)
        backoff = next_backoff(backoff)


async def run_cameras(
    ids: list[str], settings: VisionSettings, duration_s: float | None = None
) -> int:
    """Run every camera concurrently; stop after ``duration_s`` (None = until cancelled)."""
    stop = asyncio.Event()
    await check_api(settings)
    tasks = [asyncio.create_task(run_camera(i, settings, stop)) for i in ids]
    try:
        if duration_s is not None:
            await asyncio.sleep(duration_s)
            stop.set()
        await asyncio.gather(*tasks)
    finally:
        stop.set()
    return 0
