"""Integration: recommendations, dispatch transaction, notifications, scoping, E-10 (PostGIS, Redis).

Road ETAs come from a deterministic fake router; the dispatch rules, DB writes, notification
rows and scoping run against the real local infrastructure.
Covers FR-DSP-001..004, FR-NTF-001/006/007, FR-SEC-002, E-10, AC-DSP-001.1, AC-SEC-002.1.
"""

import time
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit.models import AuditLog
from nadjet_api.dispatch.service import handle_hospital_divert, make_proposer
from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units, seed_geo
from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_api.main import create_app
from nadjet_api.notifications import inbound
from nadjet_api.notifications.grammar import normalize_phone
from nadjet_api.notifications.models import Notification
from nadjet_api.routing.router import Leg, Point, Route, RouterUnavailableError

from .conftest import PASSWORD, MakeUser, make_settings
from .test_integration_routing import SEED_DIR, FakeRouter

pytestmark = pytest.mark.integration

BOUMERDES = {"lat": 36.7620, "lon": 3.4770}


class FakeQueue:
    """Stands in for arq's pool: records the scheduled delivery jobs."""

    def __init__(self) -> None:
        self.jobs: list[str] = []

    async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> None:
        self.jobs.append(str(args[0]))


class DownRouter:
    async def table(self, sources: Sequence[Point], destinations: Sequence[Point]) -> Any:
        raise RouterUnavailableError("OSRM unreachable")

    async def route(self, origin: Point, destination: Point) -> Route | None:
        raise RouterUnavailableError("OSRM unreachable")


class NoRoadRouter(FakeRouter):
    async def route(self, origin: Point, destination: Point) -> Route | None:
        return None

    async def table(self, sources: Sequence[Point], destinations: Sequence[Point]) -> Any:
        return [[Leg(60.0, 900.0) for _ in destinations] for _ in sources]


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(tmp_path), road_router=FakeRouter())
    async with application.router.lifespan_context(application):
        real_pool = application.state.arq
        application.state.arq = FakeQueue()
        yield application
        application.state.arq = real_pool


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await seed_geo(
        session,
        load_facilities(SEED_DIR / "facilities.csv"),
        load_capabilities(SEED_DIR / "capabilities.csv"),
        load_units(SEED_DIR / "units.csv"),
    )
    await session.execute(text("UPDATE units SET status = 'available'"))
    await session.commit()


def phone() -> str:
    return f"+2135{uuid.uuid4().int % 10**8:08d}"


async def login(client: httpx.AsyncClient, user: Any) -> dict[str, str]:
    response = await client.post(
        "/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def new_incident(
    client: httpx.AsyncClient, headers: dict[str, str], **extra: Any
) -> dict[str, Any]:
    """A verified incident near Boumerdès (manual incidents start verified)."""
    response = await client.post(
        "/incidents",
        json={"location": dict(BOUMERDES), "vehicle_count": 2, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def recommend(
    client: httpx.AsyncClient, headers: dict[str, str], incident_id: str
) -> dict[str, Any]:
    response = await client.get(f"/incidents/{incident_id}/recommendations", headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def notifications_of(session: AsyncSession, incident_id: str) -> list[Notification]:
    rows = await session.scalars(
        select(Notification)
        .where(Notification.incident_id == uuid.UUID(incident_id))
        .execution_options(populate_existing=True)
    )
    return list(rows)


# ------------------------------------------------------------------ recommendations


async def test_AC_DSP_001_1_ranked_units_and_hospitals_appear_in_under_two_seconds(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)

    started = time.monotonic()
    body = await recommend(client, headers, incident["id"])

    assert time.monotonic() - started < 2.0
    assert len(body["units"]) >= 3 and len(body["hospitals"]) >= 3
    etas = [u["eta_s"] for u in body["units"]]
    assert etas == sorted(etas)
    assert all(u["agency"] in ("civil_protection", "samu") for u in body["units"])
    assert all(u["route_geojson"] and u["distance_m"] > 0 for u in body["units"])
    assert body["hospital_need"] in ("trauma", "emergency")


async def test_FR_DSP_002_hospitals_are_ranked_capable_then_ready_then_eta(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers, trapped=True)  # priority 1: needs trauma
    hospitals = (await recommend(client, headers, incident["id"]))["hospitals"]
    states = [(bool((h["capabilities"] or {}).get("trauma")), h["ready_state"]) for h in hospitals]
    assert states == sorted(states, key=lambda s: (not s[0], s[1] != "ready"))
    assert states[0][0], "a trauma-capable hospital must come first"


async def test_FR_DSP_001_units_follow_the_need_of_the_incident(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    await session.execute(
        text(
            "INSERT INTO units (id, facility_id, agency, callsign, geom, simulated) "
            "SELECT 'unit-test-samu', facility_id, 'samu', 'TEST-SAMU-1', "
            "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), true FROM units LIMIT 1 "
            "ON CONFLICT (id) DO UPDATE SET status = 'available'"
        ),
        {"lon": BOUMERDES["lon"] + 0.0005, "lat": BOUMERDES["lat"]},
    )
    await session.commit()
    headers = await login(client, await make_user(session, role="operator"))
    plain = await new_incident(client, headers)
    trapped = await new_incident(client, headers, trapped=True)

    try:
        plain_units = (await recommend(client, headers, plain["id"]))["units"]
        trapped_body = await recommend(client, headers, trapped["id"])
    finally:
        await session.execute(text("DELETE FROM units WHERE id = 'unit-test-samu'"))
        await session.commit()

    assert "unit-test-samu" in {u["id"] for u in plain_units}
    assert trapped_body["unit_agencies"] == ["civil_protection"]
    assert {u["agency"] for u in trapped_body["units"]} == {"civil_protection"}


async def test_recommendations_need_a_dispatch_role_a_dispatchable_incident_and_routing(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await login(client, await make_user(session, role="operator"))
    auditor = await login(client, await make_user(session, role="auditor"))
    incident = await new_incident(client, operator)
    url = f"/incidents/{incident['id']}/recommendations"

    assert (await client.get(url, headers=auditor)).status_code == 403
    assert (await client.get(url)).status_code == 401
    assert (
        await client.get(f"/incidents/{uuid.uuid4()}/recommendations", headers=operator)
    ).status_code == 404
    app.state.router = DownRouter()
    assert (await client.get(url, headers=operator)).status_code == 503
    app.state.router = None
    assert (await client.get(url, headers=operator)).status_code == 503
    app.state.router = FakeRouter()
    await session.execute(
        text("UPDATE incidents SET status = 'closed' WHERE id = :i"), {"i": incident["id"]}
    )
    await session.commit()
    assert (await client.get(url, headers=operator)).status_code == 409


# ------------------------------------------------------------------ dispatch


async def pick(
    client: httpx.AsyncClient, headers: dict[str, str], incident_id: str, units: int = 2
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = await recommend(client, headers, incident_id)
    return body["units"][:units], body["hospitals"][0]


async def test_FR_DSP_003_one_confirm_creates_dispatches_and_notifies(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    headers = await login(client, operator)
    incident = await new_incident(client, headers)
    units, hospital = await pick(client, headers, incident["id"])
    responder_phone, raw_phone = phone(), phone()
    responder = await make_user(
        session, role="responder", agency="civil_protection", phone=responder_phone
    )
    hospital_user = await make_user(
        session, role="hospital", facility_id=hospital["id"], phone=phone()
    )
    await session.execute(
        text("UPDATE units SET phone = :p WHERE id = :id"),
        {"p": responder_phone, "id": units[0]["id"]},
    )
    await session.execute(
        text("UPDATE units SET phone = :p WHERE id = :id"), {"p": raw_phone, "id": units[1]["id"]}
    )
    await session.commit()

    response = await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [u["id"] for u in units], "hospital_id": hospital["id"]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["incident"]["status"] == "dispatched"
    by_kind = {k: [d for d in body["dispatches"] if d["kind"] == k] for k in ("unit", "hospital")}
    assert len(by_kind["unit"]) == 2 and len(by_kind["hospital"]) == 1
    assert all(
        d["eta_s"] > 0 and d["route_geojson"]["type"] == "LineString" for d in body["dispatches"]
    )
    assert by_kind["hospital"][0]["resource_id"] == hospital["id"]

    rows = await notifications_of(session, incident["id"])
    sms = {(n.kind, n.recipient) for n in rows if n.channel == "sms"}
    assert ("alert", _norm(responder_phone)) in sms
    assert ("alert", _norm(raw_phone)) in sms
    assert ("prealert", _norm(hospital_user.phone or "")) in sms
    prealert = next(n for n in rows if n.kind == "prealert")
    assert prealert.payload.startswith("PRE|") and "|E" in prealert.payload
    assert {n.status for n in rows} == {"queued"}
    assert sorted(app.state.arq.jobs) == sorted(str(n.id) for n in rows)
    assert all(d["deliveries"] for d in body["dispatches"] if d["kind"] == "hospital")

    status_rows = (
        await session.execute(
            text("SELECT id, status FROM units WHERE id = ANY(:ids)"),
            {"ids": [u["id"] for u in units]},
        )
    ).all()
    assert {r.status for r in status_rows} == {"dispatched"}
    fresh = await session.get(Incident, uuid.UUID(incident["id"]), populate_existing=True)
    assert fresh is not None
    assert fresh.assigned_agencies == ["civil_protection"]
    assert fresh.assigned_facilities == [hospital["id"]]
    events = list(
        await session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == fresh.id)
            .order_by(IncidentEvent.id)
            .execution_options(populate_existing=True)
        )
    )
    last = events[-1]
    assert (last.kind, last.actor_id) == ("status_changed", operator.id)
    assert last.payload["to"] == "dispatched" and len(last.payload["dispatch"]["units"]) == 2
    audit = await session.scalar(
        select(AuditLog).where(
            AuditLog.action == "incident.dispatch", AuditLog.target_id == incident["id"]
        )
    )
    assert audit is not None and audit.actor_id == operator.id
    assert responder.phone  # the responder user exists and was matched by phone


def _norm(raw: str) -> str:
    return normalize_phone(raw)


async def test_FR_NTF_001_units_without_phone_alert_the_responders_of_their_agency(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    units, hospital = await pick(client, headers, incident["id"], units=1)
    responder = await make_user(session, role="responder", agency=units[0]["agency"], phone=phone())

    response = await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [units[0]["id"]], "hospital_id": hospital["id"]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    recipients = {n.recipient for n in await notifications_of(session, incident["id"])}
    assert _norm(responder.phone or "") in recipients


async def test_dispatch_refuses_without_writing_anything(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    units, hospital = await pick(client, headers, incident["id"])
    url = f"/incidents/{incident['id']}/dispatch"
    good = {"unit_ids": [units[0]["id"]], "hospital_id": hospital["id"]}

    async def untouched() -> None:
        count = (
            await session.execute(
                text("SELECT count(*) FROM dispatches WHERE incident_id = :i"),
                {"i": incident["id"]},
            )
        ).scalar_one()
        fresh = await session.get(Incident, uuid.UUID(incident["id"]), populate_existing=True)
        assert (count, fresh.status if fresh else None) == (0, "verified")  # type: ignore[union-attr]
        assert not await notifications_of(session, incident["id"])

    unknown_unit = await client.post(url, json={**good, "unit_ids": ["nope"]}, headers=headers)
    unknown_hospital = await client.post(url, json={**good, "hospital_id": "nope"}, headers=headers)
    twice = await client.post(url, json={**good, "unit_ids": [units[0]["id"]] * 2}, headers=headers)
    empty = await client.post(url, json={**good, "unit_ids": []}, headers=headers)
    assert (unknown_unit.status_code, unknown_hospital.status_code) == (422, 422)
    assert (twice.status_code, empty.status_code) == (409, 422)
    await untouched()

    await session.execute(
        text("UPDATE units SET status = 'busy' WHERE id = :id"), {"id": units[1]["id"]}
    )
    await session.commit()
    busy = await client.post(
        url, json={**good, "unit_ids": [units[0]["id"], units[1]["id"]]}, headers=headers
    )
    assert busy.status_code == 409 and "not available" in busy.json()["detail"]
    await untouched()

    app.state.router = DownRouter()
    assert (await client.post(url, json=good, headers=headers)).status_code == 503
    app.state.router = NoRoadRouter()
    no_road = await client.post(url, json=good, headers=headers)
    assert no_road.status_code == 409 and "no road route" in no_road.json()["detail"]
    app.state.router = FakeRouter()
    await untouched()


async def test_dispatch_needs_a_verified_incident_a_dispatch_role_and_happens_once(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    auditor = await login(client, await make_user(session, role="auditor"))
    incident = await new_incident(client, headers)
    units, hospital = await pick(client, headers, incident["id"], units=3)
    url = f"/incidents/{incident['id']}/dispatch"
    body = {"unit_ids": [units[0]["id"]], "hospital_id": hospital["id"]}

    assert (await client.post(url, json=body, headers=auditor)).status_code == 403
    assert (
        await client.post(f"/incidents/{uuid.uuid4()}/dispatch", json=body, headers=headers)
    ).status_code == 404
    assert (await client.post(url, json=body, headers=headers)).status_code == 200
    again = await client.post(
        url, json={"unit_ids": [units[1]["id"]], "hospital_id": hospital["id"]}, headers=headers
    )
    assert again.status_code == 409

    listing = await client.get(f"/incidents/{incident['id']}/dispatches", headers=headers)
    assert listing.status_code == 200 and len(listing.json()) == 2


async def test_closing_the_incident_frees_its_units(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    units, hospital = await pick(client, headers, incident["id"], units=1)
    await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [units[0]["id"]], "hospital_id": hospital["id"]},
        headers=headers,
    )
    for step in ("acknowledged", "en_route", "on_scene", "closed"):
        response = await client.post(
            f"/incidents/{incident['id']}/status", json={"status": step}, headers=headers
        )
        assert response.status_code == 200, response.text

    status = (
        await session.execute(
            text("SELECT status FROM units WHERE id = :id"), {"id": units[0]["id"]}
        )
    ).scalar_one()
    assert status == "available"
    again = await recommend(client, headers, (await new_incident(client, headers))["id"])
    assert units[0]["id"] in {u["id"] for u in again["units"]}


# ------------------------------------------------------------------ scoping


async def test_AC_SEC_002_1_dispatch_drives_what_responders_and_hospitals_see(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    body = await recommend(client, headers, incident["id"])
    units = [u for u in body["units"] if u["agency"] == "civil_protection"][:1]
    selected, other = body["hospitals"][0], body["hospitals"][1]
    civil = await login(
        client, await make_user(session, role="responder", agency="civil_protection")
    )
    gendarme = await login(client, await make_user(session, role="responder", agency="gendarmerie"))
    chosen = await login(
        client, await make_user(session, role="hospital", facility_id=selected["id"])
    )
    unchosen = await login(
        client, await make_user(session, role="hospital", facility_id=other["id"])
    )
    url = f"/incidents/{incident['id']}"

    async def sees(who: dict[str, str]) -> bool:
        listed = (await client.get("/incidents", headers=who, params={"limit": 200})).json()
        in_list = incident["id"] in {i["id"] for i in listed["items"]}
        detail = (await client.get(url, headers=who)).status_code
        assert in_list == (detail == 200)
        return in_list

    assert not any(
        [await sees(civil), await sees(gendarme), await sees(chosen), await sees(unchosen)]
    )

    dispatched = await client.post(
        f"{url}/dispatch",
        json={"unit_ids": [units[0]["id"]], "hospital_id": selected["id"]},
        headers=headers,
    )
    assert dispatched.status_code == 200, dispatched.text

    assert await sees(civil) is True
    assert await sees(chosen) is True
    assert await sees(gendarme) is False  # assigned only to Civil Protection
    assert await sees(unchosen) is False
    assert (await client.get(f"{url}/recommendations", headers=civil)).status_code == 403
    assert (await client.post(f"{url}/dispatch", json={}, headers=civil)).status_code == 403


# ------------------------------------------------------------------ E-10


async def test_E_10_divert_alerts_the_operators_and_proposes_the_next_hospital(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers, trapped=True)
    body = await recommend(client, headers, incident["id"])
    unit = body["units"][0]
    selected = next(h for h in body["hospitals"] if h["ready_state"] == "ready")
    hospital_phone = phone()
    await make_user(session, role="hospital", facility_id=selected["id"], phone=hospital_phone)
    await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [unit["id"]], "hospital_id": selected["id"]},
        headers=headers,
    )
    code = incident["short_code"]

    async with app.state.session_factory() as s:
        result = await inbound.handle_sms(
            s,
            app.state.signer,
            hospital_phone,
            f"H {code} DIVERT",
            uuid.uuid4().hex,
            make_proposer(s, app.state.router, app.state.settings.routing_urban_multiplier),
        )
        await s.commit()
    assert "divert recorded" in result.reply
    assert len(result.changes) >= 2  # the hospital reply and the operator alert

    events = list(
        await session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == uuid.UUID(incident["id"]))
            .order_by(IncidentEvent.id)
            .execution_options(populate_existing=True)
        )
    )
    alert = events[-1]
    assert alert.kind == "hospital_diverted"
    assert alert.payload["facility_id"] == selected["id"]
    proposed = alert.payload["proposed"]
    assert proposed and proposed["id"] != selected["id"] and proposed["eta_s"] > 0

    changed = await client.post(
        f"/incidents/{incident['id']}/hospital",
        json={"hospital_id": proposed["id"]},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    hospitals = [d for d in changed.json()["dispatches"] if d["kind"] == "hospital"]
    assert {(d["resource_id"], d["status"]) for d in hospitals} == {
        (selected["id"], "replaced"),
        (proposed["id"], "dispatched"),
    }
    fresh = await session.get(Incident, uuid.UUID(incident["id"]), populate_existing=True)
    assert fresh is not None and fresh.assigned_facilities == [proposed["id"]]
    same = await client.post(
        f"/incidents/{incident['id']}/hospital",
        json={"hospital_id": proposed["id"]},
        headers=headers,
    )
    assert same.status_code == 409


async def test_divert_of_an_unrelated_hospital_raises_no_alert(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    body = await recommend(client, headers, incident["id"])
    selected, other = body["hospitals"][0], body["hospitals"][1]
    await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [body["units"][0]["id"]], "hospital_id": selected["id"]},
        headers=headers,
    )
    async with app.state.session_factory() as s:
        changes = await handle_hospital_divert(s, app.state.signer, other["id"], None)
        await s.commit()
    assert changes == []


async def test_change_hospital_needs_a_dispatched_incident(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, headers)
    body = await recommend(client, headers, incident["id"])
    url = f"/incidents/{incident['id']}/hospital"
    assert (
        await client.post(url, json={"hospital_id": body["hospitals"][0]["id"]}, headers=headers)
    ).status_code == 409
    assert (await client.post(url, json={"hospital_id": "nope"}, headers=headers)).status_code in (
        409,
        422,
    )
