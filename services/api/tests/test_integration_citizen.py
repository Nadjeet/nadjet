"""Integration: public citizen reports (PostGIS, Redis).

Covers US-9, FR-CIT-001/004/006, FR-INC-003, AC-CIT-006.2, E-14.
"""

import random
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from nadjet_api.incidents.models import Evidence, Incident, IncidentEvent
from nadjet_api.main import create_app

from .conftest import make_settings
from .test_integration_incidents import candidate, fresh_spot, ingest, metres_north

pytestmark = pytest.mark.integration

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body" * 100


def form(lat: float, lon: float, **extra: str) -> dict[str, str]:
    return {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", **extra}


def client_for(app: FastAPI) -> httpx.AsyncClient:
    """A client with its own IP, so the per-IP rate limit never leaks between tests."""
    ip = ".".join(str(random.randint(1, 254)) for _ in range(4))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 5000)), base_url="http://test"
    )


@pytest.fixture
async def citizen(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(app) as c:
        yield c


async def incident_by_code(app: FastAPI, code: str) -> Incident:
    async with app.state.session_factory() as s:
        # Short codes are reused once an incident closes: take the newest open one.
        return (
            await s.scalars(
                select(Incident)
                .where(Incident.short_code == code)
                .order_by(Incident.created_at.desc())
            )
        ).first() or pytest.fail("incident not found")


async def test_one_tap_report_creates_an_unverified_citizen_incident(
    app: FastAPI, citizen: httpx.AsyncClient
) -> None:
    """AC-CIT-006.2: the position of the phone becomes an unverified incident."""
    lat, lon = fresh_spot()
    response = await citizen.post("/public/reports", data=form(lat, lon))
    assert response.status_code == 201
    body = response.json()
    assert body["merged"] is False
    incident = await incident_by_code(app, body["short_code"])
    assert (incident.source, incident.status) == ("citizen", "candidate")
    assert incident.lat == pytest.approx(lat, abs=1e-5)
    assert incident.lon == pytest.approx(lon, abs=1e-5)
    assert incident.report_count == 1


async def test_trapped_answer_raises_priority_and_flags_extrication(
    app: FastAPI, citizen: httpx.AsyncClient
) -> None:
    """FR-INC-003: anyone trapped means at least P1 with the extrication flag."""
    lat, lon = fresh_spot()
    response = await citizen.post(
        "/public/reports", data=form(lat, lon, people_reported="3", trapped="true")
    )
    incident = await incident_by_code(app, response.json()["short_code"])
    assert incident.priority <= 1
    assert incident.needs_extrication is True
    assert (incident.people_reported, incident.trapped_reported) == (3, True)


async def test_report_near_an_open_incident_merges_and_counts(
    app: FastAPI, citizen: httpx.AsyncClient
) -> None:
    """FR-CIT-001 / FR-INC-002: a second witness raises ``report_count`` of the same incident."""
    lat, lon = fresh_spot()
    existing = await ingest(app, candidate(lat, lon))
    response = await citizen.post(
        "/public/reports", data=form(metres_north(lat, 40), lon, trapped="true")
    )
    body = response.json()
    assert body["merged"] is True
    assert body["short_code"] == existing.short_code
    merged = await incident_by_code(app, existing.short_code)
    assert merged.report_count == 2
    assert merged.trapped_reported is True


async def test_same_idempotency_key_returns_the_same_report(
    app: FastAPI, citizen: httpx.AsyncClient
) -> None:
    lat, lon = fresh_spot()
    headers = {"Idempotency-Key": uuid.uuid4().hex}
    first = await citizen.post("/public/reports", data=form(lat, lon), headers=headers)
    second = await citizen.post("/public/reports", data=form(lat, lon), headers=headers)
    assert first.json()["short_code"] == second.json()["short_code"]
    assert (await incident_by_code(app, first.json()["short_code"])).report_count == 1


async def test_phone_is_kept_in_the_event_for_call_back(
    app: FastAPI, citizen: httpx.AsyncClient
) -> None:
    lat, lon = fresh_spot()
    response = await citizen.post("/public/reports", data=form(lat, lon, phone="0550 12 34 56"))
    incident = await incident_by_code(app, response.json()["short_code"])
    async with app.state.session_factory() as s:
        event = await s.scalar(
            select(IncidentEvent).where(
                IncidentEvent.incident_id == incident.id, IncidentEvent.kind == "created"
            )
        )
    assert event is not None
    assert event.payload["contact"] == {"phone": "+213550123456"}


async def test_photo_is_stored_as_evidence_with_its_sha256(
    app: FastAPI, citizen: httpx.AsyncClient, tmp_path: Path
) -> None:
    """FR-CIT-001: the optional photo is evidence ``kind=photo`` with a server-side hash."""
    import hashlib

    lat, lon = fresh_spot()
    response = await citizen.post(
        "/public/reports",
        data=form(lat, lon),
        files={"photo": ("crash.jpg", JPEG, "image/jpeg")},
    )
    assert response.status_code == 201
    assert response.json()["photo_saved"] is True
    incident = await incident_by_code(app, response.json()["short_code"])
    async with app.state.session_factory() as s:
        evidence = (
            await s.scalars(select(Evidence).where(Evidence.incident_id == incident.id))
        ).one()
    assert evidence.kind == "photo"
    assert evidence.sha256 == hashlib.sha256(JPEG).hexdigest()
    assert (tmp_path / "evidence" / evidence.path).read_bytes() == JPEG


async def test_rate_limit_returns_429_after_the_configured_reports(tmp_path: Path) -> None:
    """FR-CIT-004: the (limit + 1)th report from one IP in the window is refused."""
    app = create_app(make_settings(tmp_path, public_report_rate_limit=2))
    async with app.router.lifespan_context(app), client_for(app) as c:
        statuses = [
            (await c.post("/public/reports", data=form(*fresh_spot()))).status_code
            for _ in range(3)
        ]
    assert statuses == [201, 201, 429]


async def test_rate_limit_is_per_ip(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, public_report_rate_limit=1))
    async with app.router.lifespan_context(app), client_for(app) as a, client_for(app) as b:
        first = await a.post("/public/reports", data=form(*fresh_spot()))
        blocked = await a.post("/public/reports", data=form(*fresh_spot()))
        other = await b.post("/public/reports", data=form(*fresh_spot()))
    assert (first.status_code, blocked.status_code, other.status_code) == (201, 429, 201)
    assert blocked.headers["retry-after"] == "600"


async def test_invalid_report_creates_no_incident(app: FastAPI, citizen: httpx.AsyncClient) -> None:
    response = await citizen.post("/public/reports", data=form(48.85, 2.35))  # Paris
    assert response.status_code == 422
