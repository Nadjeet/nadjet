"""Integration: worker health reports, fault/recovery and /system/cameras (Redis, PostGIS)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.cameras.health import EVENTS_CHANNEL, health_key
from nadjet_api.cameras.models import Camera
from nadjet_api.cameras.seed import seed_cameras
from nadjet_shared.catalogue import load_catalogue

from .conftest import INGEST_TOKEN, PASSWORD, MakeUser

pytestmark = pytest.mark.integration

CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "cameras.yaml"
CAM = "cam-a1-pk42"
INGEST = {"Authorization": f"Bearer {INGEST_TOKEN}"}


def payload(
    *, fault: bool = False, at: datetime | None = None, **extra: object
) -> dict[str, object]:
    return {
        "camera_id": CAM,
        "at": (at or datetime.now(UTC)).isoformat(),
        "connected": not fault,
        "fps": 5.4,
        "queue_depth": 1,
        "latency_ms": {"decode": 4.0, "detect": 31.5, "track": 2.0, "annotate": 6.0},
        "camera_moving": False,
        "fault": fault,
        "fault_reason": "stall" if fault else None,
        "detector": "rf-detr-medium",
        **extra,
    }


@pytest.fixture(autouse=True)
async def seeded(app: FastAPI) -> None:
    async with app.state.session_factory() as s:
        await seed_cameras(s, load_catalogue(CATALOGUE))
        await s.execute(update(Camera).where(Camera.id == CAM).values(status="unknown"))
        await s.commit()
    await app.state.redis.delete(health_key(CAM))


async def operator_headers(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> dict[str, str]:
    user = await make_user(session, role="operator")
    login = await client.post("/auth/login", json={"username": user.username, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_health_report_requires_the_service_token(client: httpx.AsyncClient) -> None:
    assert (await client.post("/internal/camera-health", json=payload())).status_code == 401


async def test_unknown_camera_is_404(client: httpx.AsyncClient) -> None:
    body = {**payload(), "camera_id": "nope"}
    assert (
        await client.post("/internal/camera-health", json=body, headers=INGEST)
    ).status_code == 404


async def test_fault_degrades_the_camera_once_and_recovery_clears_it(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    pubsub = app.state.redis.pubsub()
    await pubsub.subscribe(EVENTS_CHANNEL)
    await pubsub.get_message(timeout=1)  # subscribe confirmation

    async def post(body: dict[str, object]) -> dict[str, object]:
        response = await client.post("/internal/camera-health", json=body, headers=INGEST)
        assert response.status_code == 202, response.text
        return response.json()  # type: ignore[no-any-return]

    assert await post(payload()) == {"status": "online", "transition": None}
    assert await post(payload(fault=True)) == {"status": "degraded", "transition": "camera_fault"}
    assert await post(payload(fault=True)) == {"status": "degraded", "transition": None}
    assert await post(payload()) == {"status": "online", "transition": "camera_recovered"}

    types: list[str] = []
    for _ in range(2):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        assert message is not None
        types.append(json.loads(message["data"])["type"])
    await pubsub.aclose()  # type: ignore[no-untyped-call]
    assert types == ["camera_fault", "camera_recovered"]


async def test_system_cameras_shows_latency_and_flags_silent_workers(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await operator_headers(client, session, make_user)
    silent = await client.get("/system/cameras", headers=headers)
    row = next(c for c in silent.json() if c["id"] == CAM)
    assert row["health"] is None
    assert row["stale"] is True

    await client.post("/internal/camera-health", json=payload(), headers=INGEST)
    row = next(
        c for c in (await client.get("/system/cameras", headers=headers)).json() if c["id"] == CAM
    )
    assert row["stale"] is False
    assert row["health"]["latency_ms"]["detect"] == 31.5
    assert row["health"]["detector"] == "rf-detr-medium"

    old = payload(at=datetime.now(UTC) - timedelta(seconds=30))
    await client.post("/internal/camera-health", json=old, headers=INGEST)
    row = next(
        c for c in (await client.get("/system/cameras", headers=headers)).json() if c["id"] == CAM
    )
    assert row["stale"] is True


async def test_system_cameras_is_closed_to_other_roles(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    assert (await client.get("/system/cameras")).status_code == 401
    user = await make_user(session, role="responder", agency="samu")
    login = await client.post("/auth/login", json={"username": user.username, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/system/cameras", headers=headers)).status_code == 403
