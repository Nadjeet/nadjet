"""Integration: seeded facilities in PostGIS, KNN prefilter, ranking and the HTTP API.

Ordering rules run against a deterministic fake router; the OSRM tests need the routing
service (`make routing-up`, or the graph built in CI) and fail, not skip, when it is down.
Covers FR-DSP-001, FR-DSP-002, FR-ADM-001, AC-DSP-001.1 (backend part).
"""

import math
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.auth.security import hash_password
from nadjet_api.config import Settings
from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units, seed_geo
from nadjet_api.main import create_app
from nadjet_api.routing.router import Leg, Point, Route
from nadjet_api.routing.service import Ranked, rank_hospital_candidates, rank_units

pytestmark = pytest.mark.integration

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"
BOUMERDES = {"lat": 36.7620, "lon": 3.4770}
PASSWORD = "integration-pass-1"
MS_FREE_FLOW = 15.0  # m/s used by the fake router


def haversine_m(a: Point, b: Point) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi, dlmb = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


class FakeRouter:
    """Straight-line distance at a constant speed."""

    async def table(
        self, sources: Sequence[Point], destinations: Sequence[Point]
    ) -> list[list[Leg | None]]:
        return [
            [Leg(haversine_m(s, d) / MS_FREE_FLOW, haversine_m(s, d)) for d in destinations]
            for s in sources
        ]

    async def route(self, origin: Point, destination: Point) -> Route | None:
        meters = haversine_m(origin, destination)
        line = {
            "type": "LineString",
            "coordinates": [[origin.lon, origin.lat], [destination.lon, destination.lat]],
        }
        return Route(meters / MS_FREE_FLOW, meters, line)


class CutOffRouter(FakeRouter):
    """No road reaches ``cut``, as when OSRM answers null for a table cell."""

    def __init__(self, cut: Point) -> None:
        self.cut = cut

    async def table(
        self, sources: Sequence[Point], destinations: Sequence[Point]
    ) -> list[list[Leg | None]]:
        return [
            [None if self.cut in (s, d) else Leg(60.0, 1000.0) for d in destinations]
            for s in sources
        ]


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    application = create_app(Settings(), road_router=FakeRouter())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await seed_geo(
        session,
        load_facilities(SEED_DIR / "facilities.csv"),
        load_capabilities(SEED_DIR / "capabilities.csv"),
        load_units(SEED_DIR / "units.csv"),
    )


async def login(client: httpx.AsyncClient, session: AsyncSession, role: str) -> dict[str, str]:
    user = User(
        username=f"it-{uuid.uuid4().hex[:12]}",
        display_name="IT",
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    session.add(user)
    await session.commit()
    response = await client.post(
        "/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def http(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_seed_is_idempotent_and_flags_simulated(session: AsyncSession) -> None:
    before = (await session.execute(text("SELECT count(*) FROM facilities"))).scalar_one()
    await seed_geo(
        session,
        load_facilities(SEED_DIR / "facilities.csv"),
        load_capabilities(SEED_DIR / "capabilities.csv"),
        load_units(SEED_DIR / "units.csv"),
    )
    after = (await session.execute(text("SELECT count(*) FROM facilities"))).scalar_one()
    real = (
        await session.execute(text("SELECT count(*) FROM facilities WHERE NOT simulated"))
    ).scalar_one()
    units = (
        await session.execute(text("SELECT count(*) FROM units WHERE NOT simulated"))
    ).scalar_one()
    assert before == after > 500
    assert real == 0
    assert units == 0


async def test_seed_rejects_unknown_facility_reference(session: AsyncSession) -> None:
    [unit] = load_units(SEED_DIR / "units.csv")[:1]
    bad = unit.model_copy(update={"id": "unit-bad", "facility_id": "does-not-exist"})
    with pytest.raises(ValueError, match="unknown facility ids"):
        await seed_geo(session, [], [], [bad])


async def test_recommendations_require_operator_role(app: FastAPI, session: AsyncSession) -> None:
    async with http(app) as client:
        assert (await client.get("/routing/recommendations", params=BOUMERDES)).status_code == 401
        headers = await login(client, session, "auditor")
        response = await client.get("/routing/recommendations", params=BOUMERDES, headers=headers)
    assert response.status_code == 403


async def test_units_and_hospitals_near_boumerdes_ranked_by_eta_quickly(
    app: FastAPI, session: AsyncSession
) -> None:
    """AC-DSP-001.1 (backend): >= 3 units and >= 3 hospitals, ranked by ETA, in < 2 s."""
    async with http(app) as client:
        headers = await login(client, session, "operator")
        started = time.perf_counter()
        response = await client.get("/routing/recommendations", params=BOUMERDES, headers=headers)
        elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    body = response.json()
    assert elapsed < 2.0
    assert len(body["units"]) >= 3
    assert len(body["hospitals"]) >= 3
    unit_etas = [u["eta_s"] for u in body["units"]]
    assert unit_etas == sorted(unit_etas)
    assert all(u["simulated"] and u["route_geojson"]["type"] == "LineString" for u in body["units"])
    assert body["urban_multiplier"] == Settings().routing_urban_multiplier


async def test_trauma_need_ranks_capable_ready_hospitals_first_and_divert_after(
    app: FastAPI, session: AsyncSession
) -> None:
    async with http(app) as client:
        headers = await login(client, session, "operator")
        response = await client.get(
            "/routing/recommendations",
            params={**BOUMERDES, "kind": "hospital", "need": "trauma", "limit": 5},
            headers=headers,
        )
    hospitals = response.json()["hospitals"]
    assert response.json()["units"] == []
    trauma = [h["capabilities"].get("trauma", False) for h in hospitals]
    assert trauma[:3] == [True, True, True]  # capable first, even though nearer ones are not
    states = [h["ready_state"] for h in hospitals[:3]]
    assert states == ["ready", "ready", "divert"]  # Bologhine is simulated as Divert


async def test_dispatched_units_are_not_recommended(app: FastAPI, session: AsyncSession) -> None:
    await session.execute(text("UPDATE units SET status = 'busy' WHERE id = 'unit-pc-boumerdes-1'"))
    await session.commit()
    try:
        async with http(app) as client:
            headers = await login(client, session, "operator")
            body = (
                await client.get("/routing/recommendations", params=BOUMERDES, headers=headers)
            ).json()
        assert "unit-pc-boumerdes-1" not in {u["id"] for u in body["units"]}
    finally:
        await session.execute(
            text("UPDATE units SET status = 'available' WHERE id = 'unit-pc-boumerdes-1'")
        )
        await session.commit()


async def test_unreachable_units_and_hospitals_are_left_out(session: AsyncSession) -> None:
    """A resource with no road to the scene has no ETA, so it is never listed (FR-DSP-001)."""
    scene = Point(BOUMERDES["lat"], BOUMERDES["lon"])

    async def units(router: FakeRouter) -> list[Ranked]:
        return await rank_units(session, router, scene, limit=10, multiplier=1.0)

    async def hospitals(router: FakeRouter) -> list[Ranked]:
        return await rank_hospital_candidates(
            session, router, scene, need=None, limit=10, multiplier=1.0
        )

    for rank in (units, hospitals):
        ranked = await rank(FakeRouter())
        first = ranked[0].record
        remaining = await rank(CutOffRouter(Point(first["lat"], first["lon"])))
        assert remaining
        assert first["id"] not in {i.record["id"] for i in remaining}


async def test_osrm_down_returns_503_with_message_and_no_eta() -> None:
    dead = Settings(osrm_url="http://127.0.0.1:1", routing_timeout_s=1.0)  # nothing listens here
    application = create_app(dead)
    async with application.router.lifespan_context(application), http(application) as client:
        async with application.state.session_factory() as s:
            headers = await login(client, s, "operator")
        response = await client.get("/routing/recommendations", params=BOUMERDES, headers=headers)
    assert response.status_code == 503
    assert "Routing service unavailable" in response.json()["detail"]
    assert "eta_s" not in response.text


async def test_real_osrm_ranks_units_and_hospitals_by_road_eta(session: AsyncSession) -> None:
    """Needs OSRM (`make routing-up`, or the CI graph from the committed test extract)."""
    application = create_app(Settings())
    async with application.router.lifespan_context(application), http(application) as client:
        async with application.state.session_factory() as s:
            headers = await login(client, s, "operator")
        started = time.perf_counter()
        response = await client.get("/routing/recommendations", params=BOUMERDES, headers=headers)
        elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    body = response.json()
    assert elapsed < 2.0
    assert len(body["units"]) >= 3
    assert len(body["hospitals"]) >= 3
    for group in (body["units"], body["hospitals"]):
        assert all(r["eta_s"] > 0 and r["distance_m"] > 0 for r in group)
        assert all(len(r["route_geojson"]["coordinates"]) > 2 for r in group)
    unit_etas = [u["eta_s"] for u in body["units"]]
    assert unit_etas == sorted(unit_etas)
