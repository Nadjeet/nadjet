"""``GET /map/resources``: facilities and units for the operator map (FR-MAP-001)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.db import get_session

router = APIRouter(prefix="/map", tags=["map"])

Viewer = Annotated[
    User, Depends(require_roles(Role.OPERATOR, Role.SUPERVISOR, Role.AUDITOR, Role.ADMIN))
]

_FACILITIES = """
SELECT id, kind, name, wilaya, ready_state, simulated, ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM facilities ORDER BY id
"""
_UNITS = """
SELECT id, callsign, agency, status, simulated, ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM units ORDER BY id
"""


class MapFacility(BaseModel):
    id: str
    kind: Literal["hospital", "civil_protection", "gendarmerie", "police"]
    name: str
    wilaya: str | None
    ready_state: Literal["ready", "divert"]
    simulated: bool
    lat: float
    lon: float


class MapUnit(BaseModel):
    id: str
    callsign: str
    agency: Literal["civil_protection", "gendarmerie", "police", "samu"]
    status: Literal["available", "dispatched", "busy", "offline"]
    simulated: bool
    lat: float
    lon: float


class MapResources(BaseModel):
    facilities: list[MapFacility]
    units: list[MapUnit]


@router.get("/resources")
async def map_resources(
    _user: Viewer, session: Annotated[AsyncSession, Depends(get_session)]
) -> MapResources:
    """Every facility and unit with its position; ``simulated`` ones must be labelled."""
    facilities = (await session.execute(text(_FACILITIES))).mappings().all()
    units = (await session.execute(text(_UNITS))).mappings().all()
    return MapResources(
        facilities=[MapFacility(**row) for row in facilities],
        units=[MapUnit(**row) for row in units],
    )
