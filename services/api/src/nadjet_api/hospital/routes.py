"""Hospital API: pre-alert board, Ready/Divert, acknowledgement (FR-HSP-001/002, E-10)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.deps import current_user
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.config import Settings
from nadjet_api.db import get_session
from nadjet_api.dispatch.service import make_proposer
from nadjet_api.hospital import service
from nadjet_api.hospital.schemas import FacilityState, HospitalBoard, ReadinessIn
from nadjet_api.incidents import service as incidents
from nadjet_api.incidents.deps import RedisDep, SignerDep, announce
from nadjet_api.incidents.events import publish_facility

router = APIRouter(tags=["hospital"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]

MANAGERS = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
VIEWERS = (*MANAGERS, Role.AUDITOR)
RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "Not this hospital's user"},
    404: {"description": "Unknown hospital"},
}


async def _facility(
    session: AsyncSession, facility_id: str, user: User, *, manage: bool
) -> FacilityState:
    """The hospital, if ``user`` may use it: its own users, and dispatch roles (auditors read)."""
    facility = await service.get_facility(session, facility_id)
    if facility is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found")
    role = Role(user.role)
    own = role is Role.HOSPITAL and user.facility_id == facility_id
    if not (own or role in MANAGERS or (not manage and role in VIEWERS)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for this hospital")
    return facility


@router.get("/facilities/{facility_id}/prealerts", responses=RESPONSES)
async def prealerts(facility_id: str, session: SessionDep, user: UserDep) -> HospitalBoard:
    """Incoming pre-alerts and today's arrivals of a hospital (FR-HSP-001)."""
    facility = await _facility(session, facility_id, user, manage=False)
    return await service.board(session, facility)


@router.post("/facilities/{facility_id}/readiness", responses=RESPONSES)
async def readiness(
    facility_id: str,
    body: ReadinessIn,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    user: UserDep,
) -> FacilityState:
    """Ready or Divert, from the screen (the SMS ``H <code> READY|DIVERT`` does the same).

    Divert alerts the operators of every incident that selected the hospital (E-10).
    """
    facility = await _facility(session, facility_id, user, manage=True)
    settings: Settings = request.app.state.settings
    propose = make_proposer(
        session, getattr(request.app.state, "router", None), settings.routing_urban_multiplier
    )
    updated, changes = await service.set_readiness(
        session,
        signer,
        user,
        facility,
        body.state,
        propose,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    await announce(redis, changes)
    if updated.ready_state != facility.ready_state:
        await publish_facility(redis, facility_id, updated.ready_state)
    return updated


@router.post(
    "/facilities/{facility_id}/prealerts/{incident_id}/ack",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**RESPONSES, 409: {"description": "Incident is no longer incoming"}},
)
async def acknowledge(
    facility_id: str,
    incident_id: uuid.UUID,
    session: SessionDep,
    redis: RedisDep,
    signer: SignerDep,
    user: UserDep,
) -> None:
    """The hospital confirms it saw the pre-alert; repeating it changes nothing."""
    await _facility(session, facility_id, user, manage=True)
    try:
        change = await service.acknowledge(session, signer, user, facility_id, incident_id)
        await session.commit()
    except incidents.NotFoundError:
        await session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pre-alert not found") from None
    except service.HospitalError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    if change is not None:
        await announce(redis, [change])
