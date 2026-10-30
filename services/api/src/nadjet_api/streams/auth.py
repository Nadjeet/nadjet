"""MediaMTX HTTP authentication (``authMethod: http``) and the console stream-token route.

MediaMTX POSTs every publish/read/api request here and accepts it on 2xx. Rules (FR-SEC-007):
- the service user (camsim, Brev workers) authenticates with ``NADJET_INGEST_TOKEN`` and may
  publish, read and use the control API;
- everyone else needs a stream token, sent as Bearer token, password or ``?token=``: a
  ``read`` token to read, a ``publish`` token (try-it WHIP session) to publish its own path.
"""

import hmac
from typing import Annotated, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.auth.security import InvalidTokenError
from nadjet_api.config import Settings
from nadjet_api.streams.tokens import decode_stream_token, encode_stream_token

router = APIRouter(tags=["streams"])

SERVICE_ACTIONS = {"publish", "read", "playback", "api", "metrics", "pprof"}


class MediaMtxAuthRequest(BaseModel):
    """Body MediaMTX sends (https://mediamtx.org/docs/usage/authentication)."""

    user: str = ""
    password: str = ""
    token: str = ""
    ip: str = ""
    action: str
    path: str = ""
    protocol: str = ""
    id: str | None = None
    query: str = ""


class StreamTokenResponse(BaseModel):
    token: str
    expires_in: int
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105


def _is_service(req: MediaMtxAuthRequest, settings: Settings) -> bool:
    if settings.ingest_token is None:
        return False
    return hmac.compare_digest(req.user.encode(), settings.stream_service_user.encode()) and (
        hmac.compare_digest(
            req.password.encode(), settings.ingest_token.get_secret_value().encode()
        )
    )


def _candidate_tokens(req: MediaMtxAuthRequest) -> list[str]:
    from_query = parse_qs(req.query).get("token", [])
    return [t for t in (req.token, req.password, *from_query) if t]


def authorize(req: MediaMtxAuthRequest, settings: Settings) -> bool:
    """Pure decision for one MediaMTX request."""
    if _is_service(req, settings):
        return req.action in SERVICE_ACTIONS
    if req.action not in ("read", "publish"):
        return False
    for raw in _candidate_tokens(req):
        try:
            claims = decode_stream_token(raw, key=settings.jwt_key)
        except InvalidTokenError:
            continue
        if claims.action == req.action and claims.path in (None, req.path):
            return True
    return False


@router.post(
    "/internal/mediamtx-auth",
    include_in_schema=True,
    responses={401: {"description": "Request not allowed"}},
)
async def mediamtx_auth(body: MediaMtxAuthRequest, request: Request) -> Response:
    """Allow or reject one MediaMTX publish/read/api request."""
    if authorize(body, request.app.state.settings):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Stream access denied")


StreamViewer = Annotated[User, Depends(require_roles(Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN))]


@router.post(
    "/auth/stream-token",
    tags=["auth"],
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Role"}},
)
async def stream_token(user: StreamViewer, request: Request) -> StreamTokenResponse:
    """Short-lived token to watch camera streams (WHEP/HLS), for the console roles."""
    settings: Settings = request.app.state.settings
    ttl = settings.stream_token_ttl
    token = encode_stream_token(str(user.id), "read", key=settings.jwt_key, ttl=ttl)
    return StreamTokenResponse(token=token, expires_in=int(ttl.total_seconds()))
