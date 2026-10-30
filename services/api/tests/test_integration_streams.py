"""Integration: console stream token + MediaMTX auth hook over HTTP (FR-SEC-007)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import INGEST_TOKEN, PASSWORD, MakeUser

pytestmark = pytest.mark.integration

AUTH = "/internal/mediamtx-auth"


async def login(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser, role: str
) -> dict[str, str]:
    user = await make_user(session, role=role)
    r = await client.post("/auth/login", json={"username": user.username, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_operator_stream_token_allows_read_only(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, session, make_user, "operator")
    r = await client.post("/auth/stream-token", headers=headers)
    assert r.status_code == 200
    token = r.json()["token"]
    ok = await client.post(AUTH, json={"action": "read", "path": "cam-a1-pk42", "token": token})
    assert ok.status_code == 204
    no = await client.post(AUTH, json={"action": "publish", "path": "cam-a1-pk42", "token": token})
    assert no.status_code == 401


async def test_stream_token_requires_console_role(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    assert (await client.post("/auth/stream-token")).status_code == 401
    user = await make_user(session, role="hospital", facility_id="f1")
    r = await client.post("/auth/login", json={"username": user.username, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/auth/stream-token", headers=headers)).status_code == 403


async def test_unauthenticated_and_worker_access(client: httpx.AsyncClient) -> None:
    anon = await client.post(AUTH, json={"action": "read", "path": "cam-a1-pk42"})
    assert anon.status_code == 401
    bad = await client.post(
        AUTH, json={"action": "publish", "path": "x", "user": "nadjet-worker", "password": "no"}
    )
    assert bad.status_code == 401
    worker = await client.post(
        AUTH,
        json={
            "action": "publish",
            "path": "cam-a1-pk42_ai",
            "user": "nadjet-worker",
            "password": INGEST_TOKEN,
        },
    )
    assert worker.status_code == 204
