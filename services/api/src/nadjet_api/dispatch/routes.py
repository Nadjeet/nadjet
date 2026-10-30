"""Dispatch API: recommendations, dispatch, hospital change, dispatch list (FR-DSP-001..004)."""

import logging
import uuid
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import current_scope, require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role, Scope
from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.dispatch import service
from nadjet_api.dispatch.schemas import (
    DispatchIn,
    DispatchOut,
    DispatchResult,
    HospitalChangeIn,
    IncidentRecommendations,
)
from nadjet_api.incidents import service as incidents
from nadjet_api.incidents.deps import RedisDep, SignerDep, announce
from nadjet_api.incidents.lifecycle import IllegalTransitionError, IncidentStatus
from nadjet_api.incidents.schemas import IncidentOut
from nadjet_api.notifications import jobs
from nadjet_api.routing.router import Router, RouterUnavailableError
from nadjet_api.routing.routes import hospital_resource, unit_resource

log = logging.getLogger(__name__)

router = APIRouter(tags=["dispatch"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ScopeDep = Annotated[Scope, Depends(current_scope)]
DISPATCHERS = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
Dispatcher = Annotated[User, Depends(require_roles(*DISPATCHERS))]
Viewer = Annotated[User, Depends(require_roles(*DISPATCHERS, Role.AUDITOR, Role.RESPONDER))]

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")


def _road_router(request: Request) -> Router:
    road_router: Router | None = getattr(request.app.state, "router", None)
    if road_router is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Routing service unavailable")
    return road_router


def _multiplier(request: Request) -> float:
    settings: Settings = request.app.state.settings
    return settings.routing_urban_multiplier


def _unavailable(exc: RouterUnavailableError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Routing service unavailable: {exc}")


async def _guard[T](session: AsyncSession, work: Awaitable[T]) -> T:
    """Await ``work`` then commit; map domain errors to HTTP."""
    try:
        outcome = await work
        await session.commit()
    except incidents.NotFoundError:
        await session.rollback()
        raise NOT_FOUND from None
    except (service.DispatchError, IllegalTransitionError) as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except service.UnknownResourceError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except RouterUnavailableError as exc:
        await session.rollback()
        raise _unavailable(exc) from None
    return outcome


async def _publish(request: Request, redis: RedisDep, outcome: service.Outcome) -> None:
    """After the commit: live updates now, then the notification jobs (SC-002).

    A lost job leaves the notification ``queued``, which the response and the console show.
    """
    await announce(redis, outcome.changes)
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        log.error("no job queue: %d notification(s) stay queued", len(outcome.notifications))
        return
    try:
        await jobs.enqueue_all(pool, outcome.notifications)
    except Exception:
        log.exception("could not enqueue %d notification(s)", len(outcome.notifications))


async def _result(session: AsyncSession, scope: Scope, incident_id: uuid.UUID) -> DispatchResult:
    incident = await incidents.get_visible(session, incident_id, scope)
    return DispatchResult(
        incident=IncidentOut.model_validate(incident),
        dispatches=await service.list_dispatches(session, incident_id),
    )


@router.get(
    "/incidents/{incident_id}/recommendations",
    responses={404: {"description": "Not found"}, 409: {"description": "Not dispatchable"}},
)
async def recommendations(
    incident_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    scope: ScopeDep,
    _user: Dispatcher,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> IncidentRecommendations:
    """Units and hospitals ranked by road ETA for this incident's needs (FR-DSP-001/002)."""
    try:
        incident = await incidents.get_visible(session, incident_id, scope)
    except incidents.NotFoundError:
        raise NOT_FOUND from None
    if IncidentStatus(incident.status) not in (IncidentStatus.VERIFIED, *service.HOSPITAL_OPEN):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a {incident.status} incident cannot be dispatched"
        )
    multiplier = _multiplier(request)
    try:
        agencies, need, units, hospitals = await service.recommend(
            session, _road_router(request), incident, multiplier=multiplier, limit=limit
        )
    except service.DispatchError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except RouterUnavailableError as exc:
        raise _unavailable(exc) from None
    return IncidentRecommendations(
        unit_agencies=list(agencies),
        hospital_need=need,
        urban_multiplier=multiplier,
        units=[unit_resource(u) for u in units],
        hospitals=[hospital_resource(h) for h in hospitals],
    )


@router.post(
    "/incidents/{incident_id}/dispatch",
    responses={
        404: {"description": "Not found"},
        409: {"description": "Not dispatchable or unit not available"},
        422: {"description": "Unknown unit or hospital"},
        503: {"description": "Routing service unavailable"},
    },
)
async def dispatch_incident(
    incident_id: uuid.UUID,
    body: DispatchIn,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Dispatcher,
) -> DispatchResult:
    """Dispatch units and one hospital in one action (FR-DSP-003, FR-NTF-001, FR-NTF-006)."""
    outcome = await _guard(
        session,
        service.dispatch(
            session,
            signer,
            _road_router(request),
            user,
            scope,
            incident_id,
            body.unit_ids,
            body.hospital_id,
            multiplier=_multiplier(request),
            ip=request.client.host if request.client else None,
        ),
    )
    await _publish(request, redis, outcome)
    return await _result(session, scope, incident_id)


@router.post(
    "/incidents/{incident_id}/hospital",
    responses={
        404: {"description": "Not found"},
        409: {"description": "Hospital cannot be changed now"},
        422: {"description": "Unknown hospital"},
        503: {"description": "Routing service unavailable"},
    },
)
async def change_hospital(
    incident_id: uuid.UUID,
    body: HospitalChangeIn,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    scope: ScopeDep,
    user: Dispatcher,
) -> DispatchResult:
    """Send the patients to another hospital, e.g. after a DIVERT (E-10)."""
    outcome = await _guard(
        session,
        service.change_hospital(
            session,
            signer,
            _road_router(request),
            user,
            scope,
            incident_id,
            body.hospital_id,
            multiplier=_multiplier(request),
            ip=request.client.host if request.client else None,
        ),
    )
    await _publish(request, redis, outcome)
    return await _result(session, scope, incident_id)


@router.get("/incidents/{incident_id}/dispatches", responses={404: {"description": "Not found"}})
async def list_dispatches(
    incident_id: uuid.UUID, session: SessionDep, scope: ScopeDep, user: Viewer
) -> list[DispatchOut]:
    """Dispatches of the incident with the delivery status of each notification.

    A responder only gets the hospital the patients go to.
    """
    try:
        await incidents.get_visible(session, incident_id, scope)
    except incidents.NotFoundError:
        raise NOT_FOUND from None
    rows = await service.list_dispatches(session, incident_id)
    return service.for_responder(rows) if user.role == Role.RESPONDER.value else rows
