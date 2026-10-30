"""``GET /system/ai``: is the Brev AI endpoint reachable and serving the expected model?

The browser never talks to Brev: the API checks it server-side through
``BrevVlmClient.check()`` so no endpoint address or credential reaches the client (FR-VIS-009).
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from nadjet_api.cameras.routes import OperatorUser
from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import BrevVlmClient, InferenceConfigError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


class AiChecker(Protocol):
    async def check(self) -> str: ...
    async def aclose(self) -> None: ...


class AiStatus(BaseModel):
    available: bool
    model: str | None = Field(description="Served model id when available, else null")
    detail: str | None = Field(description="Why the AI is unavailable (no secrets), else null")


class _Misconfigured:
    """Stands in for the client when the endpoint is not an allowed Brev host."""

    async def check(self) -> str:
        raise InferenceConfigError("AI endpoint is not loopback or an allowed Brev host")

    async def aclose(self) -> None:
        pass


async def get_ai_checker() -> AsyncIterator[AiChecker]:
    """One client per request; tests override this dependency."""
    try:
        client: AiChecker = BrevVlmClient(VisionSettings())
    except InferenceConfigError as exc:  # its message names the host: log it, do not return it
        log.warning("AI endpoint misconfigured: %s", exc)
        client = _Misconfigured()
    try:
        yield client
    finally:
        await client.aclose()


@router.get(
    "/ai", responses={401: {"description": "Not authenticated"}, 403: {"description": "Role"}}
)
async def system_ai(
    _user: OperatorUser, checker: Annotated[AiChecker, Depends(get_ai_checker)]
) -> AiStatus:
    """Brev vLLM status: the served model id, or "AI unavailable" (FR-VIS-009)."""
    try:
        return AiStatus(available=True, model=await checker.check(), detail=None)
    except InferenceConfigError as exc:
        return AiStatus(available=False, model=None, detail=str(exc))
    except Exception as exc:  # unreachable, timeout, bad payload: never a 500 on a status page
        log.warning("AI endpoint check failed: %r", exc)
        return AiStatus(available=False, model=None, detail=type(exc).__name__)
