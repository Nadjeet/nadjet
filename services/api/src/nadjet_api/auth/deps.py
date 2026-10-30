"""FastAPI dependencies: current user, role checks and data scope."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role, Scope, scope_for
from nadjet_api.auth.security import InvalidTokenError, decode_token
from nadjet_api.config import Settings
from nadjet_api.db import get_session

bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    settings: Settings = request.app.state.settings
    try:
        claims = decode_token(credentials.credentials, key=settings.jwt_key)
    except InvalidTokenError:
        raise _unauthorized() from None
    user = await session.get(User, claims.user_id)
    if user is None or not user.active:
        raise _unauthorized()
    return user


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """Dependency allowing only users whose role is in ``roles`` (403 otherwise)."""
    allowed = {r.value for r in roles}

    async def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return user

    return check


async def current_scope(user: Annotated[User, Depends(current_user)]) -> Scope:
    return scope_for(user)
