"""Liveness and readiness probes.

``/health`` only says the process is up. ``/ready`` checks every dependency the API needs
(PostGIS and Redis) and returns 503 with per-dependency details when one is down.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

Probe = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str


def database_probe(engine: AsyncEngine) -> Probe:
    async def check() -> str:
        async with engine.connect() as conn:
            version = (await conn.execute(text("SELECT postgis_lib_version()"))).scalar_one()
        return f"postgis {version}"

    return check


def redis_probe(client: "Redis") -> Probe:
    async def check() -> str:
        pong = await client.ping()
        if not pong:
            raise ConnectionError("Redis did not answer PING")
        return "pong"

    return check


async def run_probes(probes: dict[str, Probe], timeout_s: float) -> list[ProbeResult]:
    async def one(name: str, probe: Probe) -> ProbeResult:
        try:
            detail = await asyncio.wait_for(probe(), timeout=timeout_s)
        except TimeoutError:
            return ProbeResult(name, False, f"timed out after {timeout_s}s")
        except Exception as exc:  # report any dependency failure instead of crashing
            return ProbeResult(name, False, f"{type(exc).__name__}: {exc}")
        return ProbeResult(name, True, detail)

    return list(await asyncio.gather(*(one(n, p) for n, p in probes.items())))
