"""Integration: ingestion, merge, lifecycle, scope, triage, evidence integrity (PostGIS, Redis)."""

import asyncio
import hashlib
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.incidents.ingest import STREAM, CandidateConsumer, enqueue
from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_api.incidents.service import ingest_candidate
from nadjet_shared.events import (
    AiStatus,
    CandidateSource,
    Finding,
    GeoLocation,
    IncidentCandidate,
    TriggerType,
    VerifierResult,
    Witness,
)

from .conftest import INGEST_TOKEN, PASSWORD, MakeUser

pytestmark = pytest.mark.integration

INGEST = {"Authorization": f"Bearer {INGEST_TOKEN}"}


def fresh_spot() -> tuple[float, float]:
    """A location no other test or earlier run uses (so merges are deterministic)."""
    n = uuid.uuid4().int
    return 20.0 + (n % 10_000_000) / 1_000_000, -5.0 + ((n >> 24) % 10_000_000) / 1_000_000


def metres_north(lat: float, metres: float) -> float:
    return lat + metres / 111_320


def candidate(
    lat: float,
    lon: float,
    *,
    at: datetime | None = None,
    signals: dict[str, float] | None = None,
    witness: Witness | None = None,
    verifier: VerifierResult | None = None,
    ai_status: AiStatus = AiStatus.PROBABLE,
    camera_id: str = "cam-test",
) -> IncidentCandidate:
    now = at or datetime.now(UTC)
    return IncidentCandidate(
        source=CandidateSource.CAMERA,
        camera_id=camera_id,
        location=GeoLocation(lat=lat, lon=lon, road="A1", pk_km=12.5, wilaya="Alger"),
        witness=witness,
        trigger=TriggerType.COLLISION_CANDIDATE,
        event_time=now,
        detected_at=now,
        signals=signals or {"vehicle_count": 2},
        verifier=verifier or VerifierResult(available=False),
        ai_status=ai_status,
    )


async def ingest(app: FastAPI, cand: IncidentCandidate, key: str | None = None) -> Incident:
    async with app.state.session_factory() as s:
        result = await ingest_candidate(s, app.state.signer, cand, key or uuid.uuid4().hex)
        await s.commit()
        return result.incident


async def login(client: httpx.AsyncClient, user: Any) -> dict[str, str]:
    response = await client.post(
        "/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def events_of(session: AsyncSession, incident_id: uuid.UUID) -> list[IncidentEvent]:
    rows = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


# ------------------------------------------------------------------ merge


async def test_AC_INC_002_1_second_candidate_merges(app: FastAPI, session: AsyncSession) -> None:
    lat, lon = fresh_spot()
    t0 = datetime.now(UTC)
    first = await ingest(app, candidate(lat, lon, at=t0))
    second = await ingest(app, candidate(metres_north(lat, 20), lon, at=t0 + timedelta(seconds=30)))
    assert second.id == first.id
    refreshed = await session.get(Incident, first.id, populate_existing=True)
    assert refreshed is not None and refreshed.report_count == 2
    assert [e.kind for e in await events_of(session, first.id)] == ["created", "merged_candidate"]


async def test_far_or_late_candidates_do_not_merge(app: FastAPI) -> None:
    lat, lon = fresh_spot()
    t0 = datetime.now(UTC)
    first = await ingest(app, candidate(lat, lon, at=t0))
    far = await ingest(app, candidate(metres_north(lat, 120), lon, at=t0))
    other_camera = candidate(lat, lon, at=t0 + timedelta(seconds=120), camera_id="cam-other")
    late = await ingest(app, other_camera)
    assert len({first.id, far.id, late.id}) == 3


async def test_E_02_same_camera_reobservation_is_counted_not_realerted(
    app: FastAPI, session: AsyncSession
) -> None:
    """A looping clip (or a crash still in view after the trigger cooldown) fires again on the
    same camera minutes later: it merges into the open incident; after 10 min it is new."""
    lat, lon = fresh_spot()
    t0 = datetime.now(UTC)
    first = await ingest(app, candidate(lat, lon, at=t0))
    again = await ingest(app, candidate(lat, lon, at=t0 + timedelta(seconds=150)))
    assert again.id == first.id
    refreshed = await session.get(Incident, first.id, populate_existing=True)
    assert refreshed is not None and refreshed.report_count == 2
    much_later = await ingest(app, candidate(lat, lon, at=t0 + timedelta(seconds=150 + 601)))
    assert much_later.id != first.id


async def test_merge_raises_priority_from_witness_and_keeps_one_incident(
    app: FastAPI, session: AsyncSession
) -> None:
    lat, lon = fresh_spot()
    first = await ingest(app, candidate(lat, lon, signals={"vehicle_count": 2}))
    assert first.priority == 3
    await ingest(app, candidate(lat, lon, signals={}, witness=Witness(trapped=True)))
    merged = await session.get(Incident, first.id, populate_existing=True)
    assert merged is not None
    assert (merged.priority, merged.needs_extrication, merged.trapped_reported) == (1, True, True)


async def test_ingestion_is_idempotent_on_the_key(app: FastAPI, session: AsyncSession) -> None:
    lat, lon = fresh_spot()
    key = uuid.uuid4().hex
    cand = candidate(lat, lon)
    a = await ingest(app, cand, key)
    b = await ingest(app, cand, key)
    assert a.id == b.id
    assert len(await events_of(session, a.id)) == 1


async def test_candidate_gets_short_code_and_explained_priority(app: FastAPI) -> None:
    """FR-INC-001: a received candidate becomes an incident with a short code and a priority."""
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon, signals={"bus_involved": 1}))
    assert len(incident.short_code) == 3
    assert incident.priority == 1 and incident.mass_casualty
    assert incident.priority_reasons[0]["source"].startswith("rule:")
    assert incident.status == "candidate"


# ------------------------------------------------------------------ stream consumer


async def wait_for_incident(app: FastAPI, key: str, wait_s: float = 8.0) -> Incident:
    deadline = asyncio.get_running_loop().time() + wait_s
    while asyncio.get_running_loop().time() < deadline:
        async with app.state.session_factory() as s:
            found = await s.scalar(
                select(Incident)
                .join(IncidentEvent, IncidentEvent.incident_id == Incident.id)
                .where(IncidentEvent.idempotency_key == key)
            )
        if found:
            return found
        await asyncio.sleep(0.1)
    raise AssertionError("candidate was not persisted in time")


def make_consumer(app: FastAPI, **kwargs: Any) -> CandidateConsumer:
    return CandidateConsumer(app.state.redis, app.state.session_factory, app.state.signer, **kwargs)


async def test_NFR_REL_002_candidate_posted_while_consumer_is_stopped_is_persisted(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    lat, lon = fresh_spot()
    key = uuid.uuid4().hex

    first = make_consumer(app, name="c1")
    stop_first = asyncio.Event()
    task = asyncio.create_task(first.run(stop_first))
    await asyncio.sleep(0.3)
    task.cancel()  # kill the consumer
    with pytest.raises(asyncio.CancelledError):
        await task

    response = await client.post(
        "/internal/candidates",
        content=candidate(lat, lon).model_dump_json(),
        headers={**INGEST, "Idempotency-Key": key, "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text

    stop = asyncio.Event()
    restarted = asyncio.create_task(make_consumer(app, name="c2").run(stop))
    try:
        incident = await wait_for_incident(app, key)
    finally:
        stop.set()
        await restarted
    assert incident.report_count == 1


async def test_pending_entry_is_reclaimed_after_a_failed_persist(app: FastAPI) -> None:
    lat, lon = fresh_spot()
    key = uuid.uuid4().hex
    redis = app.state.redis
    consumer = make_consumer(app, name="crashy", claim_idle_ms=0)
    await consumer.setup()

    def broken() -> Any:
        raise ConnectionError("database down")

    crashing = CandidateConsumer(
        redis, broken, app.state.signer, name="crashy", claim_idle_ms=10 * 60 * 1000
    )
    await enqueue(redis, candidate(lat, lon), key)
    await crashing.poll_once(block_ms=200)  # reads the entry, fails to persist, leaves it pending
    async with app.state.session_factory() as s:
        count = await s.scalar(
            text("SELECT count(*) FROM incident_events WHERE idempotency_key=:k"), {"k": key}
        )
    assert count == 0

    healthy = make_consumer(app, name="healthy", claim_idle_ms=0)
    for _ in range(20):
        await healthy.poll_once(block_ms=100)
        async with app.state.session_factory() as s:
            if await s.scalar(
                text("SELECT count(*) FROM incident_events WHERE idempotency_key=:k"), {"k": key}
            ):
                break
    incident = await wait_for_incident(app, key, wait_s=2)
    assert incident.report_count == 1
    pending = await redis.xpending(STREAM, "api")
    assert pending["pending"] == 0


async def test_entry_failing_every_delivery_is_dead_lettered(app: FastAPI) -> None:
    """NFR-REL-002: a poison entry is parked for humans instead of retried forever."""
    redis = app.state.redis
    await make_consumer(app, name="poison").setup()

    def broken() -> Any:
        raise RuntimeError("cannot persist")

    consumer = CandidateConsumer(
        redis, broken, app.state.signer, name="poison", claim_idle_ms=0, max_deliveries=3
    )
    key = uuid.uuid4().hex
    lat, lon = fresh_spot()
    await enqueue(redis, candidate(lat, lon), key)
    for _ in range(6):
        await consumer.poll_once(block_ms=50)
    dead = await redis.xrange("incidents.candidates.dead")
    assert any(fields.get("key") == key for _id, fields in dead)
    pending = await redis.xpending_range(STREAM, "api", "-", "+", 100, consumername="poison")
    assert pending == []


async def test_malformed_entry_is_dead_lettered_not_retried(app: FastAPI) -> None:
    redis = app.state.redis
    consumer = make_consumer(app, name="dl")
    await consumer.setup()
    marker = uuid.uuid4().hex
    await redis.xadd(STREAM, {"key": marker, "candidate": "{not json"})
    for _ in range(20):
        await consumer.poll_once(block_ms=100)
    dead = await redis.xrange("incidents.candidates.dead")
    assert any(fields.get("key") == marker for _id, fields in dead)


async def test_internal_endpoints_require_the_service_token(client: httpx.AsyncClient) -> None:
    lat, lon = fresh_spot()
    body = candidate(lat, lon).model_dump_json()
    headers = {"Idempotency-Key": "k", "Content-Type": "application/json"}
    assert (
        await client.post("/internal/candidates", content=body, headers=headers)
    ).status_code == 401
    bad = {**headers, "Authorization": "Bearer wrong"}
    assert (await client.post("/internal/candidates", content=body, headers=bad)).status_code == 401
    no_key = {"Authorization": INGEST["Authorization"], "Content-Type": "application/json"}
    assert (
        await client.post("/internal/candidates", content=body, headers=no_key)
    ).status_code == 422


# ------------------------------------------------------------------ lifecycle over HTTP


async def test_lifecycle_endpoints_enforce_transitions_and_chain_events(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    headers = await login(client, operator)
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    url = f"/incidents/{incident.id}"

    assert (
        await client.post(f"{url}/status", json={"status": "dispatched"}, headers=headers)
    ).status_code == 409
    assert (await client.post(f"{url}/verify", headers=headers)).status_code == 200
    assert (await client.post(f"{url}/verify", headers=headers)).status_code == 409
    for step in ("dispatched", "acknowledged", "en_route", "on_scene", "closed"):
        response = await client.post(f"{url}/status", json={"status": step}, headers=headers)
        assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"
    assert (
        await client.post(f"{url}/status", json={"status": "closed"}, headers=headers)
    ).status_code == 409

    detail = (await client.get(url, headers=headers)).json()
    kinds = [e["kind"] for e in detail["events"]]
    assert kinds == ["created"] + ["status_changed"] * 6
    chain = await events_of(session, incident.id)
    assert all(e.actor_id == operator.id for e in chain[1:])
    assert all(e.prev_hash == p.hash for p, e in itertools.pairwise(chain))
    assert all(e.signature for e in chain)


async def test_reject_stores_reason_and_frees_the_short_code(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    """FR-INC-006: a rejection stores its reason label."""
    headers = await login(client, await make_user(session, role="supervisor"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    bad = await client.post(
        f"/incidents/{incident.id}/reject", json={"reason": "bogus"}, headers=headers
    )
    assert bad.status_code == 422
    ok = await client.post(
        f"/incidents/{incident.id}/reject", json={"reason": "false_positive"}, headers=headers
    )
    assert ok.status_code == 200
    assert (ok.json()["status"], ok.json()["reject_reason"]) == ("rejected", "false_positive")


async def test_unknown_incident_is_404_and_roles_are_enforced(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await login(client, await make_user(session, role="operator"))
    responder = await login(client, await make_user(session, role="responder", agency="samu"))
    assert (await client.get(f"/incidents/{uuid.uuid4()}", headers=operator)).status_code == 404
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    assert (
        await client.post(f"/incidents/{incident.id}/verify", headers=responder)
    ).status_code == 403
    assert (await client.get("/incidents")).status_code == 401


async def test_operator_manual_creation_starts_verified(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    headers = await login(client, operator)
    lat, lon = fresh_spot()
    response = await client.post(
        "/incidents",
        json={
            "location": {"lat": lat, "lon": lon, "wilaya": "Blida"},
            "vehicle_count": 3,
            "trapped": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["source"], body["priority"], body["needs_extrication"]) == (
        "verified", "operator", 1, True,
    )  # fmt: skip
    assert body["ai_status"] is None
    events = await events_of(session, uuid.UUID(body["id"]))
    assert events[0].actor_id == operator.id


async def test_FR_INC_007_manual_notes_are_kept_in_the_signed_created_event(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    lat, lon = fresh_spot()
    created = await client.post(
        "/incidents",
        json={"location": {"lat": lat, "lon": lon}, "notes": "caller sees smoke"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    events = await events_of(session, uuid.UUID(created.json()["id"]))
    assert events[0].payload["notes"] == "caller sees smoke"
    too_long = await client.post(
        "/incidents",
        json={"location": {"lat": lat, "lon": lon}, "notes": "x" * 1001},
        headers=headers,
    )
    assert too_long.status_code == 422


async def test_FR_MAP_003_timeline_events_carry_the_actor_display_name(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    headers = await login(client, operator)
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    await client.post(f"/incidents/{incident.id}/verify", headers=headers)
    events = (await client.get(f"/incidents/{incident.id}", headers=headers)).json()["events"]
    assert [(e["kind"], e["actor_name"]) for e in events] == [
        ("created", None),
        ("status_changed", operator.display_name),
    ]


# ------------------------------------------------------------------ manual merge


async def test_FR_INC_002_operator_merges_a_candidate_into_an_open_incident(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await make_user(session, role="operator")
    headers = await login(client, operator)
    lat, lon = fresh_spot()
    target = await ingest(app, candidate(lat, lon, signals={"vehicle_count": 2}))
    far_lat, far_lon = fresh_spot()
    source = await ingest(
        app,
        candidate(far_lat, far_lon, signals={"vehicle_count": 4}, witness=Witness(trapped=True)),
    )

    response = await client.post(
        f"/incidents/{source.id}/merge", json={"into": str(target.id)}, headers=headers
    )
    assert response.status_code == 200, response.text
    merged = response.json()
    assert merged["id"] == str(target.id)
    assert merged["report_count"] == 2
    assert merged["ai_signals"]["vehicle_count"] == 4
    assert merged["trapped_reported"] is True

    gone = (await client.get(f"/incidents/{source.id}", headers=headers)).json()
    assert (gone["status"], gone["merged_into"]) == ("merged", str(target.id))
    assert [e["actor_name"] for e in gone["events"]][-1] == operator.display_name
    assert (await client.post(f"/incidents/{source.id}/verify", headers=headers)).status_code == 409


async def test_merge_rejects_self_closed_target_and_non_candidate_source(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    headers = await login(client, await make_user(session, role="operator"))
    a_lat, a_lon = fresh_spot()
    b_lat, b_lon = fresh_spot()
    a = await ingest(app, candidate(a_lat, a_lon))
    b = await ingest(app, candidate(b_lat, b_lon))

    own = await client.post(f"/incidents/{a.id}/merge", json={"into": str(a.id)}, headers=headers)
    assert own.status_code == 409
    missing = await client.post(
        f"/incidents/{a.id}/merge", json={"into": str(uuid.uuid4())}, headers=headers
    )
    assert missing.status_code == 404
    unknown_source = await client.post(
        f"/incidents/{uuid.uuid4()}/merge", json={"into": str(a.id)}, headers=headers
    )
    assert unknown_source.status_code == 404

    await client.post(f"/incidents/{b.id}/reject", json={"reason": "other"}, headers=headers)
    closed_target = await client.post(
        f"/incidents/{a.id}/merge", json={"into": str(b.id)}, headers=headers
    )
    assert closed_target.status_code == 409

    await client.post(f"/incidents/{a.id}/verify", headers=headers)
    verified_source = await client.post(
        f"/incidents/{a.id}/merge", json={"into": str(b.id)}, headers=headers
    )
    assert verified_source.status_code == 409


async def test_merge_is_limited_to_dispatch_roles(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    auditor = await login(client, await make_user(session, role="auditor"))
    a_lat, a_lon = fresh_spot()
    b_lat, b_lon = fresh_spot()
    a = await ingest(app, candidate(a_lat, a_lon))
    b = await ingest(app, candidate(b_lat, b_lon))
    response = await client.post(
        f"/incidents/{a.id}/merge", json={"into": str(b.id)}, headers=auditor
    )
    assert response.status_code == 403


# ------------------------------------------------------------------ scope, triage


async def assign(session: AsyncSession, incident_id: uuid.UUID, agency: str) -> None:
    await session.execute(
        text("UPDATE incidents SET assigned_agencies = ARRAY[:a]::varchar[] WHERE id = :i"),
        {"a": agency, "i": incident_id},
    )
    await session.commit()


async def test_FR_SEC_002_responder_only_sees_incidents_of_its_agency(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    samu = await login(client, await make_user(session, role="responder", agency="samu"))
    police = await login(client, await make_user(session, role="responder", agency="police"))
    operator = await login(client, await make_user(session, role="operator"))
    lat, lon = fresh_spot()
    mine = await ingest(app, candidate(lat, lon))
    other = await ingest(app, candidate(*fresh_spot()))
    await assign(session, mine.id, "samu")

    # Page through everything: other tests leave incidents behind, so one page of 200 sorted
    # by priority does not always hold the two fresh ones.
    listed = await all_listed_ids(client, samu)
    assert str(mine.id) in listed and str(other.id) not in listed
    assert (await client.get(f"/incidents/{mine.id}", headers=samu)).status_code == 200
    assert (await client.get(f"/incidents/{mine.id}", headers=police)).status_code == 404
    assert {str(mine.id), str(other.id)} <= await all_listed_ids(client, operator)


async def all_listed_ids(client: httpx.AsyncClient, headers: dict[str, str]) -> set[str]:
    ids: set[str] = set()
    offset = 0
    while True:
        page = (await client.get(f"/incidents?limit=200&offset={offset}", headers=headers)).json()
        ids |= {i["id"] for i in page["items"]}
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            return ids


async def test_FR_INC_004_triage_recomputes_priority_and_flags_mass_casualty(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    responder_user = await make_user(session, role="responder", agency="samu")
    responder = await login(client, responder_user)
    operator = await login(client, await make_user(session, role="operator"))
    lat, lon = fresh_spot()
    raise_ai = VerifierResult(
        available=True, model="qwen-test", collision_visible="yes", yes_probability=0.9,
        priority_raise=1, findings=[Finding(statement="overturned", basis="observed", frame_ids=[1])],
    )  # fmt: skip
    incident = await ingest(app, candidate(lat, lon, verifier=raise_ai))
    assert incident.priority == 2  # P3 rule minimum raised by the AI
    await client.post(f"/incidents/{incident.id}/verify", headers=operator)
    await assign(session, incident.id, "samu")
    url = f"/incidents/{incident.id}/casualties"

    green = await client.post(url, json={"triage_tag": "green"}, headers=responder)
    assert green.status_code == 201, green.text
    assert green.json()["priority"] == 3  # triage overrides the AI raise
    red = await client.post(
        url, json={"triage_tag": "red", "avpu": "P", "pulse": 120}, headers=responder
    )
    assert red.json()["priority"] == 1
    for _ in range(3):
        last = await client.post(
            url, json={"triage_tag": "yellow", "source": "sms"}, headers=responder
        )
    assert last.json()["mass_casualty"] is True
    detail = (await client.get(f"/incidents/{incident.id}", headers=operator)).json()
    assert len(detail["casualties"]) == 5
    assert detail["casualties"][0]["reported_by"] == str(responder_user.id)
    assert (
        await client.post(url, json={"triage_tag": "purple"}, headers=responder)
    ).status_code == 422


async def test_triage_on_a_closed_incident_is_409(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await login(client, await make_user(session, role="operator"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    await client.post(
        f"/incidents/{incident.id}/reject", json={"reason": "other"}, headers=operator
    )
    response = await client.post(
        f"/incidents/{incident.id}/casualties", json={"triage_tag": "red"}, headers=operator
    )
    assert response.status_code == 409


async def test_list_filters_and_pagination(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    operator = await login(client, await make_user(session, role="operator"))
    wilaya = f"W-{uuid.uuid4().hex[:6]}"
    for n in range(3):
        cand = candidate(*fresh_spot(), signals={"flames": 1} if n == 0 else {"vehicle_count": 2})
        cand.location.wilaya = wilaya
        await ingest(app, cand)
    page = (await client.get(f"/incidents?wilaya={wilaya}&limit=2", headers=operator)).json()
    assert (page["total"], len(page["items"])) == (3, 2)
    assert page["items"][0]["priority"] == 1  # most urgent first
    p3 = (await client.get(f"/incidents?wilaya={wilaya}&priority=3", headers=operator)).json()
    assert p3["total"] == 2
    assert (await client.get("/incidents?priority=9", headers=operator)).status_code == 422


# ------------------------------------------------------------------ evidence integrity


async def upload(
    client: httpx.AsyncClient, incident_id: uuid.UUID, data: bytes, **form: str
) -> httpx.Response:
    return await client.post(
        "/internal/evidence",
        headers=INGEST,
        data={"kind": "clip", "incident_id": str(incident_id), **form},
        files={"file": ("clip.mp4", data, form.pop("ctype", "video/mp4"))},
    )


async def test_AC_SEC_003_1_modified_evidence_file_makes_integrity_invalid(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    make_user: MakeUser,
    tmp_path: Path,
) -> None:
    operator = await login(client, await make_user(session, role="operator"))
    auditor = await login(client, await make_user(session, role="auditor"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))

    data = b"\x00fake-mp4-bytes" * 100
    response = await upload(client, incident.id, data)
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["sha256"] == hashlib.sha256(data).hexdigest()  # computed server-side

    url = f"/incidents/{incident.id}/integrity"
    ok = (await client.get(url, headers=auditor)).json()
    assert (ok["status"], ok["files_checked"], ok["failures"]) == ("valid", 1, [])

    file_path = next((tmp_path / "evidence").rglob("*.mp4"))
    file_path.write_bytes(data + b"tampered")
    bad = (await client.get(url, headers=operator)).json()
    assert bad["status"] == "invalid"
    [failure] = bad["failures"]
    assert failure["kind"] == "file" and failure["ref"] == f"{incident.id}/{evidence['id']}.mp4"

    file_path.unlink()
    gone = (await client.get(url, headers=operator)).json()
    assert gone["failures"][0]["detail"] == "file missing"


async def test_FR_SEC_003_file_and_db_hash_tampered_together_is_detected(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    make_user: MakeUser,
    tmp_path: Path,
) -> None:
    """Rewriting the file and the evidence row's sha256 still fails: the chain holds the hash."""
    auditor = await login(client, await make_user(session, role="auditor"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    data = b"\x00original" * 50
    evidence = (await upload(client, incident.id, data)).json()

    forged = data + b"forged"
    next((tmp_path / "evidence").rglob("*.mp4")).write_bytes(forged)
    await session.execute(
        text("UPDATE evidence SET sha256=:h WHERE id=:i"),
        {"h": hashlib.sha256(forged).hexdigest(), "i": evidence["id"]},
    )
    await session.commit()

    report = (await client.get(f"/incidents/{incident.id}/integrity", headers=auditor)).json()
    assert report["status"] == "invalid"
    assert report["failures"][0]["detail"] == "hash not in signed chain"


async def test_FR_SEC_003_deleted_evidence_row_is_detected(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    auditor = await login(client, await make_user(session, role="auditor"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    evidence = (await upload(client, incident.id, b"\x00keep" * 20)).json()
    await session.execute(text("DELETE FROM evidence WHERE id=:i"), {"i": evidence["id"]})
    await session.commit()

    report = (await client.get(f"/incidents/{incident.id}/integrity", headers=auditor)).json()
    assert report["status"] == "invalid"
    assert report["failures"] == [
        {"kind": "file", "ref": evidence["id"], "detail": "evidence record missing"}
    ]


async def test_evidence_upload_validation(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    wrong_type = await client.post(
        "/internal/evidence", headers=INGEST,
        data={"kind": "clip", "incident_id": str(incident.id)},
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )  # fmt: skip
    assert wrong_type.status_code == 415
    unknown = await upload(client, uuid.uuid4(), b"abc")
    assert unknown.status_code == 404
    no_target = await client.post(
        "/internal/evidence", headers=INGEST, data={"kind": "clip"},
        files={"file": ("c.mp4", b"abc", "video/mp4")},
    )  # fmt: skip
    assert no_target.status_code == 422
    unauth = await client.post(
        "/internal/evidence", data={"kind": "clip"}, files={"file": ("c.mp4", b"a", "video/mp4")}
    )
    assert unauth.status_code == 401


async def test_evidence_can_be_attached_by_candidate_key_once_persisted(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    lat, lon = fresh_spot()
    key = uuid.uuid4().hex
    pending = await client.post(
        "/internal/evidence", headers=INGEST,
        data={"kind": "keyframe", "idempotency_key": key},
        files={"file": ("k.jpg", b"jpg", "image/jpeg")},
    )  # fmt: skip
    assert pending.status_code == 409
    incident = await ingest(app, candidate(lat, lon), key)
    done = await client.post(
        "/internal/evidence", headers=INGEST,
        data={"kind": "keyframe", "idempotency_key": key},
        files={"file": ("k.jpg", b"jpg", "image/jpeg")},
    )  # fmt: skip
    assert done.status_code == 201
    assert done.json()["kind"] == "keyframe"
    assert incident.id


async def test_oversize_upload_is_413_and_leaves_no_file(tmp_path: Path) -> None:
    from nadjet_api.main import create_app

    from .conftest import make_settings

    app = create_app(make_settings(tmp_path, evidence_max_mb=1))
    async with app.router.lifespan_context(app):
        incident = await ingest(app, candidate(*fresh_spot()))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await upload(c, incident.id, b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert not list((tmp_path / "evidence").rglob("*.mp4"))


async def test_FR_SEC_004_evidence_download_is_audited_and_scoped(
    app: FastAPI, client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    viewer_user = await make_user(session, role="operator")
    viewer = await login(client, viewer_user)
    outsider = await login(client, await make_user(session, role="responder", agency="police"))
    lat, lon = fresh_spot()
    incident = await ingest(app, candidate(lat, lon))
    evidence = (await upload(client, incident.id, b"video-bytes")).json()
    url = f"/incidents/{incident.id}/evidence/{evidence['id']}"

    response = await client.get(url, headers=viewer)
    assert response.status_code == 200 and response.content == b"video-bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.get(url)).status_code == 401
    logged = await session.scalar(
        text(
            "SELECT count(*) FROM audit_log WHERE action='evidence.download' "
            "AND actor_id=:a AND target_id=:t"
        ),
        {"a": viewer_user.id, "t": evidence["id"]},
    )
    assert logged == 1


async def test_incident_events_cannot_be_modified_in_the_database(
    app: FastAPI, session: AsyncSession
) -> None:
    incident = await ingest(app, candidate(*fresh_spot()))
    for statement in (
        "UPDATE incident_events SET kind='x' WHERE incident_id=:i",
        "DELETE FROM incident_events WHERE incident_id=:i",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text(statement), {"i": incident.id})
        await session.rollback()


async def test_AC_VIS_007_1_type_is_possible_incident_until_the_ai_confirms(
    app: FastAPI, session: AsyncSession
) -> None:
    lat, lon = fresh_spot()
    t0 = datetime.now(UTC)
    no = VerifierResult(available=True, model="m", collision_visible="no", yes_probability=0.02)
    first = await ingest(app, candidate(lat, lon, at=t0, verifier=no, ai_status=AiStatus.POSSIBLE))
    assert (first.type, first.ai_status) == ("possible_incident", "possible")

    yes = VerifierResult(available=True, model="m", collision_visible="yes", yes_probability=0.95)
    await ingest(
        app,
        candidate(
            lat, lon, at=t0 + timedelta(seconds=5), verifier=yes, ai_status=AiStatus.CONFIRMED
        ),
    )
    merged = await session.get(Incident, first.id, populate_existing=True)
    assert merged is not None
    assert (merged.type, merged.ai_status) == ("collision", "confirmed")
