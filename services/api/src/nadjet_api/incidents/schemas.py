"""Request and response models of the incident API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nadjet_api.incidents.lifecycle import IncidentStatus, RejectReason
from nadjet_api.incidents.priority import TriageTag
from nadjet_shared.events import GeoLocation, VerifierResult


class PriorityReason(BaseModel):
    rule: str
    level: int
    detail: str
    source: str = Field(description="Rule name, model id or 'triage' (FR-VIS-021)")


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    type: str
    status: IncidentStatus
    priority: int
    priority_reasons: list[PriorityReason]
    to_assess: bool
    mass_casualty: bool
    needs_extrication: bool
    lat: float
    lon: float
    road: str | None
    pk_km: float | None
    wilaya: str | None
    source: str
    camera_id: str | None
    event_time: datetime
    detected_at: datetime
    ai_status: str | None
    ai_signals: dict[str, float]
    verifier_result: VerifierResult
    quality_flags: list[str]
    people_reported: int | None
    trapped_reported: bool
    report_count: int
    reject_reason: RejectReason | None
    merged_into: uuid.UUID | None
    version: int
    created_at: datetime


class IncidentList(BaseModel):
    items: list[IncidentOut]
    total: int
    limit: int
    offset: int


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    actor_id: uuid.UUID | None
    payload: dict[str, Any]
    ts: datetime
    hash: str


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: Literal["clip", "keyframe", "photo"]
    content_type: str
    size_bytes: int
    sha256: str
    start_ts: datetime | None
    end_ts: datetime | None
    created_at: datetime


class CasualtyIn(BaseModel):
    triage_tag: TriageTag
    avpu: Literal["A", "V", "P", "U"] | None = None
    resp_rate: int | None = Field(default=None, ge=0, le=120)
    pulse: int | None = Field(default=None, ge=0, le=300)
    spo2: int | None = Field(default=None, ge=0, le=100)
    bleeding: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)
    source: Literal["app", "sms"] = "app"


class CasualtyOut(CasualtyIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reported_by: uuid.UUID | None
    at: datetime


class IncidentDetail(IncidentOut):
    events: list[IncidentEventOut]
    evidence: list[EvidenceOut]
    casualties: list[CasualtyOut]


class ManualIncidentIn(BaseModel):
    """Operator-created incident from a phone call (FR-INC-007)."""

    location: GeoLocation
    event_time: datetime | None = Field(default=None, description="Defaults to now")
    vehicle_count: int | None = Field(default=None, ge=0, le=50)
    bus_involved: bool = False
    person_on_road: bool = False
    flames: bool = False
    smoke: bool = False
    overturned: bool = False
    stopped_in_lane: bool = False
    trapped: bool = False
    people_reported: int | None = Field(default=None, ge=0)


class RejectIn(BaseModel):
    reason: RejectReason


class StatusIn(BaseModel):
    status: Literal[
        IncidentStatus.DISPATCHED,
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.EN_ROUTE,
        IncidentStatus.ON_SCENE,
        IncidentStatus.TRANSPORTING,
        IncidentStatus.AT_HOSPITAL,
        IncidentStatus.CLOSED,
    ]


class IntegrityFailureOut(BaseModel):
    kind: Literal["event", "signature", "file"]
    ref: str
    detail: str


class IntegrityOut(BaseModel):
    status: Literal["valid", "invalid"]
    events_checked: int
    files_checked: int
    failures: list[IntegrityFailureOut]


class CandidateAccepted(BaseModel):
    stream_id: str
