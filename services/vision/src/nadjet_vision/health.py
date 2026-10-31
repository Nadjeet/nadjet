"""Worker health: stage latencies, fault state machine, ``/metrics`` and the push loop.

A camera is faulty when no frame arrived for ``stall_s`` (10 s, doc 11 §9): ``disconnect`` if
the stream is not open at that moment, ``stall`` if it is open but silent. The reason is kept
until a frame arrives again (FR-CAM-005).
"""

import asyncio
import logging
import statistics
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from nadjet_shared.health import CameraHealthReport, FaultReason, StageLatencyMs
from nadjet_vision.config import VisionSettings
from nadjet_vision.worker import FpsMeter

log = logging.getLogger("nadjet_vision.health")

STAGES = ("decode", "detect", "track", "annotate")


class StageTimers:
    """Median latency per pipeline stage over the last ``size`` frames."""

    def __init__(self, size: int = 50) -> None:
        self._samples: dict[str, deque[float]] = {s: deque(maxlen=size) for s in STAGES}

    def record(self, stage: str, ms: float) -> None:
        self._samples[stage].append(ms)

    def latency(self) -> StageLatencyMs:
        values = {s: (statistics.median(v) if v else None) for s, v in self._samples.items()}
        return StageLatencyMs(**values)


class FaultTracker:
    def __init__(self, stall_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._stall_s = stall_s
        self._clock = clock
        self._last_frame = clock()  # silence counts from start-up
        self._connected = False
        self._reason: FaultReason | None = None

    def frame_received(self) -> None:
        self._last_frame = self._clock()
        self._reason = None

    def set_connected(self, connected: bool) -> None:
        self._connected = connected

    @property
    def connected(self) -> bool:
        return self._connected

    def evaluate(self) -> FaultReason | None:
        """Current fault reason, or ``None`` when healthy. Sticky until the next frame."""
        if self._reason is None and self._clock() - self._last_frame > self._stall_s:
            self._reason = "stall" if self._connected else "disconnect"
        return self._reason


class WorkerState:
    """Everything the health report and ``/metrics`` need, updated by the pipeline."""

    def __init__(
        self,
        camera_id: str,
        settings: VisionSettings,
        queue_depth: Callable[[], int],
        detector: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.camera_id = camera_id
        self.timers = StageTimers()
        self.fps = FpsMeter(clock=clock)
        self.faults = FaultTracker(settings.stall_s, clock)
        self.camera_moving = False
        self.last_frame_at: datetime | None = None
        self.detector = detector
        self._queue_depth = queue_depth

    def analysed(self) -> None:
        self.fps.tick()
        self.faults.frame_received()
        self.last_frame_at = datetime.now(UTC)

    def report(self) -> CameraHealthReport:
        reason = self.faults.evaluate()
        return CameraHealthReport(
            camera_id=self.camera_id,
            at=datetime.now(UTC),
            connected=self.faults.connected,
            fps=round(self.fps.fps(), 2),
            queue_depth=self._queue_depth(),
            last_frame_at=self.last_frame_at,
            latency_ms=self.timers.latency(),
            camera_moving=self.camera_moving,
            fault=reason is not None,
            fault_reason=reason,
            detector=self.detector,
        )


def render_prometheus(report: CameraHealthReport) -> str:
    """Prometheus text exposition of one camera's report."""
    cam = f'camera="{report.camera_id}"'
    lines = [
        "# TYPE nadjet_camera_fps gauge",
        f"nadjet_camera_fps{{{cam}}} {report.fps}",
        "# TYPE nadjet_camera_connected gauge",
        f"nadjet_camera_connected{{{cam}}} {int(report.connected)}",
        "# TYPE nadjet_camera_fault gauge",
        f"nadjet_camera_fault{{{cam}}} {int(report.fault)}",
        "# TYPE nadjet_camera_moving gauge",
        f"nadjet_camera_moving{{{cam}}} {int(report.camera_moving)}",
        "# TYPE nadjet_queue_depth gauge",
        f"nadjet_queue_depth{{{cam}}} {report.queue_depth}",
        "# TYPE nadjet_stage_latency_ms gauge",
    ]
    for stage in STAGES:
        value = getattr(report.latency_ms, stage)
        if value is not None:
            lines.append(f'nadjet_stage_latency_ms{{{cam},stage="{stage}"}} {value}')
    return "\n".join(lines) + "\n"


async def serve_metrics(
    port: int,
    report: Callable[[], CameraHealthReport],
    host: str = "0.0.0.0",  # noqa: S104
) -> asyncio.Server:
    """Minimal HTTP server answering ``GET /metrics`` (no extra dependency)."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readline(), timeout=5)
            while (await asyncio.wait_for(reader.readline(), timeout=5)) not in (
                b"\r\n",
                b"\n",
                b"",
            ):
                pass
            if request.startswith(b"GET /metrics"):
                body = render_prometheus(report()).encode()
                head = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; version=0.0.4\r\n"
            else:
                body = b"not found\n"
                head = b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n"
            writer.write(
                head + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    return await asyncio.start_server(handle, host, port)


async def push_once(
    client: httpx.AsyncClient, settings: VisionSettings, report: CameraHealthReport
) -> bool:
    """POST one report to the API; a failure is logged, never raised."""
    if settings.ingest_token is None:
        log.warning("NADJET_INGEST_TOKEN is not set: health reports are not pushed")
        return False
    url = f"{str(settings.api_url).rstrip('/')}/internal/camera-health"
    headers = {"Authorization": f"Bearer {settings.ingest_token.get_secret_value()}"}
    try:
        response = await client.post(
            url,
            content=report.model_dump_json(),
            headers={**headers, "Content-Type": "application/json"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("health push failed: %s", exc)
        return False
    return True


async def push_loop(
    settings: VisionSettings,
    report: Callable[[], CameraHealthReport],
    stop: asyncio.Event,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Push every ``health_push_s``, and at once when the fault state changes.

    Checking each second keeps "stall > 10 s -> camera_fault" inside the 15 s budget (FR-CAM-005)
    instead of waiting up to one more push interval.
    """
    last_fault: bool | None = None
    last_push = float("-inf")
    loop = asyncio.get_running_loop()
    async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
        while not stop.is_set():
            try:
                current = report()
            except Exception:
                log.exception("building the health report failed")
            else:
                due = loop.time() - last_push >= settings.health_push_s
                if due or current.fault != last_fault:
                    await push_once(client, settings, current)
                    last_fault, last_push = current.fault, loop.time()
            try:
                await asyncio.wait_for(stop.wait(), timeout=min(1.0, settings.health_push_s))
            except TimeoutError:
                continue
