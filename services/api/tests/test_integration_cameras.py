"""Integration: seed-cameras and GET /cameras against the real PostGIS (`make infra`)."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.security import hash_password
from nadjet_api.cameras.models import Camera
from nadjet_api.cameras.seed import seed_cameras
from nadjet_api.config import Settings
from nadjet_api.main import create_app
from nadjet_shared.catalogue import load_catalogue

pytestmark = pytest.mark.integration

CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "cameras.yaml"
PASSWORD = "integration-pass-1"
CAM = "cam-a1-pk42"


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    application = create_app(Settings())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as s:
        yield s


@pytest.fixture
async def seeded(session: AsyncSession) -> int:
    return await seed_cameras(session, load_catalogue(CATALOGUE))


async def login(client: httpx.AsyncClient, session: AsyncSession, role: str, **extra: str) -> dict:  # type: ignore[type-arg]
    user = User(
        username=f"it-{uuid.uuid4().hex[:12]}",
        display_name="IT",
        password_hash=hash_password(PASSWORD),
        role=role,
        **extra,
    )
    session.add(user)
    await session.commit()
    response = await client.post(
        "/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_list_returns_seeded_cameras_with_coordinates_zones_and_streams(
    client: httpx.AsyncClient, session: AsyncSession, seeded: int
) -> None:
    headers = await login(client, session, "operator")
    response = await client.get("/cameras", headers=headers)
    assert response.status_code == 200, response.text
    cameras = {c["id"]: c for c in response.json()}
    assert len(cameras) >= seeded
    cam = cameras[CAM]
    assert (cam["lat"], cam["lon"]) == (36.648, 3.329)
    assert cam["road"] == "A1"
    assert cam["pk_km"] == 42
    assert cam["simulated"] is True
    assert cam["zones"]["carriageway"][0] == cam["zones"]["carriageway"][-1]
    assert cam["zones"]["live_lanes"]
    assert cam["stream"] == {
        "path": CAM,
        "rtsp_url": f"rtsp://localhost:8554/{CAM}",
        "whep_url": f"http://localhost:8889/{CAM}/whep",
        "hls_url": f"http://localhost:8888/{CAM}/index.m3u8",
    }


async def test_get_one_camera_and_unknown_camera(
    client: httpx.AsyncClient, session: AsyncSession, seeded: int
) -> None:
    headers = await login(client, session, "supervisor")
    assert (await client.get(f"/cameras/{CAM}", headers=headers)).json()["id"] == CAM
    assert (await client.get("/cameras/nope", headers=headers)).status_code == 404


async def test_cameras_require_an_operator_role(
    client: httpx.AsyncClient, session: AsyncSession, seeded: int
) -> None:
    assert (await client.get("/cameras")).status_code == 401
    responder = await login(client, session, "responder", agency="samu")
    assert (await client.get("/cameras", headers=responder)).status_code == 403
    assert (await client.get(f"/cameras/{CAM}", headers=responder)).status_code == 403


async def test_seed_is_idempotent_keeps_status_and_generates_geometry(
    session: AsyncSession, seeded: int
) -> None:
    await session.execute(update(Camera).where(Camera.id == CAM).values(status="online"))
    await session.commit()
    assert await seed_cameras(session, load_catalogue(CATALOGUE)) == seeded
    camera = await session.get(Camera, CAM, populate_existing=True)
    assert camera is not None
    assert camera.status == "online"
    point = await session.scalar(
        text("SELECT ST_AsText(geom) FROM cameras WHERE id = :id"), {"id": CAM}
    )
    assert point == "POINT(3.329 36.648)"
    await session.execute(update(Camera).where(Camera.id == CAM).values(status="unknown"))
    await session.commit()
