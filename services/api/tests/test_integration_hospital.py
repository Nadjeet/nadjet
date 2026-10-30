"""Integration: the hospital pre-alert view, Ready/Divert and acknowledgement (PostGIS, Redis).

Covers FR-HSP-001/002, FR-NTF-006, FR-INC-008, FR-SEC-002, E-10 and the live updates behind
"the pre-alert appears within 2 s and triage updates it".
"""

import asyncio
import json
import time
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
from nadjet_api.incidents.events import CHANNEL
from nadjet_api.incidents.models import IncidentEvent
from nadjet_api.main import create_app
from nadjet_api.notifications import inbound

from .conftest import MakeUser, make_settings
from .test_integration_dispatch import FakeQueue, login, new_incident, phone, recommend
from .test_integration_routing import SEED_DIR, FakeRouter

pytestmark = pytest.mark.integration


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


class Scene:
    """A dispatched incident with its operator, selected hospital and a user of that hospital."""

    def __init__(
        self,
        incident: dict[str, Any],
        operator: dict[str, str],
        hospital: dict[str, Any],
        other: dict[str, Any],
        unit: dict[str, Any],
        user: Any,
    ) -> None:
        self.incident, self.operator, self.hospital = incident, operator, hospital
        self.other, self.unit, self.user = other, unit, user
        self.id: str = incident["id"]
        self.url = f"/facilities/{hospital['id']}/prealerts"


async def dispatched(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser, **extra: Any
) -> tuple[Scene, dict[str, str]]:
    operator = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, operator, **extra)
    body = await recommend(client, operator, incident["id"])
    unit = body["units"][0]
    hospital = next(h for h in body["hospitals"] if h["ready_state"] == "ready")
    other = next(h for h in body["hospitals"] if h["id"] != hospital["id"])
    user = await make_user(session, role="hospital", facility_id=hospital["id"], phone=phone())
    response = await client.post(
        f"/incidents/{incident['id']}/dispatch",
        json={"unit_ids": [unit["id"]], "hospital_id": hospital["id"]},
        headers=operator,
    )
    assert response.status_code == 200, response.text
    return Scene(incident, operator, hospital, other, unit, user), await login(client, user)


def mine(items: list[dict[str, Any]], incident_id: str) -> list[dict[str, Any]]:
    """This scene's entries: the seeded hospitals keep the incidents of earlier runs."""
    return [a for a in items if a["incident_id"] == incident_id]


async def events(session: AsyncSession, incident_id: str) -> list[IncidentEvent]:
    rows = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == uuid.UUID(incident_id))
        .order_by(IncidentEvent.id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


# ------------------------------------------------------------------ the pre-alert


async def test_FR_HSP_001_the_selected_hospital_sees_the_pre_alert_at_once(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user, trapped=True)

    started = time.monotonic()
    response = await client.get(scene.url, headers=hospital)

    assert time.monotonic() - started < 2.0
    board = response.json()
    assert response.status_code == 200, response.text
    assert board["facility"]["id"] == scene.hospital["id"]
    assert mine(board["history"], scene.id) == []
    [alert] = mine(board["incoming"], scene.id)
    assert alert["incident_id"] == scene.id and alert["short_code"] == scene.incident["short_code"]
    assert alert["status"] == "dispatched" and alert["needs_extrication"] is True
    assert [u["callsign"] for u in alert["units"]] == [scene.unit["name"].split(" (")[0]]
    assert alert["eta_s"] > 0 and alert["expected_arrival_at"] > alert["dispatched_at"]
    assert alert["victims"] == {"red": 0, "yellow": 0, "green": 0, "black": 0, "total": 0}
    assert alert["acknowledged_at"] is None


async def test_FR_HSP_001_triage_updates_the_pre_alert_and_the_mass_casualty_flag(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    tags = ["red", "red", "yellow", "green", "black"]
    for tag in tags:
        body = {"triage_tag": tag, "avpu": "P", "pulse": 110, "spo2": 91, "bleeding": True}
        added = await client.post(
            f"/incidents/{scene.id}/casualties", json=body, headers=scene.operator
        )
        assert added.status_code == 201, added.text

    [alert] = mine((await client.get(scene.url, headers=hospital)).json()["incoming"], scene.id)

    assert alert["victims"] == {"red": 2, "yellow": 1, "green": 1, "black": 1, "total": 5}
    assert alert["mass_casualty"] is True  # five victims (FR-INC-008)
    assert len(alert["casualties"]) == 5
    first = alert["casualties"][0]
    assert (first["avpu"], first["pulse"], first["spo2"], first["bleeding"]) == ("P", 110, 91, True)


async def test_the_pre_alert_is_announced_live_to_the_hospital_only(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    """A dispatch publishes an update scoped to the selected facility (SSE, FR-MAP-002)."""
    operator = await login(client, await make_user(session, role="operator"))
    incident = await new_incident(client, operator)
    body = await recommend(client, operator, incident["id"])
    hospital_id = body["hospitals"][0]["id"]
    pubsub = app.state.redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        await client.post(
            f"/incidents/{incident['id']}/dispatch",
            json={"unit_ids": [body["units"][0]["id"]], "hospital_id": hospital_id},
            headers=operator,
        )
        messages: list[dict[str, Any]] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not messages:
            raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if raw is not None:
                message = json.loads(raw["data"])
                if message.get("incident_id") == incident["id"]:
                    messages.append(message)
    finally:
        await pubsub.aclose()
    assert messages and messages[0]["facilities"] == [hospital_id]


async def test_FR_SEC_002_other_hospitals_cannot_see_or_act_on_the_pre_alert(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    stranger_user = await make_user(
        session, role="hospital", facility_id=scene.other["id"], phone=phone()
    )
    stranger = await login(client, stranger_user)
    own_url = f"/facilities/{scene.other['id']}/prealerts"

    # Their own board does not list it; the incident itself is 404; the other board is 403.
    board = (await client.get(own_url, headers=stranger)).json()
    assert mine(board["incoming"], scene.id) == []
    assert (await client.get(f"/incidents/{scene.id}", headers=stranger)).status_code == 404
    assert (await client.get(scene.url, headers=stranger)).status_code == 403
    assert (
        await client.post(
            f"/facilities/{scene.hospital['id']}/readiness",
            json={"state": "divert"},
            headers=stranger,
        )
    ).status_code == 403
    ack = f"/facilities/{scene.other['id']}/prealerts/{scene.id}/ack"
    assert (await client.post(ack, headers=stranger)).status_code == 404
    assert (await client.get(scene.url)).status_code == 401
    assert (await client.get("/facilities/nope/prealerts", headers=hospital)).status_code == 404


async def test_a_police_station_is_not_a_hospital(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    police = (
        await session.execute(text("SELECT id FROM facilities WHERE kind = 'police' LIMIT 1"))
    ).scalar_one()
    assert (await client.get(f"/facilities/{police}/prealerts", headers=headers)).status_code == 404


async def test_operators_and_auditors_can_read_a_board_but_only_operators_change_it(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, _hospital = await dispatched(client, session, make_user)
    auditor = await login(client, await make_user(session, role="auditor"))
    responder = await login(client, await make_user(session, role="responder", agency="samu"))

    for reader in (scene.operator, auditor):
        board = (await client.get(scene.url, headers=reader)).json()
        assert len(mine(board["incoming"], scene.id)) == 1
    assert (await client.get(scene.url, headers=responder)).status_code == 403
    readiness = f"/facilities/{scene.hospital['id']}/readiness"
    assert (
        await client.post(readiness, json={"state": "divert"}, headers=auditor)
    ).status_code == 403


# ------------------------------------------------------------------ history


async def test_FR_HSP_001_the_arrival_moves_from_incoming_to_todays_history(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    for step in ("acknowledged", "en_route", "on_scene", "transporting", "at_hospital"):
        done = await client.post(
            f"/incidents/{scene.id}/status", json={"status": step}, headers=scene.operator
        )
        assert done.status_code == 200, done.text

    board = (await client.get(scene.url, headers=hospital)).json()

    assert mine(board["incoming"], scene.id) == []
    [arrival] = mine(board["history"], scene.id)
    assert arrival["status"] == "at_hospital"


async def test_an_arrival_from_an_earlier_day_leaves_the_board(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    """The board only loads what it shows: older arrivals are not history of the day."""
    scene, hospital = await dispatched(client, session, make_user)
    for step in ("acknowledged", "en_route", "on_scene", "transporting", "at_hospital"):
        done = await client.post(
            f"/incidents/{scene.id}/status", json={"status": step}, headers=scene.operator
        )
        assert done.status_code == 200, done.text
    await session.execute(
        text("UPDATE dispatches SET at = at - interval '2 days' WHERE incident_id = :i"),
        {"i": scene.id},
    )
    await session.commit()

    board = (await client.get(scene.url, headers=hospital)).json()

    assert mine(board["incoming"], scene.id) == []
    assert mine(board["history"], scene.id) == []


# ------------------------------------------------------------------ acknowledgement


async def test_FR_HSP_002_the_hospital_acknowledges_a_pre_alert_once(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    url = f"{scene.url}/{scene.id}/ack"

    first = await client.post(url, headers=hospital)
    again = await client.post(url, headers=hospital)

    assert (first.status_code, again.status_code) == (204, 204)
    [alert] = mine((await client.get(scene.url, headers=hospital)).json()["incoming"], scene.id)
    assert alert["acknowledged_at"] and alert["acknowledged_by"] == "IT"
    kinds = [e.kind for e in await events(session, scene.id)]
    assert kinds.count("prealert_acknowledged") == 1
    last = (await events(session, scene.id))[-1]
    assert last.actor_id == scene.user.id and last.payload == {"facility_id": scene.hospital["id"]}


async def test_acknowledging_an_unknown_or_finished_incident_is_refused(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    missing = f"{scene.url}/{uuid.uuid4()}/ack"
    assert (await client.post(missing, headers=hospital)).status_code == 404
    await session.execute(
        text("UPDATE incidents SET status = 'closed' WHERE id = :i"), {"i": scene.id}
    )
    await session.commit()
    done = await client.post(f"{scene.url}/{scene.id}/ack", headers=hospital)
    assert done.status_code == 409


# ------------------------------------------------------------------ Ready / Divert


async def test_FR_HSP_002_divert_from_the_screen_alerts_the_operators_and_reranks(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user, trapped=True)
    readiness = f"/facilities/{scene.hospital['id']}/readiness"

    response = await client.post(readiness, json={"state": "divert"}, headers=hospital)

    assert response.status_code == 200, response.text
    assert response.json()["ready_state"] == "divert"
    kinds = [(e.kind, e.actor_id) for e in await events(session, scene.id)]
    assert ("hospital_response", scene.user.id) in kinds
    alert = (await events(session, scene.id))[-1]
    assert alert.kind == "hospital_diverted"  # E-10
    proposed = alert.payload["proposed"]
    assert proposed and proposed["id"] != scene.hospital["id"]
    # Dispatch ranking reads the new state: the diverted hospital no longer comes first among
    # the capable ones.
    ranked = (await recommend(client, scene.operator, scene.id))["hospitals"]
    states = {h["id"]: h["ready_state"] for h in ranked}
    assert states.get(scene.hospital["id"], "divert") == "divert"
    assert (await client.get(scene.url, headers=hospital)).json()["facility"]["ready_state"] == (
        "divert"
    )

    back = await client.post(readiness, json={"state": "ready"}, headers=hospital)
    assert back.json()["ready_state"] == "ready"


async def test_repeating_the_same_state_changes_nothing(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, hospital = await dispatched(client, session, make_user)
    readiness = f"/facilities/{scene.hospital['id']}/readiness"
    await client.post(readiness, json={"state": "divert"}, headers=hospital)
    before = len(await events(session, scene.id))

    again = await client.post(readiness, json={"state": "divert"}, headers=hospital)

    assert again.status_code == 200 and again.json()["ready_state"] == "divert"
    assert len(await events(session, scene.id)) == before
    bad = await client.post(readiness, json={"state": "closed"}, headers=hospital)
    assert bad.status_code == 422


async def test_an_operator_can_set_the_state_of_any_hospital(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    scene, _hospital = await dispatched(client, session, make_user)
    response = await client.post(
        f"/facilities/{scene.other['id']}/readiness",
        json={"state": "divert"},
        headers=scene.operator,
    )
    assert response.status_code == 200 and response.json()["ready_state"] == "divert"


async def test_E_10_an_sms_divert_is_announced_live_like_the_screen(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    """The SMS path returns the facility change so the route can publish it (operator console)."""
    scene, _hospital = await dispatched(client, session, make_user)
    async with app.state.session_factory() as s:
        result = await inbound.handle_sms(
            s,
            app.state.signer,
            scene.user.phone,
            f"H {scene.incident['short_code']} DIVERT",
            uuid.uuid4().hex,
        )
        await s.commit()
    assert result.facility_states == {scene.hospital["id"]: "divert"}
    await asyncio.sleep(0)
