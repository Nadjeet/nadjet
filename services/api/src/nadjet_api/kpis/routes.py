"""``GET /kpis``: response-time KPIs from incident events (supervisor, admin; FR-KPI-001/002)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.db import get_session
from nadjet_api.incidents.lifecycle import IncidentStatus, RejectReason
from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_api.kpis import compute

router = APIRouter(prefix="/kpis", tags=["kpis"])

SupervisorUser = Annotated[User, Depends(require_roles(Role.SUPERVISOR, Role.ADMIN))]
MAX_INCIDENT_ROWS = 200


class MetricStats(BaseModel):
    n: int = Field(description="Incidents that reached both milestones")
    median_s: float | None
    p90_s: float | None


class IncidentKpi(BaseModel):
    id: uuid.UUID
    short_code: str
    status: str
    priority: int
    wilaya: str | None
    agencies: list[str]
    event_time: datetime
    durations: dict[str, float | None] = Field(
        description="Seconds per metric; null when the milestone was not reached"
    )


class KpiGroup(BaseModel):
    key: str
    incidents: int
    metrics: dict[str, MetricStats]


class CameraFalseAlarms(BaseModel):
    camera_id: str
    incidents: int = Field(description="Distinct incidents the camera raised (duplicates excluded)")
    false_positives: int = Field(description="Rejected by an operator as false positive")
    rate: float | None


class KpiReport(BaseModel):
    since: datetime
    until: datetime
    period: Literal["day", "week", "month"]
    overall: KpiGroup
    by_period: list[KpiGroup]
    by_agency: list[KpiGroup]
    by_wilaya: list[KpiGroup]
    false_alarms: list[CameraFalseAlarms]
    incidents: list[IncidentKpi] = Field(description=f"Newest {MAX_INCIDENT_ROWS} incidents")


Row = tuple[Incident, dict[str, float | None]]


def _group(key: str, rows: list[Row]) -> KpiGroup:
    metrics = compute.aggregate(d for _, d in rows)
    return KpiGroup(
        key=key,
        incidents=len(rows),
        metrics={
            name: MetricStats(n=s.n, median_s=s.median_s, p90_s=s.p90_s)
            for name, s in metrics.items()
        },
    )


@router.get("", responses={401: {"description": "Not authenticated"}, 403: {"description": "Role"}})
async def kpis(
    _user: SupervisorUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    since: Annotated[AwareDatetime | None, Query(description="Default: 30 days ago")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Default: now")] = None,
    period: Literal["day", "week", "month"] = "week",
) -> KpiReport:
    """Durations per incident and their median and p90 by period, agency and wilaya, plus the
    false-alarm rate per camera. Merged incidents are duplicates and are not counted."""
    until = until or datetime.now(UTC)
    since = since or until - timedelta(days=30)
    incidents = list(
        await session.scalars(
            select(Incident)
            .where(
                Incident.event_time >= since,
                Incident.event_time <= until,
                Incident.status != IncidentStatus.MERGED.value,
            )
            .order_by(Incident.event_time.desc())
        )
    )
    events: dict[uuid.UUID, list[tuple[str, dict[str, object], datetime]]] = {}
    if incidents:
        # ponytail: aggregated in memory, fine for pilot volumes; move to SQL past ~100k incidents.
        rows = await session.execute(
            select(
                IncidentEvent.incident_id,
                IncidentEvent.kind,
                IncidentEvent.payload,
                IncidentEvent.ts,
            ).where(
                IncidentEvent.incident_id.in_([i.id for i in incidents]),
                IncidentEvent.kind.in_(("created", "status_changed")),
            )
        )
        for incident_id, kind, payload, ts in rows:
            events.setdefault(incident_id, []).append((kind, payload, ts))
    measured = [
        (i, compute.durations(compute.milestones(i.event_time, events.get(i.id, []))))
        for i in incidents
    ]

    def groups(keys: Callable[[Row], list[str]]) -> list[KpiGroup]:
        return [_group(k, v) for k, v in sorted(compute.group_by(measured, keys).items())]

    per_camera: dict[str, list[Incident]] = {}
    for incident in incidents:
        if incident.camera_id and incident.reject_reason != RejectReason.DUPLICATE.value:
            per_camera.setdefault(incident.camera_id, []).append(incident)
    false_alarms = []
    for camera_id, raised in sorted(per_camera.items()):
        false_positives = sum(i.reject_reason == RejectReason.FALSE_POSITIVE.value for i in raised)
        false_alarms.append(
            CameraFalseAlarms(
                camera_id=camera_id,
                incidents=len(raised),
                false_positives=false_positives,
                rate=compute.false_alarm_rate(false_positives, len(raised)),
            )
        )
    return KpiReport(
        since=since,
        until=until,
        period=period,
        overall=_group("all", measured),
        by_period=groups(lambda m: [compute.period_key(m[0].event_time, period)]),
        by_agency=groups(lambda m: list(m[0].assigned_agencies)),
        by_wilaya=groups(lambda m: [m[0].wilaya or "-"]),
        false_alarms=false_alarms,
        incidents=[
            IncidentKpi(
                id=i.id,
                short_code=i.short_code,
                status=i.status,
                priority=i.priority,
                wilaya=i.wilaya,
                agencies=list(i.assigned_agencies),
                event_time=i.event_time,
                durations=d,
            )
            for i, d in measured[:MAX_INCIDENT_ROWS]
        ],
    )
