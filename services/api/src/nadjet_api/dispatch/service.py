"""Dispatch: recommendations, one-action dispatch, hospital change, DIVERT handling.

FR-DSP-001..004, FR-NTF-001/006/007, FR-SEC-002, E-10. Like the other services, every function
works in the caller's transaction and never commits; the caller commits, announces ``changes``
and enqueues ``notifications``.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role, Scope
from nadjet_api.dispatch.models import Dispatch
from nadjet_api.dispatch.need import hospital_need, unit_agencies
from nadjet_api.dispatch.schemas import DeliveryOut, DispatchOut
from nadjet_api.incidents import service as incidents
from nadjet_api.incidents.lifecycle import IncidentStatus, check_transition
from nadjet_api.incidents.models import Incident
from nadjet_api.incidents.service import STATUS_CHANGED, UPDATED, Change
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.notifications import service as notifications
from nadjet_api.notifications.channels import SMS
from nadjet_api.notifications.grammar import normalize_phone
from nadjet_api.notifications.models import Notification
from nadjet_api.routing.ranking import apply_urban_multiplier
from nadjet_api.routing.router import Point, Route, Router, RouterUnavailableError
from nadjet_api.routing.service import Ranked, rank_hospital_candidates, rank_units

log = logging.getLogger(__name__)

#: Statuses in which the incident still has a hospital that can be changed or can divert.
HOSPITAL_OPEN = (
    IncidentStatus.DISPATCHED,
    IncidentStatus.ACKNOWLEDGED,
    IncidentStatus.EN_ROUTE,
    IncidentStatus.ON_SCENE,
    IncidentStatus.TRANSPORTING,
)


class DispatchError(Exception):
    """The dispatch is not allowed in the current state (HTTP 409)."""


class UnknownResourceError(Exception):
    """A unit or hospital id does not exist (HTTP 422)."""


@dataclass
class Outcome:
    changes: list[Change] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)


HospitalProposer = Callable[[Incident, str], Awaitable[dict[str, Any] | None]]


# ---------------------------------------------------------------- helpers


def scene_of(incident: Incident) -> Point:
    if incident.lat is None or incident.lon is None:
        raise DispatchError("the incident has no position yet (call-back pending)")
    return Point(incident.lat, incident.lon)


def need_of(incident: Incident) -> tuple[tuple[str, ...], str]:
    """Unit agencies and hospital capability the incident calls for (FR-DSP-001/002)."""
    return (
        unit_agencies(needs_extrication=incident.needs_extrication),
        hospital_need(
            priority=incident.priority,
            mass_casualty=incident.mass_casualty,
            needs_extrication=incident.needs_extrication,
        ),
    )


async def recommend(
    session: AsyncSession,
    router: Router,
    incident: Incident,
    *,
    multiplier: float,
    limit: int,
) -> tuple[tuple[str, ...], str, list[Ranked], list[Ranked]]:
    """Ranked units and hospitals with their routes for ``incident`` (FR-DSP-001/002)."""
    scene = scene_of(incident)
    agencies, need = need_of(incident)
    # One session cannot run two statements at once: rank one after the other.
    units = await rank_units(
        session, router, scene, limit=limit, multiplier=multiplier, agencies=agencies
    )
    hospitals = await rank_hospital_candidates(
        session, router, scene, need=need, limit=limit, multiplier=multiplier
    )
    return agencies, need, units, hospitals


async def _rows(session: AsyncSession, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in (await session.execute(text(sql), params)).mappings()]


_UNITS = """
SELECT id, callsign, agency, status, phone, simulated, ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM units WHERE id = ANY(:ids)
"""
_UNITS_LOCKED = "SELECT id, status FROM units WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"
_HOSPITAL = """
SELECT id, name, contact_sms, simulated, ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM facilities WHERE id = :id AND kind = 'hospital'
"""


async def _route(
    router: Router, origin: Point, destination: Point, multiplier: float, what: str
) -> Route:
    """Server-side ETA and route: the client never supplies them (FR-DSP-003)."""
    route = await router.route(origin, destination)
    if route is None:
        raise DispatchError(f"no road route for {what}")
    return Route(
        apply_urban_multiplier(route.duration_s, multiplier), route.distance_m, route.geometry
    )


async def _unit_rows(session: AsyncSession, unit_ids: Sequence[str]) -> list[dict[str, Any]]:
    rows = {r["id"]: r for r in await _rows(session, _UNITS, ids=list(unit_ids))}
    missing = [i for i in unit_ids if i not in rows]
    if missing:
        raise UnknownResourceError(f"unknown unit: {', '.join(missing)}")
    return [rows[i] for i in unit_ids]


async def _hospital_row(session: AsyncSession, hospital_id: str) -> dict[str, Any]:
    rows = await _rows(session, _HOSPITAL, id=hospital_id)
    if not rows:
        raise UnknownResourceError(f"unknown hospital: {hospital_id}")
    return rows[0]


# ---------------------------------------------------------------- recipients


async def _responders(session: AsyncSession, unit: dict[str, Any]) -> tuple[list[User], str | None]:
    """Who is alerted for ``unit``: the responders using its phone, else the phone itself,
    else the responders of its agency (who can see the incident through the agency scope)."""
    base = select(User).where(User.role == Role.RESPONDER.value, User.active.is_(True))
    phone = unit["phone"]
    if phone:
        # Phones are stored as typed (05... or +2135...): compare them normalised.
        candidates = await session.scalars(base.where(User.phone.like(f"%{phone[-9:]}")))
        matched = [
            u for u in candidates if u.phone and normalize_phone(u.phone) == normalize_phone(phone)
        ]
        return matched, (None if matched else normalize_phone(phone))
    return list(await session.scalars(base.where(User.agency == unit["agency"]))), None


async def _hospital_users(session: AsyncSession, facility_id: str) -> list[User]:
    return list(
        await session.scalars(
            select(User).where(
                User.role == Role.HOSPITAL.value,
                User.facility_id == facility_id,
                User.active.is_(True),
            )
        )
    )


async def _alert_unit(
    session: AsyncSession, incident: Incident, unit: dict[str, Any], dispatch_id: uuid.UUID
) -> list[Notification]:
    """SMS + push to the unit's responders (FR-NTF-001), once per recipient (FR-NTF-007)."""
    users, raw_phone = await _responders(session, unit)
    meta = {"dispatch_id": str(dispatch_id)}
    created = await notifications.queue_alerts(session, incident, users, meta=meta)
    if raw_phone:
        sms = await notifications.queue_notification(
            session,
            incident_id=incident.id,
            kind=notifications.KIND_ALERT,
            channel=SMS,
            recipient=raw_phone,
            text=notifications.alert_text(incident),
            meta=meta,
        )
        if sms:
            created.append(sms)
    return created


async def _prealert_hospital(
    session: AsyncSession,
    incident: Incident,
    hospital: dict[str, Any],
    dispatch_id: uuid.UUID,
    eta_s: float,
) -> list[Notification]:
    """Pre-alert by SMS and push to the hospital's users and contact number (FR-NTF-006)."""
    body = notifications.alert_text(incident, kind="PRE", eta_s=eta_s)
    meta = {"dispatch_id": str(dispatch_id)}
    users = await _hospital_users(session, hospital["id"])
    created = await notifications.queue_alerts(
        session, incident, users, kind=notifications.KIND_PREALERT, text=body, meta=meta
    )
    if hospital["contact_sms"]:
        sms = await notifications.queue_notification(
            session,
            incident_id=incident.id,
            kind=notifications.KIND_PREALERT,
            channel=SMS,
            recipient=normalize_phone(hospital["contact_sms"]),
            text=body,
            meta=meta,
        )
        if sms:
            created.append(sms)
    return created


# ---------------------------------------------------------------- dispatch


def _union(current: Sequence[str], extra: Sequence[str]) -> list[str]:
    return sorted({*current, *extra})


async def dispatch(
    session: AsyncSession,
    signer: ChainSigner,
    router: Router,
    user: User,
    scope: Scope,
    incident_id: uuid.UUID,
    unit_ids: Sequence[str],
    hospital_id: str,
    *,
    multiplier: float,
    ip: str | None = None,
) -> Outcome:
    """Dispatch units and one hospital in one transaction (FR-DSP-003).

    Creates the dispatches with server-computed ETA and route, moves the incident to
    ``dispatched``, assigns its agencies and hospital (they drive FR-SEC-002 scoping), marks the
    units assigned and queues the notifications. Raises ``DispatchError``,
    ``UnknownResourceError``, ``IllegalTransitionError``, ``incidents.NotFoundError`` or
    ``RouterUnavailableError``; nothing is written then.
    """
    if len(set(unit_ids)) != len(unit_ids):
        raise DispatchError("a unit can be dispatched only once")
    incident = await incidents.get_visible(session, incident_id, scope)
    check_transition(IncidentStatus(incident.status), IncidentStatus.DISPATCHED)
    scene = scene_of(incident)
    units = await _unit_rows(session, unit_ids)
    hospital = await _hospital_row(session, hospital_id)

    unit_routes, hospital_route = await asyncio.gather(
        asyncio.gather(
            *(
                _route(
                    router, Point(u["lat"], u["lon"]), scene, multiplier, f"unit {u['callsign']}"
                )
                for u in units
            )
        ),
        _route(
            router, scene, Point(hospital["lat"], hospital["lon"]), multiplier, hospital["name"]
        ),
    )

    incident = await incidents.get_visible(session, incident_id, scope, lock=True)
    current = IncidentStatus(incident.status)
    check_transition(current, IncidentStatus.DISPATCHED)
    locked = {r["id"]: r["status"] for r in await _rows(session, _UNITS_LOCKED, ids=list(unit_ids))}
    busy = [u["callsign"] for u in units if locked[u["id"]] != "available"]
    if busy:
        raise DispatchError(f"unit not available: {', '.join(busy)}")

    outcome = Outcome()
    summary_units: list[dict[str, Any]] = []
    for unit, route in zip(units, unit_routes, strict=True):
        row = Dispatch(
            incident_id=incident.id,
            unit_id=unit["id"],
            eta_s=route.duration_s,
            distance_m=route.distance_m,
            route=route.geometry,
            dispatched_by=user.id,
        )
        session.add(row)
        await session.flush()
        await session.execute(
            text("UPDATE units SET status = 'dispatched' WHERE id = :id"), {"id": unit["id"]}
        )
        outcome.notifications += await _alert_unit(session, incident, unit, row.id)
        summary_units.append(
            {"id": unit["id"], "callsign": unit["callsign"], "eta_s": round(route.duration_s)}
        )
    hospital_row = Dispatch(
        incident_id=incident.id,
        hospital_id=hospital["id"],
        eta_s=hospital_route.duration_s,
        distance_m=hospital_route.distance_m,
        route=hospital_route.geometry,
        dispatched_by=user.id,
    )
    session.add(hospital_row)
    await session.flush()
    outcome.notifications += await _prealert_hospital(
        session, incident, hospital, hospital_row.id, hospital_route.duration_s
    )

    incident.status = IncidentStatus.DISPATCHED.value
    incident.assigned_agencies = _union(incident.assigned_agencies, [u["agency"] for u in units])
    incident.assigned_facilities = _union(incident.assigned_facilities, [hospital["id"]])
    incident.version += 1
    payload = {
        "from": current.value,
        "to": IncidentStatus.DISPATCHED.value,
        "dispatch": {
            "units": summary_units,
            "hospital": {"id": hospital["id"], "eta_s": round(hospital_route.duration_s)},
        },
    }
    await incidents.append_event(session, signer, incident, "status_changed", user, payload)
    await audit(
        session,
        user,
        "incident.dispatch",
        AuditTarget("incident", str(incident.id)),
        {"units": [u["id"] for u in units], "hospital": hospital["id"]},
        ip=ip,
    )
    outcome.changes.append(incidents._change(STATUS_CHANGED, incident))
    return outcome


async def change_hospital(
    session: AsyncSession,
    signer: ChainSigner,
    router: Router,
    user: User,
    scope: Scope,
    incident_id: uuid.UUID,
    hospital_id: str,
    *,
    multiplier: float,
    ip: str | None = None,
) -> Outcome:
    """Send the patients to another hospital, e.g. after a DIVERT (E-10).

    The previous hospital is marked ``replaced`` and loses access to the incident.
    """
    incident = await incidents.get_visible(session, incident_id, scope)
    if IncidentStatus(incident.status) not in HOSPITAL_OPEN:
        raise DispatchError(f"cannot change the hospital of a {incident.status} incident")
    scene = scene_of(incident)
    hospital = await _hospital_row(session, hospital_id)
    route = await _route(
        router, scene, Point(hospital["lat"], hospital["lon"]), multiplier, hospital["name"]
    )

    incident = await incidents.get_visible(session, incident_id, scope, lock=True)
    if IncidentStatus(incident.status) not in HOSPITAL_OPEN:
        raise DispatchError(f"cannot change the hospital of a {incident.status} incident")
    previous = await _rows(
        session,
        "SELECT id, hospital_id FROM dispatches "
        "WHERE incident_id = :i AND hospital_id IS NOT NULL AND status = 'dispatched' FOR UPDATE",
        i=incident.id,
    )
    if any(p["hospital_id"] == hospital["id"] for p in previous):
        raise DispatchError("this hospital is already selected")
    old_ids = [p["hospital_id"] for p in previous]
    await session.execute(
        text("UPDATE dispatches SET status = 'replaced' WHERE id = ANY(:ids)"),
        {"ids": [p["id"] for p in previous]},
    )
    row = Dispatch(
        incident_id=incident.id,
        hospital_id=hospital["id"],
        eta_s=route.duration_s,
        distance_m=route.distance_m,
        route=route.geometry,
        dispatched_by=user.id,
    )
    session.add(row)
    await session.flush()
    outcome = Outcome()
    outcome.notifications = await _prealert_hospital(
        session, incident, hospital, row.id, route.duration_s
    )
    incident.assigned_facilities = _union(
        [f for f in incident.assigned_facilities if f not in old_ids], [hospital["id"]]
    )
    incident.version += 1
    await incidents.append_event(
        session,
        signer,
        incident,
        "hospital_changed",
        user,
        {"from": old_ids, "to": hospital["id"], "eta_s": round(route.duration_s)},
    )
    await audit(
        session,
        user,
        "incident.hospital_change",
        AuditTarget("incident", str(incident.id)),
        {"from": old_ids, "to": hospital["id"]},
        ip=ip,
    )
    outcome.changes.append(incidents._change(UPDATED, incident))
    return outcome


# ---------------------------------------------------------------- E-10


def make_proposer(
    session: AsyncSession, router: Router | None, multiplier: float
) -> HospitalProposer:
    """Proposes the best Ready hospital other than the diverted one; ``None`` when routing fails."""

    async def propose(incident: Incident, excluded: str) -> dict[str, Any] | None:
        if router is None or incident.lat is None or incident.lon is None:
            return None
        _agencies, need = need_of(incident)
        try:
            ranked = await rank_hospital_candidates(
                session,
                router,
                Point(incident.lat, incident.lon),
                need=need,
                limit=5,
                multiplier=multiplier,
            )
        except RouterUnavailableError:
            log.warning("no hospital proposal for %s: routing unavailable", incident.short_code)
            return None
        for item in ranked:
            if item.record["id"] != excluded and item.record["ready_state"] == "ready":
                return {
                    "id": item.record["id"],
                    "name": item.record["name"],
                    "eta_s": round(item.eta_s),
                }
        return None

    return propose


async def handle_hospital_divert(
    session: AsyncSession,
    signer: ChainSigner,
    facility_id: str,
    propose: HospitalProposer | None,
) -> list[Change]:
    """A hospital went DIVERT: alert the operators of every incident it was selected for and
    propose the next-ranked hospital (E-10). The alert is a timeline event plus a live update."""
    open_values = [s.value for s in HOSPITAL_OPEN]
    rows = await _rows(
        session,
        "SELECT DISTINCT d.incident_id FROM dispatches d JOIN incidents i ON i.id = d.incident_id "
        "WHERE d.hospital_id = :f AND d.status = 'dispatched' AND i.status = ANY(:open)",
        f=facility_id,
        open=open_values,
    )
    changes: list[Change] = []
    for row in rows:
        incident = await incidents.get_visible(
            session, row["incident_id"], Scope(unrestricted=True), lock=True
        )
        proposed = await propose(incident, facility_id) if propose else None
        incident.version += 1
        await incidents.append_event(
            session,
            signer,
            incident,
            "hospital_diverted",
            None,
            {"facility_id": facility_id, "proposed": proposed},
        )
        changes.append(incidents._change(UPDATED, incident))
    return changes


# ---------------------------------------------------------------- reading


_LIST = """
SELECT d.id, d.unit_id, d.hospital_id, d.eta_s, d.distance_m, d.route, d.status,
       d.dispatched_by, d.at, u.callsign, u.agency, u.simulated AS unit_simulated,
       f.name AS hospital_name, f.simulated AS hospital_simulated
FROM dispatches d
LEFT JOIN units u ON u.id = d.unit_id
LEFT JOIN facilities f ON f.id = d.hospital_id
WHERE d.incident_id = :i
ORDER BY d.at, d.id
"""
_DELIVERIES = """
SELECT meta ->> 'dispatch_id' AS dispatch_id, channel, status, attempts
FROM notifications
WHERE incident_id = :i AND meta ->> 'dispatch_id' IS NOT NULL
ORDER BY created_at, id
"""


async def list_dispatches(session: AsyncSession, incident_id: uuid.UUID) -> list[DispatchOut]:
    """The incident's dispatches with the delivery status of each recipient notification."""
    deliveries: dict[str, list[DeliveryOut]] = {}
    for d in await _rows(session, _DELIVERIES, i=incident_id):
        deliveries.setdefault(d["dispatch_id"], []).append(
            DeliveryOut(channel=d["channel"], status=d["status"], attempts=d["attempts"])
        )
    out: list[DispatchOut] = []
    for r in await _rows(session, _LIST, i=incident_id):
        is_unit = r["unit_id"] is not None
        out.append(
            DispatchOut(
                id=r["id"],
                kind="unit" if is_unit else "hospital",
                resource_id=r["unit_id"] or r["hospital_id"],
                name=r["callsign"] if is_unit else r["hospital_name"],
                agency=r["agency"],
                simulated=r["unit_simulated"] if is_unit else r["hospital_simulated"],
                eta_s=r["eta_s"],
                distance_m=r["distance_m"],
                route_geojson=r["route"],
                status=r["status"],
                dispatched_by=r["dispatched_by"],
                at=r["at"],
                deliveries=deliveries.get(str(r["id"]), []),
            )
        )
    return out
