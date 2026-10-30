"""Integration: GET /kpis with seeded incident timelines (FR-KPI-001/002, US-11).

Each run seeds a random 30-day window in the 1950s-1960s (incident events cannot be deleted), so
rows from earlier runs, other tests or other agents never fall inside the queried window.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.incidents.models import Incident, IncidentEvent
from nadjet_api.kpis import compute

from .conftest import MakeUser
from .test_integration_incidents import login

pytestmark = pytest.mark.integration

WINDOW_START = datetime(1950, 1, 1, tzinfo=UTC) + timedelta(days=40 * random.randrange(500))
T0 = WINDOW_START + timedelta(days=4, hours=12)
WINDOW = {
    "since": WINDOW_START.isoformat(),
    "until": (WINDOW_START + timedelta(days=31)).isoformat(),
}


async def seed(
    session: AsyncSession,
    *,
    camera: str,
    wilaya: str,
    agencies: list[str],
    start: datetime,
    timeline: list[tuple[str, float]],
    status: str = "closed",
    reject_reason: str | None = None,
) -> Incident:
    """One incident; ``timeline`` is ``(milestone, seconds after start)``, ``created`` first."""
    incident = Incident(
        id=uuid.uuid4(), short_code="K1P", type="collision", status=status, priority=2,
        priority_reasons=[], lat=36.7, lon=3.0, wilaya=wilaya, source="camera", camera_id=camera,
        event_time=start, last_event_time=start, detected_at=start, ai_signals={},
        verifier_result={"available": False}, quality_flags=[], assigned_agencies=agencies, reject_reason=reject_reason,
    )  # fmt: skip
    session.add(incident)
    await session.flush()
    prev = "0" * 64
    for milestone, seconds in timeline:
        kind = "created" if milestone == "created" else "status_changed"
        payload: dict[str, Any] = {} if kind == "created" else {"to": milestone}
        prev = uuid.uuid4().hex + uuid.uuid4().hex  # fake chain: KPIs do not verify it
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                kind=kind,
                payload=payload,
                ts=start + timedelta(seconds=seconds),
                prev_hash="0" * 64,
                hash=prev,
            )
        )
    await session.commit()
    return incident


FULL = [
    ("created", 10), ("verified", 40), ("dispatched", 100), ("acknowledged", 130),
    ("on_scene", 700), ("at_hospital", 1300),
]  # fmt: skip


async def test_FR_KPI_001_per_incident_durations_and_FR_KPI_002_aggregates(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    cam = f"kpi-cam-{uuid.uuid4().hex[:6]}"
    other = f"kpi-cam-{uuid.uuid4().hex[:6]}"
    await seed(session, camera=cam, wilaya="Alger", agencies=["samu"], start=T0, timeline=FULL)
    # Twice as slow: scene 1200 s after dispatch (verification 60 s, detection 20 s).
    slow = [("created", 20), ("verified", 80), ("dispatched", 140), ("on_scene", 1340)]
    await seed(
        session, camera=cam, wilaya="Alger", agencies=["samu", "civil_protection"],
        start=T0 + timedelta(hours=1), timeline=slow,
    )  # fmt: skip
    await seed(
        session, camera=other, wilaya="Blida", agencies=[], start=T0 + timedelta(days=9),
        timeline=[("created", 5), ("rejected", 25)], status="rejected",
        reject_reason="false_positive",
    )  # fmt: skip
    await seed(
        session, camera=other, wilaya="Blida", agencies=[], start=T0 + timedelta(days=9, hours=2),
        timeline=[("created", 5), ("rejected", 25)], status="rejected", reject_reason="duplicate",
    )  # fmt: skip
    await seed(  # merged into another incident: not counted at all
        session, camera=other, wilaya="Blida", agencies=[], start=T0 + timedelta(days=9, hours=3),
        timeline=[("created", 5)], status="merged",
    )  # fmt: skip
    supervisor = await login(client, await make_user(session, role="supervisor"))

    response = await client.get("/kpis", params={**WINDOW, "period": "week"}, headers=supervisor)

    assert response.status_code == 200, response.text
    body = response.json()
    overall = body["overall"]
    assert overall["incidents"] == 4
    assert overall["metrics"]["detection_s"] == {"n": 4, "median_s": 7.5, "p90_s": 17.0}
    # (40-10)=30 and (80-20)=60 for the two verified incidents; the rejected ones never verify.
    assert overall["metrics"]["verification_s"] == {"n": 2, "median_s": 45.0, "p90_s": 57.0}
    assert overall["metrics"]["acknowledge_s"]["n"] == 1
    assert overall["metrics"]["scene_s"] == {"n": 2, "median_s": 900.0, "p90_s": 1140.0}
    assert overall["metrics"]["hospital_s"] == {"n": 1, "median_s": 1200.0, "p90_s": 1200.0}
    by_agency = {g["key"]: g for g in body["by_agency"]}
    assert by_agency["samu"]["incidents"] == 2
    assert by_agency["civil_protection"]["metrics"]["scene_s"]["median_s"] == 1200.0
    by_wilaya = {g["key"]: g for g in body["by_wilaya"]}
    assert by_wilaya["Alger"]["incidents"] == 2
    assert by_wilaya["Blida"]["incidents"] == 2
    assert [g["key"] for g in body["by_period"]] == [
        compute.period_key(T0, "week"),
        compute.period_key(T0 + timedelta(days=9), "week"),
    ]
    # Per camera: duplicates leave the denominator; the false positive is 1 of 1.
    rates = {c["camera_id"]: c for c in body["false_alarms"]}
    assert rates[cam] == {"camera_id": cam, "incidents": 2, "false_positives": 0, "rate": 0.0}
    assert rates[other]["incidents"] == 1
    assert rates[other]["false_positives"] == 1
    assert rates[other]["rate"] == 1.0
    first = next(
        i for i in body["incidents"] if i["event_time"] == T0.isoformat().replace("+00:00", "Z")
    )
    assert first["durations"] == {
        "detection_s": 10, "verification_s": 30, "acknowledge_s": 30,
        "scene_s": 600, "hospital_s": 1200,
    }  # fmt: skip


async def test_kpis_are_for_supervisors_and_admins_only(
    client: httpx.AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    assert (await client.get("/kpis")).status_code == 401
    for role, expected in (
        ("operator", 403),
        ("auditor", 403),
        ("supervisor", 200),
        ("admin", 200),
    ):
        headers = await login(client, await make_user(session, role=role))
        response = await client.get("/kpis", params=WINDOW, headers=headers)
        assert response.status_code == expected, role
