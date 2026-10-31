"""Idempotent import of facilities, capabilities and units from the CSV seed files.

``facilities.csv`` comes from the one-off Overpass export (``scripts/osm/export_facilities.py``);
capabilities, contacts and units are simulated on real OSM locations and flagged ``simulated``
(PRD A-02).
"""

import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.roles import Agency


class FacilitySeed(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    kind: Literal["hospital", "civil_protection", "gendarmerie", "police"]
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    wilaya: str | None = None
    contact_sms: str | None = None
    simulated: bool = True


class CapabilitySeed(BaseModel):
    facility_id: str
    capability: str
    ready_state: Literal["ready", "divert"] = "ready"


class UnitSeed(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    facility_id: str
    agency: Agency
    callsign: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    phone: str | None = None
    simulated: bool = True


def _read[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            model.model_validate({k: v for k, v in row.items() if v != ""})
            for row in csv.DictReader(fh)
        ]


def load_facilities(path: Path) -> list[FacilitySeed]:
    return _read(path, FacilitySeed)


def load_capabilities(path: Path) -> list[CapabilitySeed]:
    return _read(path, CapabilitySeed)


def load_units(path: Path) -> list[UnitSeed]:
    return _read(path, UnitSeed)


_UPSERT_FACILITY = text("""
INSERT INTO facilities (id, kind, name, geom, wilaya, contact_sms, simulated)
VALUES (:id, :kind, :name, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :wilaya, :contact_sms,
        :simulated)
ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, name = EXCLUDED.name, geom = EXCLUDED.geom,
  wilaya = EXCLUDED.wilaya, contact_sms = EXCLUDED.contact_sms, simulated = EXCLUDED.simulated
""")

_UPSERT_CAPABILITY = text("""
UPDATE facilities SET capabilities = capabilities || jsonb_build_object(CAST(:cap AS text), true),
  ready_state = :ready_state WHERE id = :facility_id
""")

_UPSERT_UNIT = text("""
INSERT INTO units (id, facility_id, agency, callsign, geom, phone, simulated)
VALUES (:id, :facility_id, :agency, :callsign, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :phone,
        :simulated)
ON CONFLICT (id) DO UPDATE SET facility_id = EXCLUDED.facility_id, agency = EXCLUDED.agency,
  callsign = EXCLUDED.callsign, geom = EXCLUDED.geom, phone = EXCLUDED.phone,
  simulated = EXCLUDED.simulated
""")


async def seed_geo(
    session: AsyncSession,
    facilities: list[FacilitySeed],
    capabilities: list[CapabilitySeed],
    units: list[UnitSeed],
) -> tuple[int, int, int]:
    """Upsert everything in one transaction. Returns (facilities, capabilities, units)."""
    known = {f.id for f in facilities}
    missing = {c.facility_id for c in capabilities} | {u.facility_id for u in units}
    missing -= known
    if missing:
        raise ValueError(f"unknown facility ids in seed files: {sorted(missing)}")
    for f in facilities:
        await session.execute(_UPSERT_FACILITY, f.model_dump())
    for c in capabilities:
        await session.execute(
            _UPSERT_CAPABILITY,
            {"cap": c.capability, "ready_state": c.ready_state, "facility_id": c.facility_id},
        )
    for u in units:
        await session.execute(_UPSERT_UNIT, {**u.model_dump(), "agency": u.agency.value})
    await session.commit()
    return len(facilities), len(capabilities), len(units)
