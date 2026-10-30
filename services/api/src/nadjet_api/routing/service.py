"""Resource recommendation: PostGIS KNN prefilter, OSRM road ETAs, then ranking rules."""

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.routing.ranking import (
    HospitalCandidate,
    apply_urban_multiplier,
    rank_hospitals,
)
from nadjet_api.routing.router import Point, Route, Router

KNN_CANDIDATES = 10

_SELECT_UNITS = """
SELECT u.id, u.callsign, u.agency, u.status, u.phone, u.simulated, u.facility_id,
       f.name AS facility_name, ST_Y(u.geom) AS lat, ST_X(u.geom) AS lon
FROM units u JOIN facilities f ON f.id = u.facility_id
WHERE u.status = 'available'
ORDER BY u.geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
LIMIT :k
"""

_SELECT_HOSPITALS = """
SELECT id, name, ready_state, capabilities, contact_sms, simulated, wilaya,
       ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM facilities
WHERE kind = 'hospital'
  AND (CAST(:need AS text) IS NULL OR capabilities ->> CAST(:need AS text) = 'true')
ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
LIMIT :k
"""


@dataclass(frozen=True)
class Ranked:
    record: dict[str, Any]
    eta_s: float
    distance_m: float
    route: Route | None = None


async def _rows(session: AsyncSession, sql: str, **params: Any) -> list[dict[str, Any]]:
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def _with_routes(items: list[Ranked], leg: Any, router: Router) -> list[Ranked]:
    """Fetch the polyline for each ranked item; ``leg(record)`` gives (origin, destination)."""
    routes = await asyncio.gather(*(router.route(*leg(i.record)) for i in items))
    return [Ranked(i.record, i.eta_s, i.distance_m, r) for i, r in zip(items, routes, strict=True)]


def _point(record: dict[str, Any]) -> Point:
    return Point(record["lat"], record["lon"])


async def rank_units(
    session: AsyncSession, router: Router, scene: Point, *, limit: int, multiplier: float
) -> list[Ranked]:
    rows = await _rows(session, _SELECT_UNITS, lat=scene.lat, lon=scene.lon, k=KNN_CANDIDATES)
    if not rows:
        return []
    matrix = await router.table([_point(r) for r in rows], [scene])
    ranked = [
        Ranked(r, apply_urban_multiplier(leg.duration_s, multiplier), leg.distance_m)
        for r, [leg] in zip(rows, matrix, strict=True)
        if leg is not None
    ]
    ranked.sort(key=lambda i: i.eta_s)
    return await _with_routes(ranked[:limit], lambda r: (_point(r), scene), router)


async def rank_hospital_candidates(
    session: AsyncSession,
    router: Router,
    scene: Point,
    *,
    need: str | None,
    limit: int,
    multiplier: float,
) -> list[Ranked]:
    rows = await _rows(
        session, _SELECT_HOSPITALS, lat=scene.lat, lon=scene.lon, need=None, k=KNN_CANDIDATES
    )
    if need:  # a distant capable hospital must not be lost behind nearer, incapable ones
        capable = await _rows(
            session, _SELECT_HOSPITALS, lat=scene.lat, lon=scene.lon, need=need, k=KNN_CANDIDATES
        )
        rows += [r for r in capable if r["id"] not in {x["id"] for x in rows}]
    if not rows:
        return []
    [legs] = await router.table([scene], [_point(r) for r in rows])
    by_id: dict[str, Ranked] = {}
    candidates: list[HospitalCandidate] = []
    for row, leg in zip(rows, legs, strict=True):
        if leg is None:
            continue
        eta = apply_urban_multiplier(leg.duration_s, multiplier)
        by_id[row["id"]] = Ranked(row, eta, leg.distance_m)
        candidates.append(
            HospitalCandidate(
                id=row["id"],
                capable=bool(need) and bool(row["capabilities"].get(need)),
                ready=row["ready_state"] == "ready",
                eta_s=eta,
            )
        )
    ordered = [by_id[c.id] for c in rank_hospitals(candidates)][:limit]
    return await _with_routes(ordered, lambda r: (scene, _point(r)), router)
