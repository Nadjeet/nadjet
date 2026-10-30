"""Road-network routing behind a small ``Router`` protocol (NFR-MAINT-002).

``OsrmRouter`` talks to the self-hosted OSRM service; tests use fakes. OSRM has no live traffic,
so durations are free-flow and the caller applies the urban multiplier.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class RouterUnavailableError(Exception):
    """The routing service cannot be reached or gave an unusable answer."""


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class Leg:
    duration_s: float
    distance_m: float


@dataclass(frozen=True)
class Route(Leg):
    geometry: dict[str, Any]  # GeoJSON LineString


class Router(Protocol):
    async def table(
        self, sources: Sequence[Point], destinations: Sequence[Point]
    ) -> list[list[Leg | None]]:
        """``result[i][j]``: leg sources[i] -> destinations[j], None when no road connects them."""
        ...

    async def route(self, origin: Point, destination: Point) -> Route | None:
        """Fastest route, or None when the points are not connected."""
        ...


def _coords(points: Sequence[Point]) -> str:
    return ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in points)


class OsrmRouter:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.get(f"{self._base}{path}", params=params)
        except httpx.HTTPError as exc:
            raise RouterUnavailableError(f"OSRM unreachable: {type(exc).__name__}") from exc
        body: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
        if response.status_code >= 500 or (response.status_code != 200 and not body):
            raise RouterUnavailableError(f"OSRM answered HTTP {response.status_code}")
        return body

    async def table(
        self, sources: Sequence[Point], destinations: Sequence[Point]
    ) -> list[list[Leg | None]]:
        points = [*sources, *destinations]
        n = len(sources)
        body = await self._get(
            f"/table/v1/driving/{_coords(points)}",
            {
                "sources": ";".join(map(str, range(n))),
                "destinations": ";".join(map(str, range(n, len(points)))),
                "annotations": "duration,distance",
            },
        )
        if body.get("code") != "Ok":
            raise RouterUnavailableError(f"OSRM table failed: {body.get('code')}")
        durations, distances = body["durations"], body["distances"]
        return [
            [
                None if d is None or m is None else Leg(float(d), float(m))
                for d, m in zip(d_row, m_row, strict=True)
            ]
            for d_row, m_row in zip(durations, distances, strict=True)
        ]

    async def route(self, origin: Point, destination: Point) -> Route | None:
        body = await self._get(
            f"/route/v1/driving/{_coords([origin, destination])}",
            {"overview": "full", "geometries": "geojson", "steps": "false"},
        )
        code = body.get("code")
        if code == "NoRoute":
            return None
        if code != "Ok" or not body.get("routes"):
            raise RouterUnavailableError(f"OSRM route failed: {code}")
        best = body["routes"][0]
        return Route(float(best["duration"]), float(best["distance"]), best["geometry"])
