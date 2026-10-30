"""Hospital pre-alerts, Ready/Divert and acknowledgement (FR-HSP-001/002, FR-NTF-006, E-10).

Like the other services, every function works in the caller's transaction and never commits;
the caller commits and announces the returned changes.
"""

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Scope
from nadjet_api.dispatch.service import HOSPITAL_OPEN, HospitalProposer, handle_hospital_divert
from nadjet_api.hospital.board import expected_arrival, victim_counts
from nadjet_api.hospital.schemas import (
    FacilityState,
    HospitalBoard,
    PreAlert,
    PreAlertUnit,
    VictimCounts,
    VictimOut,
)
from nadjet_api.incidents import service as incidents
from nadjet_api.incidents.lifecycle import IncidentStatus
from nadjet_api.incidents.models import Casualty, Incident, IncidentEvent
from nadjet_api.incidents.service import UPDATED, Change
from nadjet_api.incidents.signing import ChainSigner

ACK_EVENT = "prealert_acknowledged"
INCOMING_VALUES = [s.value for s in HOSPITAL_OPEN]
ARRIVED_VALUES = [IncidentStatus.AT_HOSPITAL.value, IncidentStatus.CLOSED.value]


class HospitalError(Exception):
    """The action is not allowed in the current state (HTTP 409)."""


async def _rows(session: AsyncSession, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in (await session.execute(text(sql), params)).mappings()]


async def get_facility(session: AsyncSession, facility_id: str) -> FacilityState | None:
    rows = await _rows(
        session,
        "SELECT id, name, ready_state, simulated FROM facilities "
        "WHERE id = :id AND kind = 'hospital'",
        id=facility_id,
    )
    return FacilityState(**rows[0]) if rows else None


# ---------------------------------------------------------------- the board

_DISPATCHES = """
SELECT d.incident_id, d.eta_s, d.distance_m, d.at,
       d.at >= (date_trunc('day', now() AT TIME ZONE 'Africa/Algiers')
                AT TIME ZONE 'Africa/Algiers') AS today
FROM dispatches d
WHERE d.hospital_id = :f AND d.status = 'dispatched'
"""
_UNITS = """
SELECT d.incident_id, u.callsign, u.agency, u.simulated
FROM dispatches d JOIN units u ON u.id = d.unit_id
WHERE d.incident_id = ANY(:ids) AND d.status = 'dispatched'
ORDER BY u.callsign
"""


async def board(session: AsyncSession, facility: FacilityState) -> HospitalBoard:
    """Incoming pre-alerts and today's arrivals for ``facility`` (FR-HSP-001)."""
    dispatches = {r["incident_id"]: r for r in await _rows(session, _DISPATCHES, f=facility.id)}
    ids = list(dispatches)
    if not ids:
        return HospitalBoard(facility=facility, incoming=[], history=[])

    found = await session.scalars(
        select(Incident).where(Incident.id.in_(ids)).execution_options(populate_existing=True)
    )
    by_id = {i.id: i for i in found}
    casualties: dict[uuid.UUID, list[Casualty]] = {}
    for casualty in await session.scalars(
        select(Casualty).where(Casualty.incident_id.in_(ids)).order_by(Casualty.at)
    ):
        casualties.setdefault(casualty.incident_id, []).append(casualty)
    units: dict[uuid.UUID, list[PreAlertUnit]] = {}
    for row in await _rows(session, _UNITS, ids=ids):
        units.setdefault(row["incident_id"], []).append(
            PreAlertUnit(callsign=row["callsign"], agency=row["agency"], simulated=row["simulated"])
        )
    acknowledged: dict[uuid.UUID, tuple[Any, str]] = {}
    acks = await session.execute(
        select(IncidentEvent, User.display_name)
        .outerjoin(User, User.id == IncidentEvent.actor_id)
        .where(IncidentEvent.incident_id.in_(ids), IncidentEvent.kind == ACK_EVENT)
        .order_by(IncidentEvent.id)
    )
    for event, name in acks:
        if event.payload.get("facility_id") == facility.id:
            acknowledged.setdefault(event.incident_id, (event.ts, name or ""))

    incoming: list[PreAlert] = []
    history: list[PreAlert] = []
    for incident_id, dispatch in dispatches.items():
        incident = by_id.get(incident_id)
        if incident is None:
            continue
        victims = casualties.get(incident_id, [])
        ack = acknowledged.get(incident_id)
        item = PreAlert(
            incident_id=incident.id,
            short_code=incident.short_code,
            status=IncidentStatus(incident.status),
            priority=incident.priority,
            type=incident.type,
            mass_casualty=incident.mass_casualty,
            needs_extrication=incident.needs_extrication,
            trapped_reported=incident.trapped_reported,
            people_reported=incident.people_reported,
            road=incident.road,
            pk_km=incident.pk_km,
            wilaya=incident.wilaya,
            location_text=incident.location_text,
            dispatched_at=dispatch["at"],
            eta_s=dispatch["eta_s"],
            distance_m=dispatch["distance_m"],
            expected_arrival_at=expected_arrival(dispatch["at"], dispatch["eta_s"]),
            units=units.get(incident_id, []),
            victims=VictimCounts(**victim_counts(c.triage_tag for c in victims)),
            casualties=[VictimOut.model_validate(c, from_attributes=True) for c in victims],
            acknowledged_at=ack[0] if ack else None,
            acknowledged_by=(ack[1] or None) if ack else None,
        )
        if incident.status in INCOMING_VALUES:
            incoming.append(item)
        elif incident.status in ARRIVED_VALUES and dispatch["today"]:
            history.append(item)
    incoming.sort(key=lambda a: (a.priority, a.expected_arrival_at))
    history.sort(key=lambda a: a.expected_arrival_at, reverse=True)
    return HospitalBoard(facility=facility, incoming=incoming, history=history)


# ---------------------------------------------------------------- Ready / Divert


async def set_readiness(
    session: AsyncSession,
    signer: ChainSigner,
    user: User,
    facility: FacilityState,
    state: str,
    propose: HospitalProposer | None,
    *,
    ip: str | None = None,
) -> tuple[FacilityState, list[Change]]:
    """Set the facility Ready or Divert (FR-HSP-002), the state hospital ranking reads.

    Every open incident that selected this hospital gets a ``hospital_response`` event; going to
    Divert also raises the E-10 alert with the next-ranked hospital. No change, no events.
    """
    if facility.ready_state == state:
        return facility, []
    await session.execute(
        text("UPDATE facilities SET ready_state = :s WHERE id = :id AND kind = 'hospital'"),
        {"s": state, "id": facility.id},
    )
    await audit(
        session,
        user,
        "facility.readiness",
        AuditTarget("facility", facility.id),
        {"from": facility.ready_state, "to": state},
        ip=ip,
    )
    changes: list[Change] = []
    affected = await _rows(
        session,
        "SELECT DISTINCT d.incident_id FROM dispatches d JOIN incidents i ON i.id = d.incident_id "
        "WHERE d.hospital_id = :f AND d.status = 'dispatched' AND i.status = ANY(:open)",
        f=facility.id,
        open=INCOMING_VALUES,
    )
    for row in affected:
        incident = await incidents.get_visible(
            session, row["incident_id"], Scope(unrestricted=True), lock=True
        )
        incident.version += 1
        await incidents.append_event(
            session,
            signer,
            incident,
            "hospital_response",
            user,
            {"facility_id": facility.id, "state": state},
        )
        changes.append(incidents._change(UPDATED, incident))
    if state == "divert":
        changes += await handle_hospital_divert(session, signer, facility.id, propose)
    return facility.model_copy(update={"ready_state": state}), changes


# ---------------------------------------------------------------- acknowledgement


async def acknowledge(
    session: AsyncSession,
    signer: ChainSigner,
    user: User,
    facility_id: str,
    incident_id: uuid.UUID,
) -> Change | None:
    """The hospital confirms it saw the pre-alert; ``None`` when it already had.

    Raises ``incidents.NotFoundError`` when the incident was not assigned to this hospital.
    """
    incident = await incidents.get_visible(
        session, incident_id, Scope(facility_id=facility_id), lock=True
    )
    if incident.status not in INCOMING_VALUES:
        raise HospitalError(f"a {incident.status} incident cannot be acknowledged")
    known = await session.scalars(
        select(IncidentEvent.payload).where(
            IncidentEvent.incident_id == incident.id, IncidentEvent.kind == ACK_EVENT
        )
    )
    if any(p.get("facility_id") == facility_id for p in known):
        return None
    incident.version += 1
    await incidents.append_event(
        session, signer, incident, ACK_EVENT, user, {"facility_id": facility_id}
    )
    return incidents._change(UPDATED, incident)
