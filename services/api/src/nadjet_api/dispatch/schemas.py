"""Request and response models of the dispatch API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from nadjet_api.incidents.schemas import IncidentOut
from nadjet_api.routing.routes import RankedResource


class DispatchIn(BaseModel):
    unit_ids: list[str] = Field(min_length=1, max_length=10, description="Units to send")
    hospital_id: str = Field(description="The hospital that receives the patients")


class HospitalChangeIn(BaseModel):
    hospital_id: str


class IncidentRecommendations(BaseModel):
    """Ranked resources for one incident, with the need that filtered them."""

    unit_agencies: list[str] = Field(description="Agencies whose units can answer")
    hospital_need: str = Field(description="Capability hospitals are ranked by")
    urban_multiplier: float
    units: list[RankedResource]
    hospitals: list[RankedResource]


class DeliveryOut(BaseModel):
    channel: Literal["sms", "push", "telegram"]
    status: Literal["queued", "sent", "delivered", "failed"]
    attempts: int


class DispatchOut(BaseModel):
    id: uuid.UUID
    kind: Literal["unit", "hospital"]
    resource_id: str
    name: str
    agency: str | None
    simulated: bool
    lat: float = Field(description="Position of the unit or hospital")
    lon: float
    eta_s: float
    distance_m: float
    route_geojson: dict[str, Any] | None
    status: Literal["dispatched", "replaced"]
    dispatched_by: uuid.UUID
    at: datetime
    deliveries: list[DeliveryOut]


class DispatchResult(BaseModel):
    incident: IncidentOut
    dispatches: list[DispatchOut]
