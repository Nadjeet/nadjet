"""``/auth`` routes."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit import AuditTarget, audit
from nadjet_api.auth.deps import current_user
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Agency, Role
from nadjet_api.auth.schemas import LoginRequest, TokenResponse, UserOut
from nadjet_api.auth.security import DUMMY_HASH, encode_token, verify_password
from nadjet_api.config import Settings
from nadjet_api.db import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

BAD_CREDENTIALS = "Invalid username or password"


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=Role(user.role),
        agency=Agency(user.agency) if user.agency else None,
        facility_id=user.facility_id,
        phone=user.phone,
    )


@router.post(
    "/login",
    responses={401: {"description": "Wrong credentials or inactive user (same message)"}},
)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """Exchange username and password for a short-lived access token."""
    settings: Settings = request.app.state.settings
    user = await session.scalar(select(User).where(User.username == body.username))
    # Always run one Argon2 verification so timing does not reveal whether the user exists.
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    token = encode_token(user.id, user.role, key=settings.jwt_key, ttl=ttl)
    await audit(
        session,
        user,
        "auth.login",
        AuditTarget("user", str(user.id)),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return TokenResponse(
        access_token=token, expires_in=int(ttl.total_seconds()), user=user_out(user)
    )


@router.get("/me", responses={401: {"description": "Missing, invalid or expired token"}})
async def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    """The authenticated user."""
    return user_out(user)
