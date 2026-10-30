"""Integration: what the responder app relies on (FR-RSP-001..004, FR-INC-004, AC-RSP-004.1, E-09).

Idempotent status and triage (the offline queue retries after a lost answer), the hospital a
responder may see, and the gateway number behind the SMS fallback.
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units, seed_geo
from nadjet_api.incidents.models import Casualty, Incident, IncidentEvent
from nadjet_api.main import create_app

from .conftest import MakeUser, make_settings
from .test_integration_incidents import candidate, fresh_spot, ingest, login
from .test_integration_routing import SEED_DIR

pytestmark = pytest.mark.integration


def key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


async def dispatched(app: FastAPI, agency: str = "civil_protection") -> Incident:
    """A dispatched incident assigned to ``agency`` (what the dispatch API leaves behind)."""
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    async with app.state.session_factory() as s:
        await s.execute(
            text(
                "UPDATE incidents SET status = 'dispatched', "
                "assigned_agencies = ARRAY[:a]::varchar[] WHERE id = :i"
            ),
            {"a": agency, "i": incident.id},
        )
        await s.commit()
    return incident


async def status_events(session: AsyncSession, incident_id: uuid.UUID) -> list[IncidentEvent]:
    rows = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id, IncidentEvent.kind == "status_changed")
        .order_by(IncidentEvent.id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def casualties(session: AsyncSession, incident_id: uuid.UUID) -> list[Casualty]:
    rows = await session.scalars(
        select(Casualty)
        .where(Casualty.incident_id == incident_id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


# ------------------------------------------------------------------ idempotent status


async def test_FR_RSP_004_a_retried_status_is_applied_once(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    incident = await dispatched(app)
    url = f"/incidents/{incident.id}/status"
    ack = key()

    first = await client.post(url, json={"status": "acknowledged"}, headers={**headers, **ack})
    again = await client.post(url, json={"status": "acknowledged"}, headers={**headers, **ack})

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json()["status"] == "acknowledged"
    assert len(await status_events(session, incident.id)) == 1


async def test_a_replay_still_succeeds_after_the_incident_moved_on(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    """The answer to the first request was lost; the queue retries it after the next step."""
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    incident = await dispatched(app)
    url = f"/incidents/{incident.id}/status"
    ack = key()
    await client.post(url, json={"status": "acknowledged"}, headers={**headers, **ack})
    await client.post(url, json={"status": "en_route"}, headers={**headers, **key()})

    replay = await client.post(url, json={"status": "acknowledged"}, headers={**headers, **ack})

    assert replay.status_code == 200
    assert replay.json()["status"] == "en_route"  # the live state, not a rollback
    assert len(await status_events(session, incident.id)) == 2


async def test_the_same_status_without_a_key_is_still_an_illegal_transition(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    incident = await dispatched(app)
    url = f"/incidents/{incident.id}/status"
    assert (
        await client.post(url, json={"status": "acknowledged"}, headers=headers)
    ).status_code == 200
    assert (
        await client.post(url, json={"status": "acknowledged"}, headers=headers)
    ).status_code == 409


async def test_a_key_cannot_be_reused_for_another_action_or_incident(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    one, other = await dispatched(app), await dispatched(app)
    shared = key()
    await client.post(
        f"/incidents/{one.id}/status",
        json={"status": "acknowledged"},
        headers={**headers, **shared},
    )

    other_action = await client.post(
        f"/incidents/{one.id}/status", json={"status": "en_route"}, headers={**headers, **shared}
    )
    other_incident = await client.post(
        f"/incidents/{other.id}/status",
        json={"status": "acknowledged"},
        headers={**headers, **shared},
    )
    as_triage = await client.post(
        f"/incidents/{one.id}/casualties",
        json={"triage_tag": "red"},
        headers={**headers, **shared},
    )

    assert [r.status_code for r in (other_action, other_incident, as_triage)] == [409, 409, 409]
    assert len(await status_events(session, one.id)) == 1
    assert (await status_events(session, other.id)) == []
    assert (await casualties(session, one.id)) == []


async def test_idempotency_key_length_is_validated(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    incident = await dispatched(app)
    too_long = await client.post(
        f"/incidents/{incident.id}/status",
        json={"status": "acknowledged"},
        headers={**headers, "Idempotency-Key": "k" * 129},
    )
    assert too_long.status_code == 422


async def test_E_09_a_retried_status_from_another_agency_is_still_refused(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    gendarme = await login(client, await make_user(session, role="responder", agency="gendarmerie"))
    incident = await dispatched(app, agency="civil_protection")
    retry = key()
    for _ in range(2):
        response = await client.post(
            f"/incidents/{incident.id}/status",
            json={"status": "acknowledged"},
            headers={**gendarme, **retry},
        )
        assert response.status_code == 404
    assert await status_events(session, incident.id) == []


# ------------------------------------------------------------------ idempotent triage


async def test_AC_RSP_004_1_a_retried_triage_is_recorded_once(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    responder = await make_user(session, role="responder", agency="civil_protection")
    headers = await login(client, responder)
    incident = await dispatched(app)
    url = f"/incidents/{incident.id}/casualties"
    body = {"triage_tag": "red", "avpu": "P", "resp_rate": 34, "pulse": 120, "bleeding": True}
    queued = key()

    first = await client.post(url, json=body, headers={**headers, **queued})
    retry = await client.post(url, json=body, headers={**headers, **queued})

    assert (first.status_code, retry.status_code) == (201, 201)
    rows = await casualties(session, incident.id)
    assert len(rows) == 1
    assert (rows[0].triage_tag, rows[0].reported_by, rows[0].source) == (
        "red",
        responder.id,
        "app",
    )
    other = await client.post(url, json={"triage_tag": "green"}, headers={**headers, **key()})
    assert other.status_code == 201
    assert len(await casualties(session, incident.id)) == 2


async def test_FR_INC_004_triage_by_a_responder_recomputes_the_priority(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    incident = await dispatched(app)
    response = await client.post(
        f"/incidents/{incident.id}/casualties", json={"triage_tag": "red"}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["priority"] == 1


# ------------------------------------------------------------------ hospital view


@pytest.fixture
async def seeded(session: AsyncSession) -> None:
    await seed_geo(
        session,
        load_facilities(SEED_DIR / "facilities.csv"),
        load_capabilities(SEED_DIR / "capabilities.csv"),
        load_units(SEED_DIR / "units.csv"),
    )


async def test_FR_RSP_001_a_responder_sees_the_hospital_but_not_the_other_units(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    make_user: MakeUser,
    seeded: None,
) -> None:
    operator = await make_user(session, role="operator")
    incident = await dispatched(app)
    await session.execute(
        text(
            "INSERT INTO dispatches (incident_id, unit_id, eta_s, distance_m, dispatched_by) "
            "SELECT :i, id, 300, 4000, :u FROM units WHERE agency = 'civil_protection' LIMIT 1"
        ),
        {"i": incident.id, "u": operator.id},
    )
    await session.execute(
        text(
            "INSERT INTO dispatches (incident_id, hospital_id, eta_s, distance_m, dispatched_by) "
            "SELECT :i, id, 600, 9000, :u FROM facilities WHERE kind = 'hospital' LIMIT 1"
        ),
        {"i": incident.id, "u": operator.id},
    )
    await session.commit()
    url = f"/incidents/{incident.id}/dispatches"
    civil = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    gendarme = await login(client, await make_user(session, role="responder", agency="gendarmerie"))
    ops = await login(client, operator)

    seen = (await client.get(url, headers=civil)).json()
    assert [(d["kind"], d["deliveries"]) for d in seen] == [("hospital", [])]
    assert -90 < seen[0]["lat"] < 90 and -180 < seen[0]["lon"] < 180
    assert len((await client.get(url, headers=ops)).json()) == 2
    assert (await client.get(url, headers=gendarme)).status_code == 404
    assert (await client.get(url)).status_code == 401


# ------------------------------------------------------------------ gateway number


@pytest.fixture
async def numbered_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(tmp_path, sms_gateway_number="+213550000000"))
    async with application.router.lifespan_context(application):
        yield application


async def test_FR_RSP_004_the_gateway_number_is_given_to_signed_in_users(
    numbered_app: FastAPI, make_user: MakeUser
) -> None:
    async with numbered_app.state.session_factory() as s:
        user = await make_user(s, role="responder", agency="samu")
    transport = httpx.ASGITransport(app=numbered_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        headers = await login(c, user)
        configured = await c.get("/sms/gateway", headers=headers)
        anonymous = await c.get("/sms/gateway")
    assert (configured.status_code, configured.json()) == (200, {"number": "+213550000000"})
    assert anonymous.status_code == 401


async def test_the_gateway_number_is_null_when_unset(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="responder", agency="samu"))
    response: Any = await client.get("/sms/gateway", headers=headers)
    assert response.json() == {"number": None}
