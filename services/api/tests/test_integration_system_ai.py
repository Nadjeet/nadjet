"""Integration: ``/system/ai`` behind real auth (PostGIS) with a mocked Brev endpoint."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.system.routes import AiChecker, get_ai_checker
from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import BrevVlmClient

from .conftest import PASSWORD, MakeUser

pytestmark = pytest.mark.integration

MODEL = "Qwen/Qwen3-VL-8B-Instruct-FP8"


@pytest.fixture(autouse=True)
def brev_serves_the_model(app: FastAPI) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": MODEL}]})
    )

    async def checker() -> AsyncIterator[AiChecker]:
        client = BrevVlmClient(VisionSettings(), transport=transport)
        try:
            yield client
        finally:
            await client.aclose()

    app.dependency_overrides[get_ai_checker] = checker


async def headers(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser, **user: str
) -> dict[str, str]:
    created = await make_user(session, **user)
    login = await client.post(
        "/auth/login", json={"username": created.username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_operator_sees_the_served_model(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    auth = await headers(client, session, make_user, role="operator")
    response = await client.get("/system/ai", headers=auth)
    assert response.status_code == 200
    assert response.json() == {"available": True, "model": MODEL, "detail": None}


async def test_system_ai_is_closed_to_anonymous_and_other_roles(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    assert (await client.get("/system/ai")).status_code == 401
    auth = await headers(client, session, make_user, role="responder", agency="samu")
    assert (await client.get("/system/ai", headers=auth)).status_code == 403
