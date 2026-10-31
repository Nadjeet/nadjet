"""``GET /routing/recommendations`` (FR-DSP-001, FR-DSP-002), operator-facing."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.routing.router import Point, RouterUnavailableError
from nadjet_api.routing.service import Ranked, rank_hospital_candidates, rank_units

router = APIRouter(prefix="/routing", tags=["routing"])

Operator = Annotated[User, Depends(require_roles(Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN))]


class RankedResource(BaseModel):
    id: str
    name: str
    kind: Literal["unit", "hospital"]
    agency: str | None = None
    ready_state: str | None = None
    capabilities: dict[str, Any] | None = None
    contact: str | None = None
    simulated: bool
    lat: float
    lon: float
    eta_s: float
    distance_m: float
    route_geojson: dict[str, Any] | None
    source: str = "osrm"


class Recommendations(BaseModel):
    urban_multiplier: float
    units: list[RankedResource]
    hospitals: list[RankedResource]


def unit_resource(item: Ranked) -> RankedResource:
    r = item.record
    return RankedResource(
        id=r["id"],
        name=f"{r['callsign']} ({r['facility_name']})",
        kind="unit",
        agency=r["agency"],
        contact=r["phone"],
        simulated=r["simulated"],
        lat=r["lat"],
        lon=r["lon"],
        eta_s=round(item.eta_s, 1),
        distance_m=round(item.distance_m, 1),
        route_geojson=item.route.geometry if item.route else None,
    )


def hospital_resource(item: Ranked) -> RankedResource:
    r = item.record
    return RankedResource(
        id=r["id"],
        name=r["name"],
        kind="hospital",
        ready_state=r["ready_state"],
        capabilities=r["capabilities"],
        contact=r["contact_sms"],
        simulated=r["simulated"],
        lat=r["lat"],
        lon=r["lon"],
        eta_s=round(item.eta_s, 1),
        distance_m=round(item.distance_m, 1),
        route_geojson=item.route.geometry if item.route else None,
    )


@router.get(
    "/recommendations",
    responses={503: {"description": "Routing service unavailable"}},
)
async def recommendations(
    request: Request,
    _user: Operator,
    session: Annotated[AsyncSession, Depends(get_session)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    kind: Annotated[Literal["unit", "hospital", "all"], Query()] = "all",
    need: Annotated[
        str | None, Query(description="Required hospital capability, e.g. trauma")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> Recommendations:
    """Rank units and hospitals near a point by road ETA; hospitals by capability, state, ETA."""
    road_router = getattr(request.app.state, "router", None)
    if road_router is None:
        raise HTTPException(503, "Routing service unavailable")
    settings: Settings = request.app.state.settings
    scene = Point(lat, lon)
    mult = settings.routing_urban_multiplier
    try:
        units = (
            await rank_units(session, road_router, scene, limit=limit, multiplier=mult)
            if kind in ("unit", "all")
            else []
        )
        hospitals = (
            await rank_hospital_candidates(
                session, road_router, scene, need=need, limit=limit, multiplier=mult
            )
            if kind in ("hospital", "all")
            else []
        )
    except RouterUnavailableError as exc:
        raise HTTPException(503, f"Routing service unavailable: {exc}") from exc
    return Recommendations(
        urban_multiplier=mult,
        units=[unit_resource(u) for u in units],
        hospitals=[hospital_resource(h) for h in hospitals],
    )
