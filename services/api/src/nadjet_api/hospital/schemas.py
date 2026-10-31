"""Request and response models of the hospital API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nadjet_api.incidents.lifecycle import IncidentStatus


class FacilityState(BaseModel):
    id: str
    name: str
    ready_state: Literal["ready", "divert"]
    simulated: bool


class ReadinessIn(BaseModel):
    state: Literal["ready", "divert"]


class VictimCounts(BaseModel):
    red: int
    yellow: int
    green: int
    black: int
    total: int


class VictimOut(BaseModel):
    id: uuid.UUID
    triage_tag: Literal["red", "yellow", "green", "black"]
    avpu: Literal["A", "V", "P", "U"] | None
    resp_rate: int | None
    pulse: int | None
    spo2: int | None
    bleeding: bool | None
    notes: str | None
    at: datetime


class PreAlertUnit(BaseModel):
    callsign: str
    agency: str
    simulated: bool


class PreAlert(BaseModel):
    """One incident this hospital was selected for (FR-HSP-001)."""

    incident_id: uuid.UUID
    short_code: str
    status: IncidentStatus
    priority: int
    type: str
    mass_casualty: bool
    needs_extrication: bool
    trapped_reported: bool
    people_reported: int | None
    road: str | None
    pk_km: float | None
    wilaya: str | None
    location_text: str | None
    dispatched_at: datetime
    eta_s: float
    distance_m: float
    expected_arrival_at: datetime = Field(description="Dispatch time plus the stored road ETA")
    units: list[PreAlertUnit]
    victims: VictimCounts
    casualties: list[VictimOut]
    acknowledged_at: datetime | None
    acknowledged_by: str | None


class HospitalBoard(BaseModel):
    facility: FacilityState
    incoming: list[PreAlert] = Field(description="Hospital selected, patients not yet arrived")
    history: list[PreAlert] = Field(description="Arrivals of today (Algiers time)")
