"""Integration: inbound SMS, notification delivery/retries, push subscriptions, CAP (PostGIS, Redis).

Covers FR-NTF-001..007, AC-NTF-005.1/005.2, E-07/E-08/E-09, FR-INC-009.
"""

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from lxml import etree
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.auth.models import User
from nadjet_api.incidents.models import Casualty, Incident, IncidentEvent
from nadjet_api.main import create_app
from nadjet_api.notifications import jobs
from nadjet_api.notifications import service as notifications
from nadjet_api.notifications.channels import SMS, DeliveryError, DeliveryRequest
from nadjet_api.notifications.models import (
    DELIVERED,
    FAILED,
    SENT,
    FacilityStatus,
    Notification,
    PushSubscription,
)

from .conftest import MakeUser, make_settings
from .test_integration_incidents import candidate, fresh_spot, ingest, login

pytestmark = pytest.mark.integration

SECRET = "whsec-test"
XSD = Path(__file__).parent / "data" / "cap-v1.2.xsd"
BASE_S, MAX_RETRIES = 30, 3


class FakeSms:
    """Records sends; ``fail`` makes every send raise (gateway offline)."""

    name = SMS
    reports_delivery = True

    def __init__(self) -> None:
        self.sent: list[DeliveryRequest] = []
        self.fail: DeliveryError | None = None

    async def send(self, request: DeliveryRequest) -> None:
        if self.fail:
            raise self.fail
        self.sent.append(request)


@pytest.fixture
async def sms() -> FakeSms:
    return FakeSms()


@pytest.fixture
async def gw_app(tmp_path: Path, sms: FakeSms) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(tmp_path, sms_webhook_secret=SECRET))
    async with application.router.lifespan_context(application):
        application.state.channels = {SMS: sms}
        yield application


@pytest.fixture
async def gw(gw_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gw_app), base_url="http://test"
    ) as c:
        yield c


def phone() -> str:
    return f"+2135{uuid.uuid4().int % 10**8:08d}"


def envelope(sender: str, body: str, message_id: str | None = None) -> dict[str, object]:
    return {
        "event": "sms:received",
        "id": uuid.uuid4().hex,
        "payload": {"messageId": message_id or uuid.uuid4().hex, "message": body, "sender": sender},
    }


async def post_sms(
    gw: httpx.AsyncClient, sender: str, body: str, message_id: str | None = None
) -> httpx.Response:
    return await gw.post(
        "/sms/inbound", params={"token": SECRET}, json=envelope(sender, body, message_id)
    )


async def dispatched_incident(
    app: FastAPI,
    *,
    agencies: tuple[str, ...] = ("civil_protection",),
    facilities: tuple[str, ...] = (),
) -> Incident:
    """A verified-then-dispatched incident assigned to ``agencies``/``facilities``."""
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    async with app.state.session_factory() as s:
        await s.execute(
            text(
                "UPDATE incidents SET status='dispatched', assigned_agencies=:a, "
                "assigned_facilities=:f WHERE id=:id"
            ),
            {"a": list(agencies), "f": list(facilities), "id": incident.id},
        )
        await s.commit()
    return incident


async def fresh(app: FastAPI, incident_id: uuid.UUID) -> Incident:
    async with app.state.session_factory() as s:
        row = await s.get(Incident, incident_id, populate_existing=True)
        assert row is not None
        return row


async def event_kinds(app: FastAPI, incident_id: uuid.UUID) -> list[str]:
    async with app.state.session_factory() as s:
        rows = await s.scalars(
            select(IncidentEvent.kind)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.id)
        )
        return list(rows)


# ---------------------------------------------------------------- inbound: webhook security


async def test_webhook_requires_a_valid_signature_or_token(gw: httpx.AsyncClient) -> None:
    body = json.dumps(envelope(phone(), "OK ABC")).encode()
    assert (await gw.post("/sms/inbound", content=body)).status_code == 401
    bad = await gw.post(
        "/sms/inbound",
        content=body,
        headers={"X-Signature": "00", "X-Timestamp": str(int(time.time()))},
    )
    assert bad.status_code == 401
    assert (
        await gw.post("/sms/inbound", params={"token": "nope"}, content=body)
    ).status_code == 401


async def test_webhook_accepts_the_gateway_hmac_signature(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)
    body = json.dumps(envelope(number, f"OK {incident.short_code}")).encode()
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), body + ts.encode(), hashlib.sha256).hexdigest()
    response = await gw.post(
        "/sms/inbound",
        content=body,
        headers={"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert (await fresh(gw_app, incident.id)).status == "acknowledged"


async def test_webhook_is_unavailable_without_a_configured_secret(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/sms/inbound", json=envelope(phone(), "OK ABC"))
    assert response.status_code == 503


async def test_an_empty_webhook_secret_counts_as_not_configured(tmp_path: Path) -> None:
    """``.env.example`` ships ``NADJET_SMS_WEBHOOK_SECRET=``; ``?token=`` must not match it."""
    application = create_app(make_settings(tmp_path, sms_webhook_secret=""))
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as c,
    ):
        response = await c.post(
            "/sms/inbound", params={"token": ""}, json=envelope(phone(), "OK ABC")
        )
    assert response.status_code == 503


# ---------------------------------------------------------------- inbound: status, triage, hospital


async def test_ok_reply_acknowledges_and_confirms_by_sms(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """AC-NTF-005.1 (webhook flow)."""
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)

    response = await post_sms(gw, number, f"ok {incident.short_code}")

    assert response.json() == {"status": "processed"}
    assert (await fresh(gw_app, incident.id)).status == "acknowledged"
    [reply] = sms.sent
    assert reply.recipient == number
    assert incident.short_code in reply.text
    assert "acknowledged" in reply.text
    assert len(reply.text) <= 160


async def test_status_codes_walk_the_lifecycle(
    gw: httpx.AsyncClient, gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)
    for code, expected in [
        ("OK", "acknowledged"),
        ("ER", "en_route"),
        ("OS", "on_scene"),
        ("TR", "transporting"),
        ("AH", "at_hospital"),
        ("CL", "closed"),
    ]:
        await post_sms(gw, number, f"{code} {incident.short_code}")
        assert (await fresh(gw_app, incident.id)).status == expected


async def test_illegal_status_move_changes_nothing_and_says_why(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)

    await post_sms(gw, number, f"OS {incident.short_code}")  # dispatched -> on_scene is illegal

    assert (await fresh(gw_app, incident.id)).status == "dispatched"
    assert "refused" in sms.sent[-1].text


async def test_triage_sms_creates_casualties_and_recomputes_priority(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """AC-NTF-005.2: ``T 7F3 R1 Y2 G0`` -> 3 casualty records, priority recomputed."""
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)
    before = incident.priority

    await post_sms(gw, number, f"T {incident.short_code} R1 Y2 G0")

    async with gw_app.state.session_factory() as s:
        tags = sorted(
            await s.scalars(select(Casualty.triage_tag).where(Casualty.incident_id == incident.id))
        )
        sources = set(
            await s.scalars(select(Casualty.source).where(Casualty.incident_id == incident.id))
        )
    assert tags == ["red", "yellow", "yellow"]
    assert sources == {"sms"}
    after = await fresh(gw_app, incident.id)
    assert after.priority == 1  # one red casualty
    assert before >= after.priority
    assert any(r["rule"] == "triage" for r in after.priority_reasons)
    assert "triage 3" in sms.sent[-1].text


async def test_hospital_reply_updates_facility_state(
    gw: httpx.AsyncClient, gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    facility = f"fac-{uuid.uuid4().hex[:8]}"
    await make_user(session, role="hospital", facility_id=facility, phone=number)
    incident = await dispatched_incident(gw_app, agencies=(), facilities=(facility,))

    await post_sms(gw, number, f"H {incident.short_code} READY")
    async with gw_app.state.session_factory() as s:
        row = await s.get(FacilityStatus, facility)
        assert row is not None
        assert row.state == "ready"
    await post_sms(gw, number, f"H {incident.short_code} DIVERT")
    async with gw_app.state.session_factory() as s:
        row = await s.get(FacilityStatus, facility, populate_existing=True)
        assert row is not None
        assert row.state == "divert"
    assert (await event_kinds(gw_app, incident.id)).count("hospital_response") == 2


async def test_a_responder_cannot_send_hospital_replies(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)

    await post_sms(gw, number, f"H {incident.short_code} READY")

    assert "not authorised" in sms.sent[-1].text


# ---------------------------------------------------------------- inbound: rejections


async def test_reply_from_an_unassigned_sender_is_rejected_and_operators_are_told(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """E-09: a responder of another agency, and an unknown phone, change nothing."""
    other = phone()
    await make_user(session, role="responder", agency="gendarmerie", phone=other)
    incident = await dispatched_incident(gw_app, agencies=("civil_protection",))

    for sender in (other, phone()):
        await post_sms(gw, sender, f"OK {incident.short_code}")
        assert "not authorised" in sms.sent[-1].text

    assert (await fresh(gw_app, incident.id)).status == "dispatched"
    assert (await event_kinds(gw_app, incident.id)).count("sms_rejected") == 2


async def test_inactive_user_is_not_recognised(
    gw: httpx.AsyncClient, gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(
        session, role="responder", agency="civil_protection", phone=number, active=False
    )
    incident = await dispatched_incident(gw_app)

    await post_sms(gw, number, f"OK {incident.short_code}")

    assert (await fresh(gw_app, incident.id)).status == "dispatched"


async def test_bad_syntax_gets_help_and_changes_nothing(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """E-08."""
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)
    events_before = await event_kinds(gw_app, incident.id)

    response = await post_sms(gw, number, "bonjour, on arrive")

    assert response.json() == {"status": "processed"}
    assert sms.sent[-1].text.startswith("Nadjet: OK|ER|OS|TR|AH|CL")
    assert await event_kinds(gw_app, incident.id) == events_before
    assert (await fresh(gw_app, incident.id)).status == "dispatched"


async def test_unknown_code_gets_help_and_changes_nothing(
    gw: httpx.AsyncClient, sms: FakeSms
) -> None:
    await post_sms(gw, phone(), "OK ZZZ")
    assert "unknown code ZZZ" in sms.sent[-1].text


async def test_redelivered_webhook_is_applied_once(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    number = phone()
    await make_user(session, role="responder", agency="civil_protection", phone=number)
    incident = await dispatched_incident(gw_app)
    message_id = uuid.uuid4().hex

    first = await post_sms(gw, number, f"OK {incident.short_code}", message_id)
    second = await post_sms(gw, number, f"OK {incident.short_code}", message_id)

    assert first.json() == {"status": "processed"}
    assert second.json() == {"status": "duplicate"}
    assert len(sms.sent) == 1
    assert (await event_kinds(gw_app, incident.id)).count("status_changed") == 1


async def test_a_phone_flooding_the_gateway_is_throttled(
    gw: httpx.AsyncClient, sms: FakeSms
) -> None:
    number = phone()
    statuses = [(await post_sms(gw, number, "hello")).json()["status"] for _ in range(32)]
    assert statuses[:30] == ["processed"] * 30
    assert statuses[30:] == ["throttled"] * 2
    assert len(sms.sent) == 30


# ---------------------------------------------------------------- inbound: citizen reports


async def test_accident_with_coordinates_creates_an_unverified_incident(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms
) -> None:
    """Issue AC: people=3, trapped -> P1 + extrication; AC-CIT-006.1 confirmation SMS."""
    lat, lon = (round(v, 5) for v in fresh_spot())  # the SMS carries 5 decimals
    number = phone()

    await post_sms(gw, number, f"ACCIDENT {lat:.5f},{lon:.5f} P3 C1")

    async with gw_app.state.session_factory() as s:
        incident = await s.scalar(
            select(Incident).where(
                Incident.lat.between(lat - 1e-5, lat + 1e-5),
                Incident.lon.between(lon - 1e-5, lon + 1e-5),
            )
        )
    assert incident is not None
    assert incident.status == "candidate"  # unverified
    assert incident.source == "citizen"
    assert (incident.lat, incident.lon) == (pytest.approx(lat), pytest.approx(lon))
    assert incident.people_reported == 3
    assert incident.trapped_reported is True
    assert incident.priority == 1
    assert incident.needs_extrication is True
    assert incident.location_text is None
    assert incident.short_code in sms.sent[-1].text


async def test_accident_without_coordinates_is_flagged_for_call_back(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms
) -> None:
    number = phone()
    label = f"RN24 Dellys {uuid.uuid4().hex[:6]}"

    await post_sms(gw, number, f"ACCIDENT {label}")

    async with gw_app.state.session_factory() as s:
        incident = await s.scalar(select(Incident).where(Incident.location_text == label))
        assert incident is not None
        created = await s.scalar(
            select(IncidentEvent.payload).where(
                IncidentEvent.incident_id == incident.id, IncidentEvent.kind == "created"
            )
        )
    assert (incident.lat, incident.lon) == (None, None)
    assert incident.status == "candidate"
    assert "callback_needed" in incident.quality_flags
    assert created is not None
    assert created["sms"]["phone"] == number  # the operator calls this number back
    assert incident.short_code in sms.sent[-1].text


async def test_citizen_report_merges_into_a_nearby_open_incident(
    gw: httpx.AsyncClient, gw_app: FastAPI
) -> None:
    """FR-INC-002 applies to SMS reports."""
    lat, lon = fresh_spot()
    existing = await ingest(gw_app, candidate(lat, lon))

    await post_sms(gw, phone(), f"ACCIDENT {lat:.5f},{lon:.5f} P2")

    after = await fresh(gw_app, existing.id)
    assert after.report_count == 2
    assert after.people_reported == 2


# ---------------------------------------------------------------- delivery and retries


async def alert_for(
    app: FastAPI, make_user: MakeUser, session: AsyncSession, *, number: str | None = None
) -> tuple[Incident, Notification, User]:
    user = await make_user(
        session, role="responder", agency="civil_protection", phone=number or phone()
    )
    incident = await dispatched_incident(app)
    async with app.state.session_factory() as s:
        live = await s.get(Incident, incident.id)
        assert live is not None
        [created] = await notifications.queue_alerts(s, live, [user])
        await s.commit()
        return incident, created, user


async def run(app: FastAPI, notification_id: uuid.UUID, channel: FakeSms) -> notifications.Outcome:
    async with app.state.session_factory() as s:
        outcome = await notifications.process(
            s,
            {SMS: channel},
            app.state.signer,
            notification_id,
            base_s=BASE_S,
            max_retries=MAX_RETRIES,
        )
        await s.commit()
        return outcome


async def row(app: FastAPI, notification_id: uuid.UUID) -> Notification:
    async with app.state.session_factory() as s:
        n = await s.get(Notification, notification_id, populate_existing=True)
        assert n is not None
        return n


async def test_alert_is_queued_once_per_incident_and_recipient(
    gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    """FR-NTF-007."""
    incident, first, user = await alert_for(gw_app, make_user, session)
    assert first.payload.startswith("ACC|P")
    assert first.payload.endswith(f"|{incident.short_code}")
    async with gw_app.state.session_factory() as s:
        live = await s.get(Incident, incident.id)
        assert live is not None
        again = await notifications.queue_alerts(s, live, [user])
        await s.commit()
        count = await s.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.incident_id == incident.id)
        )
    assert again == []
    assert count == 1


async def test_sms_is_sent_then_confirmed_by_the_delivery_report(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """FR-NTF-003: delivery status is recorded."""
    number = phone()
    _, notification, _ = await alert_for(gw_app, make_user, session, number=number)

    outcome = await run(gw_app, notification.id, sms)

    assert outcome.retry_in_s == BASE_S  # re-check in 30 s
    sent = await row(gw_app, notification.id)
    assert (sent.status, sent.attempts) == (SENT, 1)
    assert sms.sent[0].recipient == number
    assert sms.sent[0].ref == sent.provider_ref

    report = {"event": "sms:delivered", "payload": {"messageId": sent.provider_ref}}
    response = await gw.post("/sms/status", params={"token": SECRET}, json=report)
    assert response.json() == {"status": "processed"}
    assert (await row(gw_app, notification.id)).status == DELIVERED

    again = await run(gw_app, notification.id, sms)  # the delayed re-check
    assert again.retry_in_s is None
    assert len(sms.sent) == 1  # no duplicate send


async def test_undelivered_sms_is_retried_three_times_then_alerts_the_operator(
    gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """E-07 / FR-NTF-004: 30 s, then back-off, 3 retries, then an operator alert."""
    incident, notification, _ = await alert_for(gw_app, make_user, session)
    delays = []
    for _ in range(MAX_RETRIES + 1):  # first send + 3 retries, never delivered
        outcome = await run(gw_app, notification.id, sms)
        delays.append(outcome.retry_in_s)
        assert (await row(gw_app, notification.id)).status == SENT
    assert delays == [30, 60, 120, 240]
    assert len(sms.sent) == 4

    final = await run(gw_app, notification.id, sms)  # the last re-check gives up

    failed = await row(gw_app, notification.id)
    assert failed.status == FAILED
    assert failed.attempts == 4
    assert len(sms.sent) == 4  # no fifth send
    assert [c.type for c in final.changes] == ["incident.updated"]
    assert (await event_kinds(gw_app, incident.id))[-1] == "notification_failed"
    assert (await fresh(gw_app, incident.id)).version >= 2


async def test_gateway_offline_is_retried_and_finally_alerts(
    gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """E-07: gateway offline."""
    incident, notification, _ = await alert_for(gw_app, make_user, session)
    sms.fail = DeliveryError("gateway unreachable")
    for _ in range(MAX_RETRIES + 1):
        outcome = await run(gw_app, notification.id, sms)
        assert outcome.retry_in_s is not None
    await run(gw_app, notification.id, sms)

    failed = await row(gw_app, notification.id)
    assert failed.status == FAILED
    assert failed.last_error == "gateway unreachable"
    assert "notification_failed" in await event_kinds(gw_app, incident.id)


async def test_gateway_failure_report_triggers_a_resend_on_the_next_check(
    gw: httpx.AsyncClient, gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    _, notification, _ = await alert_for(gw_app, make_user, session)
    await run(gw_app, notification.id, sms)
    ref = (await row(gw_app, notification.id)).provider_ref
    await gw.post(
        "/sms/status",
        params={"token": SECRET},
        json={"event": "sms:failed", "payload": {"messageId": ref, "reason": "no signal"}},
    )

    await run(gw_app, notification.id, sms)

    assert len(sms.sent) == 2
    assert sms.sent[1].ref != sms.sent[0].ref


async def test_a_permanent_failure_is_not_retried_or_escalated(
    gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    incident, notification, _ = await alert_for(gw_app, make_user, session)
    sms.fail = DeliveryError("gone", permanent=True)

    outcome = await run(gw_app, notification.id, sms)

    assert outcome.retry_in_s is None
    assert (await row(gw_app, notification.id)).status == FAILED
    assert "notification_failed" not in await event_kinds(gw_app, incident.id)


async def test_unknown_delivery_report_is_ignored(gw: httpx.AsyncClient) -> None:
    report = {"event": "sms:delivered", "payload": {"messageId": uuid.uuid4().hex}}
    response = await gw.post("/sms/status", params={"token": SECRET}, json=report)
    assert response.json() == {"status": "ignored"}


# ---------------------------------------------------------------- push subscriptions


SUBSCRIPTION = {
    "endpoint": "https://push.example/send/abc",
    "keys": {"p256dh": "BPk", "auth": "au"},
}


async def test_push_subscription_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.post("/push/subscriptions", json=SUBSCRIPTION)).status_code == 401


async def test_push_subscription_is_stored_and_updated_per_endpoint(
    client: httpx.AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    user = await make_user(session, role="responder", agency="civil_protection")
    headers = await login(client, user)
    endpoint = f"https://push.example/send/{uuid.uuid4().hex}"
    body = {"endpoint": endpoint, "keys": {"p256dh": "k1", "auth": "a1"}}

    assert (await client.post("/push/subscriptions", json=body, headers=headers)).status_code == 201
    body["keys"] = {"p256dh": "k2", "auth": "a2"}
    assert (await client.post("/push/subscriptions", json=body, headers=headers)).status_code == 201

    rows = list(
        await session.scalars(
            select(PushSubscription)
            .where(PushSubscription.endpoint == endpoint)
            .execution_options(populate_existing=True)
        )
    )
    assert [(r.user_id, r.p256dh, r.auth) for r in rows] == [(user.id, "k2", "a2")]


async def test_push_subscription_rejects_non_https_endpoints(
    client: httpx.AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    user = await make_user(session, role="operator")
    body = {**SUBSCRIPTION, "endpoint": "http://insecure.example/x"}
    response = await client.post(
        "/push/subscriptions", json=body, headers=await login(client, user)
    )
    assert response.status_code == 422


class FakePush:
    name = "push"
    reports_delivery = False

    def __init__(self) -> None:
        self.sent: list[DeliveryRequest] = []

    async def send(self, request: DeliveryRequest) -> None:
        self.sent.append(request)


async def test_alerts_also_go_to_the_users_push_subscriptions(
    gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    """FR-NTF-001: SMS and push; push is delivered as soon as it is accepted."""
    user = await make_user(session, role="responder", agency="civil_protection", phone=phone())
    endpoint = f"https://push.example/send/{uuid.uuid4().hex}"
    session.add(PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="k", auth="a"))
    await session.commit()
    incident = await dispatched_incident(gw_app)
    async with gw_app.state.session_factory() as s:
        live = await s.get(Incident, incident.id)
        assert live is not None
        created = await notifications.queue_alerts(s, live, [user])
        await s.commit()
    assert sorted(n.channel for n in created) == ["push", "sms"]
    push = next(n for n in created if n.channel == "push")
    fake = FakePush()
    async with gw_app.state.session_factory() as s:
        outcome = await notifications.process(
            s, {"push": fake}, gw_app.state.signer, push.id, base_s=BASE_S, max_retries=MAX_RETRIES
        )
        await s.commit()
    assert outcome.retry_in_s is None
    assert fake.sent[0].recipient == endpoint
    assert fake.sent[0].meta == {"p256dh": "k", "auth": "a"}
    assert (await row(gw_app, push.id)).status == DELIVERED


# ---------------------------------------------------------------- CAP export


async def test_cap_endpoint_returns_a_valid_alert_in_arabic_and_french(
    client: httpx.AsyncClient, app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    """FR-INC-009."""
    user = await make_user(session, role="operator")
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))

    response = await client.get(
        f"/incidents/{incident.id}.cap.xml", headers=await login(client, user)
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/cap+xml")
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    document = etree.fromstring(response.content)
    schema.assertValid(document)
    ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
    assert document.xpath("//c:identifier/text()", namespaces=ns) == [str(incident.id)]
    assert sorted(document.xpath("//c:info/c:language/text()", namespaces=ns)) == ["ar", "fr"]


async def test_cap_endpoint_respects_the_data_scope(
    client: httpx.AsyncClient, app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    other_agency = await make_user(session, role="responder", agency="police")
    incident = await dispatched_incident(app, agencies=("civil_protection",))
    headers = await login(client, other_agency)

    assert (
        await client.get(f"/incidents/{incident.id}.cap.xml", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/incidents/{uuid.uuid4()}.cap.xml", headers=headers)
    ).status_code == 404
    assert (await client.get(f"/incidents/{incident.id}.cap.xml")).status_code == 401


async def test_cap_route_does_not_shadow_the_incident_detail_route(
    client: httpx.AsyncClient, app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    user = await make_user(session, role="operator")
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))

    response = await client.get(f"/incidents/{incident.id}", headers=await login(client, user))

    assert response.status_code == 200
    assert response.json()["short_code"] == incident.short_code


async def test_position_less_incident_cannot_be_alerted_yet(
    gw: httpx.AsyncClient, gw_app: FastAPI
) -> None:
    label = f"call-back {uuid.uuid4().hex[:6]}"
    await post_sms(gw, phone(), f"ACCIDENT {label}")
    async with gw_app.state.session_factory() as s:
        incident = await s.scalar(select(Incident).where(Incident.location_text == label))
        assert incident is not None
        with pytest.raises(ValueError, match="no position"):
            notifications.alert_text(incident)


# ---------------------------------------------------------------- worker job


class FakeQueue:
    """Stands in for arq's redis: records scheduled jobs; publishes are dropped."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> None:
        self.jobs.append((name, args, kwargs))

    async def publish(self, *_: object) -> None:
        return None


def worker_ctx(app: FastAPI, channel: FakeSms, queue: FakeQueue) -> dict[str, object]:
    return {
        "settings": app.state.settings,
        "session_factory": app.state.session_factory,
        "channels": {SMS: channel},
        "signer": app.state.signer,
        "redis": queue,
    }


async def test_worker_job_sends_and_schedules_the_delivery_check(
    gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    """FR-NTF-004: after a send the job re-runs itself in 30 s."""
    _, notification, _ = await alert_for(gw_app, make_user, session)
    queue = FakeQueue()

    await jobs.deliver_notification(worker_ctx(gw_app, sms, queue), str(notification.id))

    assert len(sms.sent) == 1
    assert queue.jobs == [
        (jobs.JOB, (str(notification.id),), {"_defer_by": timedelta(seconds=BASE_S)})
    ]


async def test_worker_job_does_not_reschedule_a_delivered_notification(
    gw_app: FastAPI, sms: FakeSms, make_user: MakeUser, session: AsyncSession
) -> None:
    _, notification, _ = await alert_for(gw_app, make_user, session)
    queue = FakeQueue()
    ctx = worker_ctx(gw_app, sms, queue)
    await jobs.deliver_notification(ctx, str(notification.id))
    async with gw_app.state.session_factory() as s:
        await notifications.record_receipt(
            s, (await row(gw_app, notification.id)).provider_ref or "", "sms:delivered"
        )
        await s.commit()
    queue.jobs.clear()

    await jobs.deliver_notification(ctx, str(notification.id))

    assert queue.jobs == []
    assert len(sms.sent) == 1


async def test_enqueue_all_schedules_one_job_per_notification(
    gw_app: FastAPI, make_user: MakeUser, session: AsyncSession
) -> None:
    _, notification, _ = await alert_for(gw_app, make_user, session)
    queue = FakeQueue()

    await jobs.enqueue_all(queue, [notification])  # type: ignore[arg-type]

    assert [job[1] for job in queue.jobs] == [(str(notification.id),)]
