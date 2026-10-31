"""Inbound SMS: parse, authorise the sender, apply, answer (FR-NTF-005, E-08, E-09)."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role, Scope, scope_for
from nadjet_api.dispatch.service import HospitalProposer, handle_hospital_divert
from nadjet_api.incidents import service
from nadjet_api.incidents.lifecycle import IllegalTransitionError
from nadjet_api.incidents.models import Incident
from nadjet_api.incidents.service import OPEN_STATUS_VALUES, UPDATED, Change
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.notifications.grammar import (
    AccidentReport,
    FacilityState,
    GrammarError,
    HospitalResponse,
    StatusUpdate,
    Triage,
    help_message,
    normalize_phone,
    parse_inbound,
)
from nadjet_shared.events import (
    CandidateSource,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    Witness,
)

log = logging.getLogger(__name__)

DISPATCHERS = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
STATUS_SENDERS = (*DISPATCHERS, Role.RESPONDER, Role.HOSPITAL)
TRIAGE_SENDERS = (*DISPATCHERS, Role.RESPONDER)
HOSPITAL_SENDERS = (Role.HOSPITAL,)

NOT_AUTHORISED = "Nadjet: not authorised for this incident. The operator was notified."


@dataclass
class Result:
    reply: str
    changes: list[Change] = field(default_factory=list)
    #: Hospitals whose Ready/Divert state this SMS changed (facility id -> state): announced live.
    facility_states: dict[str, str] = field(default_factory=dict)


async def handle_sms(
    session: AsyncSession,
    signer: ChainSigner,
    sender: str,
    body: str,
    message_id: str,
    propose: HospitalProposer | None = None,
) -> Result:
    """Apply one inbound SMS. The caller commits, announces ``changes`` and sends ``reply``.

    ``propose`` finds the next hospital when a DIVERT reply arrives (E-10).
    """
    phone = normalize_phone(sender)
    try:
        command = parse_inbound(body)
    except GrammarError as exc:
        log.info("inbound sms from %s rejected: %s", phone, exc)  # E-08: no state change
        return Result(help_message())
    if isinstance(command, AccidentReport):
        return await _citizen_report(session, signer, phone, command, message_id)

    incident = await session.scalar(
        select(Incident).where(
            Incident.short_code == command.code, Incident.status.in_(OPEN_STATUS_VALUES)
        )
    )
    if incident is None:
        log.info("inbound sms from %s: unknown code %s", phone, command.code)
        return Result(f"Nadjet: unknown code {command.code}. " + help_message())
    user = await _user_by_phone(session, phone)
    allowed = _roles_for(command)
    if (
        user is None
        or Role(user.role) not in allowed
        or not service.can_see(incident, scope_for(user))
    ):
        return await _reject(session, signer, incident, phone, command)
    scope = scope_for(user)
    try:
        if isinstance(command, StatusUpdate):
            return await _status(session, signer, incident, user, scope, command)
        if isinstance(command, Triage):
            return await _triage(session, signer, incident, user, scope, command)
        return await _hospital(session, signer, incident, user, command, propose)
    except IllegalTransitionError as exc:
        return Result(f"Nadjet: {incident.short_code} refused, {exc}")


async def _user_by_phone(session: AsyncSession, phone: str) -> User | None:
    """Phones are stored as typed (``0550...`` or ``+213550...``): compare them normalised."""
    candidates = await session.scalars(
        select(User).where(User.phone.like(f"%{phone[-9:]}"), User.active.is_(True))
    )
    return next((u for u in candidates if u.phone and normalize_phone(u.phone) == phone), None)


def _roles_for(command: StatusUpdate | Triage | HospitalResponse) -> tuple[Role, ...]:
    if isinstance(command, StatusUpdate):
        return STATUS_SENDERS
    if isinstance(command, Triage):
        return TRIAGE_SENDERS
    return HOSPITAL_SENDERS


async def _reject(
    session: AsyncSession,
    signer: ChainSigner,
    incident: Incident,
    phone: str,
    command: Any,
) -> Result:
    """E-09: not assigned (or unknown) sender. No state change; the operators are told."""
    locked = await session.get(Incident, incident.id, with_for_update=True, populate_existing=True)
    changes: list[Change] = []
    if locked is not None:
        locked.version += 1
        await service.append_event(
            session,
            signer,
            locked,
            "sms_rejected",
            None,
            {"phone": phone, "command": type(command).__name__},
        )
        changes.append(service._change(UPDATED, locked))
    return Result(NOT_AUTHORISED, changes)


async def _status(
    session: AsyncSession,
    signer: ChainSigner,
    incident: Incident,
    user: User,
    scope: Scope,
    command: StatusUpdate,
) -> Result:
    change = await service.transition(session, signer, incident.id, command.target, user, scope)
    return Result(f"Nadjet: {incident.short_code} {command.target.value} recorded", [change])


async def _triage(
    session: AsyncSession,
    signer: ChainSigner,
    incident: Incident,
    user: User,
    scope: Scope,
    command: Triage,
) -> Result:
    changes: list[Change] = []
    total = 0
    for tag, count in command.counts.items():
        for _ in range(count):
            _casualty, change = await service.add_casualty(
                session, signer, incident.id, user, scope, {"triage_tag": tag, "source": "sms"}
            )
            changes.append(change)
            total += 1
    await session.refresh(incident)
    return Result(
        f"Nadjet: {incident.short_code} triage {total} recorded, P{incident.priority}", changes
    )


async def _hospital(
    session: AsyncSession,
    signer: ChainSigner,
    incident: Incident,
    user: User,
    command: HospitalResponse,
    propose: HospitalProposer | None,
) -> Result:
    facility_id = user.facility_id
    # The state hospital ranking reads (FR-DSP-002).
    updated = await session.scalar(
        text(
            "UPDATE facilities SET ready_state = :state "
            "WHERE id = :id AND kind = 'hospital' RETURNING id"
        ),
        {"state": command.state.value, "id": facility_id},
    )
    if updated is None:
        log.warning("H reply from a user of unknown facility %s", facility_id)
        return Result(f"Nadjet: {incident.short_code} refused, unknown facility")
    locked = await session.get(Incident, incident.id, with_for_update=True, populate_existing=True)
    assert locked is not None
    locked.version += 1
    await service.append_event(
        session,
        signer,
        locked,
        "hospital_response",
        user,
        {"facility_id": facility_id, "state": command.state.value},
    )
    changes = [service._change(UPDATED, locked)]
    if command.state is FacilityState.DIVERT:
        # E-10: tell the operators of every incident this hospital was selected for.
        changes += await handle_hospital_divert(session, signer, str(updated), propose)
    return Result(
        f"Nadjet: {incident.short_code} {command.state.value} recorded",
        changes,
        {str(updated): command.state.value},
    )


async def _citizen_report(
    session: AsyncSession,
    signer: ChainSigner,
    phone: str,
    report: AccidentReport,
    message_id: str,
) -> Result:
    """Anyone may report. Coordinates place it (and merge, FR-INC-002); else call-back."""
    now = datetime.now(UTC)
    key = f"sms:{message_id or uuid.uuid4()}"
    if report.lat is None or report.lon is None:
        outcome = await service.create_callback_incident(
            session, signer, location_text=report.text, phone=phone, event_time=now, key=key
        )
    else:
        candidate = IncidentCandidate(
            source=CandidateSource.CITIZEN,
            location=GeoLocation(lat=report.lat, lon=report.lon),
            witness=Witness(people_reported=report.people, trapped=report.trapped),
            trigger=TriggerType.CITIZEN_REPORT,
            event_time=now,
            detected_at=now,
        )
        outcome = await service.ingest_candidate(session, signer, candidate, key)
    return Result(f"Nadjet: report received, code {outcome.incident.short_code}", outcome.changes)
