"""Process model: one worker process per camera; a crash never touches the others (NFR-REL-001)."""

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Protocol

from nadjet_vision.config import VisionSettings

log = logging.getLogger("nadjet_vision.supervisor")

RESTART_MIN_S = 1.0
RESTART_MAX_S = 30.0
HEALTHY_AFTER_S = 60.0  # a process that ran this long is restarted at the shortest back-off


class Process(Protocol):
    async def wait(self) -> int: ...
    def terminate(self) -> None: ...


Spawn = Callable[[str, int | None], Awaitable[Process]]


def restart_delay(uptime_s: float, previous_s: float) -> float:
    """Back-off before restarting a worker: 1 s doubling to 30 s, reset after a long run."""
    if uptime_s >= HEALTHY_AFTER_S:
        return RESTART_MIN_S
    return min(max(previous_s * 2, RESTART_MIN_S), RESTART_MAX_S)


def worker_command(camera_id: str, metrics_port: int | None) -> list[str]:
    command = [sys.executable, "-m", "nadjet_vision.cli", "camera", "--id", camera_id, "--inline"]
    if metrics_port is not None:
        command += ["--metrics-port", str(metrics_port)]
    return command


async def spawn_process(camera_id: str, metrics_port: int | None) -> Process:
    return await asyncio.create_subprocess_exec(*worker_command(camera_id, metrics_port))


async def supervise_camera(
    camera_id: str,
    metrics_port: int | None,
    stop: asyncio.Event,
    spawn: Spawn = spawn_process,
) -> None:
    """Keep one camera process alive until ``stop``."""
    delay = RESTART_MIN_S / 2
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        started = loop.time()
        process = await spawn(camera_id, metrics_port)
        log.info("camera=%s worker started", camera_id)
        waiter = asyncio.ensure_future(process.wait())
        stopper = asyncio.ensure_future(stop.wait())
        await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if stop.is_set():
            process.terminate()
            await waiter
            stopper.cancel()
            return
        stopper.cancel()
        code = waiter.result()
        delay = restart_delay(loop.time() - started, delay)
        log.warning("camera=%s worker exited with %s; restart in %.0fs", camera_id, code, delay)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            continue


async def supervise(
    camera_ids: list[str],
    settings: VisionSettings,
    stop: asyncio.Event,
    spawn: Spawn = spawn_process,
) -> int:
    """Run every camera in its own process; ``stop`` ends them all."""
    tasks = [
        asyncio.create_task(
            supervise_camera(camera_id, settings.metrics_port_base + index, stop, spawn)
        )
        for index, camera_id in enumerate(camera_ids)
    ]
    await asyncio.gather(*tasks)
    return 0
