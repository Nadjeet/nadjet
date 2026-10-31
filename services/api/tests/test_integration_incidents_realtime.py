"""Integration: SSE delivery over a real HTTP server and list latency (NFR-PERF-002)."""

import asyncio
import json
import statistics
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.roles import Agency
from nadjet_api.incidents.models import Incident
from nadjet_api.incidents.shortcodes import pick_short_code
from nadjet_api.main import create_app

from .conftest import PASSWORD, MakeUser, make_settings
from .test_integration_incidents import assign, candidate, fresh_spot, ingest

pytestmark = pytest.mark.integration


@pytest.fixture
async def live_server(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, str]]:
    """The app behind a real uvicorn server (ASGITransport does not stream SSE)."""
    app = create_app(make_settings(tmp_path))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield app, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def token_for(base: str, user_name: str) -> dict[str, str]:
    async with httpx.AsyncClient(base_url=base) as c:
        r = await c.post("/auth/login", json={"username": user_name, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def read_event(lines: AsyncIterator[str], *, wait_s: float) -> tuple[str, dict[str, object]]:
    """Next ``event:`` frame (comments are skipped)."""
    async with asyncio.timeout(wait_s):
        name = ""
        async for line in lines:
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: ") and name:
                return name, json.loads(line.removeprefix("data: "))
    raise AssertionError("stream ended")


async def test_verify_is_pushed_to_a_connected_client_in_under_two_seconds(
    live_server: tuple[FastAPI, str], make_user: MakeUser
) -> None:
    app, base = live_server
    async with app.state.session_factory() as s:
        operator = await make_user(s, role="operator")
    headers = await token_for(base, operator.username)
    incident = await ingest(app, candidate(*fresh_spot()))

    async with (
        httpx.AsyncClient(base_url=base, timeout=10) as stream_client,
        httpx.AsyncClient(base_url=base, timeout=10) as api,
        stream_client.stream("GET", "/events", headers=headers) as stream,
    ):
        assert stream.headers["content-type"].startswith("text/event-stream")
        lines = stream.aiter_lines()
        started = time.perf_counter()
        response = await api.post(f"/incidents/{incident.id}/verify", headers=headers)
        assert response.status_code == 200
        name, data = await read_event(lines, wait_s=2.0)
    assert time.perf_counter() - started < 2.0
    assert name == "incident.status_changed"
    assert data == {"incident_id": str(incident.id), "version": 2}


async def test_sse_is_filtered_by_role_scope_and_needs_auth(
    live_server: tuple[FastAPI, str], make_user: MakeUser
) -> None:
    app, base = live_server
    async with app.state.session_factory() as s:
        operator = await make_user(s, role="operator")
        samu = await make_user(s, role="responder", agency=Agency.SAMU.value)
        incident = await ingest(app, candidate(*fresh_spot()))
        await assign(s, incident.id, "samu")
    op_headers = await token_for(base, operator.username)
    samu_headers = await token_for(base, samu.username)
    other = await ingest(app, candidate(*fresh_spot()))

    async with httpx.AsyncClient(base_url=base, timeout=10) as anon:
        assert (await anon.get("/events")).status_code == 401

    async with (
        httpx.AsyncClient(base_url=base, timeout=10) as sc,
        httpx.AsyncClient(base_url=base, timeout=10) as api,
        sc.stream("GET", "/events", headers=samu_headers) as stream,
    ):
        lines = stream.aiter_lines()
        await api.post(f"/incidents/{other.id}/verify", headers=op_headers)  # not samu's
        await api.post(f"/incidents/{incident.id}/verify", headers=op_headers)  # samu's
        _name, data = await read_event(lines, wait_s=2.0)
    assert data["incident_id"] == str(incident.id)


async def test_NFR_PERF_002_list_p95_under_300ms_with_500_incidents(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    login = await client.post(
        "/auth/login", json={"username": operator.username, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    wilaya = f"perf-{uuid.uuid4().hex[:8]}"
    ids = [uuid.uuid4() for _ in range(500)]
    taken = set(await session.scalars(select(Incident.short_code)))
    now = datetime.now(UTC)
    rows = []
    for n, incident_id in enumerate(ids):
        code = pick_short_code(incident_id, taken)
        taken.add(code)
        rows.append(
            {
                "id": incident_id, "short_code": code, "type": "crash", "status": "verified",
                "priority": 1 + n % 4, "priority_reasons": [], "lat": 36.0 + n / 10_000,
                "lon": 3.0, "wilaya": wilaya, "source": "camera", "event_time": now,
                "last_event_time": now, "detected_at": now, "ai_status": "probable",
                "ai_signals": {}, "verifier_result": {"available": False}, "quality_flags": [],
                "version": 1,
            }
        )  # fmt: skip
    await session.execute(insert(Incident), rows)
    await session.commit()
    try:
        timings = []
        for _ in range(60):
            started = time.perf_counter()
            response = await client.get(f"/incidents?wilaya={wilaya}&limit=50", headers=headers)
            timings.append(time.perf_counter() - started)
            assert response.status_code == 200
        assert response.json()["total"] == 500
        p95 = statistics.quantiles(timings, n=20)[18]
        assert p95 <= 0.3, f"p95 {p95 * 1000:.0f} ms"
    finally:
        await session.execute(delete(Incident).where(Incident.wilaya == wilaya))
        await session.commit()
