"""Dependencies shared by the incident routes."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis

from nadjet_api.config import Settings
from nadjet_api.incidents.events import publish
from nadjet_api.incidents.service import Change
from nadjet_api.incidents.signing import ChainSigner
from nadjet_api.incidents.store import EvidenceStore


def get_signer(request: Request) -> ChainSigner:
    signer: ChainSigner = request.app.state.signer
    return signer


def get_store(request: Request) -> EvidenceStore:
    store: EvidenceStore = request.app.state.store
    return store


def get_redis(request: Request) -> Redis:
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")
    return redis


def require_ingest_token(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Service-to-service auth for ``/internal/*`` (NADJET_INGEST_TOKEN)."""
    settings: Settings = request.app.state.settings
    if settings.ingest_token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Ingestion is not configured")
    expected = f"Bearer {settings.ingest_token.get_secret_value()}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def announce(redis: Redis, changes: list[Change]) -> None:
    for change in changes:
        await publish(redis, change)


SignerDep = Annotated[ChainSigner, Depends(get_signer)]
StoreDep = Annotated[EvidenceStore, Depends(get_store)]
RedisDep = Annotated[Redis, Depends(get_redis)]
