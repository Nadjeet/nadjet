"""Incident API: list, detail, create, verify, reject, status, triage, integrity, SSE."""

import uuid
from collections.abc import AsyncIterator, Awaitable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.auth.deps import current_scope, current_user, require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role, Scope
from nadjet_api.db import get_session
from nadjet_api.incidents import events, service
from nadjet_api.incidents.deps import RedisDep, SignerDep, StoreDep, announce
from nadjet_api.incidents.lifecycle import IllegalTransitionError, IncidentStatus, RejectReason
from nadjet_api.incidents.models import Casualty, Evidence, IncidentEvent
from nadjet_api.incidents.schemas import (
    CasualtyIn,
    CasualtyOut,
    EvidenceOut,
    IncidentDetail,
    IncidentEventOut,
    IncidentList,
    IncidentOut,
    IntegrityFailureOut,
    IntegrityOut,
    ManualIncidentIn,
    MergeIn,
    RejectIn,
    StatusIn,
)
from nadjet_api.incidents.store import EvidenceNotFoundError
from nadjet_shared.events import CandidateSource, IncidentCandidate, TriggerType, Witness

router = APIRouter(tags=["incidents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ScopeDep = Annotated[Scope, Depends(current_scope)]
UserDep = Annotated[User, Depends(current_user)]

DISPATCHERS = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
STATUS_UPDATERS = (*DISPATCHERS, Role.RESPONDER, Role.HOSPITAL)
TRIAGE_REPORTERS = (*DISPATCHERS, Role.RESPONDER)
INTEGRITY_VIEWERS = (*DISPATCHERS, Role.AUDITOR)

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _run[T](session: AsyncSession, work: Awaitable[T]) -> T:
    """Await ``work`` then commit; map domain errors to HTTP."""
    try:
        outcome = await work
        await session.commit()
    except service.NotFoundError:
        await session.rollback()
        raise NOT_FOUND from None
    except (IllegalTransitionError, service.MergeError) as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return outcome


@router.get("/incidents")
async def list_incidents(
    session: SessionDep,
    scope: ScopeDep,
    status_: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    priority: Annotated[int | None, Query(ge=1, le=4)] = None,
    source: CandidateSource | None = None,
    wilaya: str | None = None,
    to_assess: bool | None = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentList:
    """Incidents ordered by priority then recency, limited to the caller's scope."""
    filters = service.IncidentFilters(status_, priority, source, wilaya, to_assess, open_only)
    items, total = await service.list_incidents(session, scope, filters, limit, offset)
    return IncidentList(
        items=[IncidentOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/incidents/{incident_id}", responses={404: {"description": "Not found"}})
async def get_incident(
    incident_id: uuid.UUID, session: SessionDep, scope: ScopeDep
) -> IncidentDetail:
    """One incident with its event timeline, evidence and casualties."""
    try:
        incident = await service.get_visible(session, incident_id, scope)
    except service.NotFoundError:
        raise NOT_FOUND from None
    event_rows = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.id)
    )
    evidence_rows = await session.scalars(
        select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at)
    )
    casualty_rows = await session.scalars(
        select(Casualty).where(Casualty.incident_id == incident_id).order_by(Casualty.at)
    )
    events_out = [IncidentEventOut.model_validate(e) for e in event_rows]
    actor_ids = {e.actor_id for e in events_out if e.actor_id}
    names: dict[uuid.UUID, str] = {}
    if actor_ids:
        rows = await session.execute(
            select(User.id, User.display_name).where(User.id.in_(actor_ids))
        )
        names = {row.id: row.display_name for row in rows}
    for event in events_out:
        event.actor_name = names.get(event.actor_id) if event.actor_id else None
    return IncidentDetail(
        **IncidentOut.model_validate(incident).model_dump(),
        events=events_out,
        evidence=[EvidenceOut.model_validate(e) for e in evidence_rows],
        casualties=[CasualtyOut.model_validate(c) for c in casualty_rows],
    )


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: ManualIncidentIn,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    user: Annotated[User, Depends(require_roles(*DISPATCHERS))],
) -> IncidentOut:
    """Operator creates an incident from a phone call (FR-INC-007); it starts verified."""
    signals: dict[str, float] = {
        name: 1.0
        for name in (
            "bus_involved",
            "person_on_road",
            "flames",
            "smoke",
            "overturned",
            "stopped_in_lane",
        )
        if getattr(body, name)
    }
    if body.vehicle_count is not None:
        signals["vehicle_count"] = float(body.vehicle_count)
    now = datetime.now(UTC)
    candidate = IncidentCandidate(
        source=CandidateSource.OPERATOR,
        location=body.location,
        witness=Witness(people_reported=body.people_reported, trapped=body.trapped),
        trigger=TriggerType.OPERATOR_REPORT,
        event_time=body.event_time or now,
        detected_at=now,
        signals=signals,
    )
    result = await _run(
        session, service.create_manual(session, signer, user, candidate, body.notes)
    )
    await announce(redis, result.changes)
    return IncidentOut.model_validate(result.incident)


@router.post(
    "/incidents/{incident_id}/verify", responses={409: {"description": "Illegal transition"}}
)
async def verify_incident(
    incident_id: uuid.UUID,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Annotated[User, Depends(require_roles(*DISPATCHERS))],
    request: Request,
) -> IncidentOut:
    """Operator confirms a candidate (FR-INC-005)."""
    return await _transition(
        incident_id, IncidentStatus.VERIFIED, session, redis, signer, scope, user, request
    )


@router.post(
    "/incidents/{incident_id}/reject", responses={409: {"description": "Illegal transition"}}
)
async def reject_incident(
    incident_id: uuid.UUID,
    body: RejectIn,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Annotated[User, Depends(require_roles(*DISPATCHERS))],
    request: Request,
) -> IncidentOut:
    """Operator rejects a candidate with a reason label (FR-INC-006)."""
    return await _transition(
        incident_id,
        IncidentStatus.REJECTED,
        session,
        redis,
        signer,
        scope,
        user,
        request,
        body.reason,
    )


@router.post(
    "/incidents/{incident_id}/merge",
    responses={404: {"description": "Not found"}, 409: {"description": "Cannot merge"}},
)
async def merge_incident(
    incident_id: uuid.UUID,
    body: MergeIn,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Annotated[User, Depends(require_roles(*DISPATCHERS))],
) -> IncidentOut:
    """Operator merges a candidate into another open incident (FR-INC-002, E-14)."""
    changes = await _run(
        session, service.merge_into(session, signer, incident_id, body.into, user, scope)
    )
    await announce(redis, changes)
    return IncidentOut.model_validate(await service.get_visible(session, body.into, scope))


@router.post(
    "/incidents/{incident_id}/status", responses={409: {"description": "Illegal transition"}}
)
async def set_status(
    incident_id: uuid.UUID,
    body: StatusIn,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Annotated[User, Depends(require_roles(*STATUS_UPDATERS))],
    request: Request,
) -> IncidentOut:
    """Advance the response lifecycle (dispatch, acknowledge, ..., close)."""
    return await _transition(
        incident_id, IncidentStatus(body.status), session, redis, signer, scope, user, request
    )


async def _transition(
    incident_id: uuid.UUID,
    target: IncidentStatus,
    session: AsyncSession,
    redis: RedisDep,
    signer: SignerDep,
    scope: Scope,
    user: User,
    request: Request,
    reason: RejectReason | None = None,
) -> IncidentOut:
    change = await _run(
        session,
        service.transition(session, signer, incident_id, target, user, scope, reason=reason),
    )
    await announce(redis, [change])
    incident = await service.get_visible(session, incident_id, scope)
    return IncidentOut.model_validate(incident)


@router.post(
    "/incidents/{incident_id}/casualties",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Incident is closed"}},
)
async def add_casualty(
    incident_id: uuid.UUID,
    body: CasualtyIn,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Annotated[User, Depends(require_roles(*TRIAGE_REPORTERS))],
) -> IncidentOut:
    """Record a triage entry; the incident priority is recomputed (FR-INC-004, FR-INC-008)."""
    _casualty, change = await _run(
        session,
        service.add_casualty(
            session, signer, incident_id, user, scope, body.model_dump(mode="json")
        ),
    )
    await announce(redis, [change])
    return IncidentOut.model_validate(await service.get_visible(session, incident_id, scope))


@router.get("/incidents/{incident_id}/integrity", responses={404: {"description": "Not found"}})
async def integrity(
    incident_id: uuid.UUID,
    session: SessionDep,
    signer: SignerDep,
    store: StoreDep,
    scope: ScopeDep,
    _user: Annotated[User, Depends(require_roles(*INTEGRITY_VIEWERS))],
) -> IntegrityOut:
    """Recompute evidence hashes and the signed event chain (FR-SEC-003)."""
    try:
        await service.get_visible(session, incident_id, scope)
    except service.NotFoundError:
        raise NOT_FOUND from None
    report = await service.verify_integrity(session, signer, store, incident_id)
    return IntegrityOut(
        status="valid" if report.valid else "invalid",
        events_checked=report.events_checked,
        files_checked=report.files_checked,
        failures=[
            IntegrityFailureOut(kind=f.kind, ref=f.ref, detail=f.detail) for f in report.failures
        ],
    )


@router.get(
    "/incidents/{incident_id}/evidence/{evidence_id}",
    responses={404: {"description": "Not found"}},
    response_class=StreamingResponse,
)
async def download_evidence(
    incident_id: uuid.UUID,
    evidence_id: uuid.UUID,
    session: SessionDep,
    store: StoreDep,
    scope: ScopeDep,
    user: UserDep,
    request: Request,
) -> StreamingResponse:
    """Stream an evidence file; every view or download is audited (FR-SEC-004)."""
    try:
        await service.get_visible(session, incident_id, scope)
    except service.NotFoundError:
        raise NOT_FOUND from None
    item = await session.get(Evidence, evidence_id)
    if item is None or item.incident_id != incident_id:
        raise NOT_FOUND
    await audit(
        session,
        user,
        "evidence.download",
        AuditTarget("evidence", str(evidence_id)),
        {"incident_id": str(incident_id), "kind": item.kind, "sha256": item.sha256},
        ip=_client_ip(request),
    )
    await session.commit()
    content_type, path = item.content_type, item.path
    try:
        body = store.read(path)
        first = await anext(body)
    except (EvidenceNotFoundError, StopAsyncIteration):
        raise NOT_FOUND from None

    async def chunks() -> AsyncIterator[bytes]:
        yield first
        async for chunk in body:
            yield chunk

    return StreamingResponse(chunks(), media_type=content_type)


@router.get("/events", response_class=StreamingResponse)
async def incident_events(
    session: SessionDep, redis: RedisDep, scope: ScopeDep
) -> StreamingResponse:
    """Server-Sent Events: ``incident.created|updated|status_changed`` with id and version.

    Clients refetch the incident on each event. A comment heartbeat is sent every 15 s.
    """
    await session.close()  # do not hold a DB connection for the lifetime of the stream
    return StreamingResponse(
        events.stream(redis, scope),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
