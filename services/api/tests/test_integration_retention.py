"""Integration: the retention purge deletes only expired evidence and audits it (FR-SEC-005)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nadjet_api.audit.models import AuditLog
from nadjet_api.config import Settings
from nadjet_api.incidents.models import Evidence, Incident
from nadjet_api.retention import purge_expired

from .conftest import make_settings

pytestmark = pytest.mark.integration

# A fake "now" in 2001 so only the rows made here are older than the cutoff.
NOW = datetime(2001, 6, 1, tzinfo=UTC)


async def evidence(
    session: AsyncSession, app: FastAPI, incident: Incident, name: str, created: datetime
) -> Evidence:
    path = f"{incident.id}/{name}"
    target = Path(app.state.store.root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"clip")
    row = Evidence(
        id=uuid.uuid4(), incident_id=incident.id, kind="clip", path=path,
        content_type="video/mp4", size_bytes=4, sha256="0" * 64, created_at=created,
    )  # fmt: skip
    session.add(row)
    await session.commit()
    return row


async def test_FR_SEC_005_purges_only_evidence_older_than_the_retention_period(
    app: FastAPI, session: AsyncSession, tmp_path: Path
) -> None:
    incident = Incident(
        id=uuid.uuid4(), short_code="RET", type="collision", status="closed", priority=2,
        priority_reasons=[], source="camera", event_time=NOW, last_event_time=NOW,
        detected_at=NOW, ai_signals={}, verifier_result={"available": False}, quality_flags=[],
    )  # fmt: skip
    session.add(incident)
    await session.commit()
    old = await evidence(session, app, incident, "old.mp4", NOW - timedelta(days=91))
    edge = await evidence(session, app, incident, "edge.mp4", NOW - timedelta(days=89))
    new = await evidence(session, app, incident, "new.mp4", NOW - timedelta(days=1))
    settings: Settings = make_settings(tmp_path, retention_days=90)

    deleted = await purge_expired(app.state.session_factory, app.state.store, settings, at=NOW)

    assert deleted == 1
    root = Path(app.state.store.root)
    assert not (root / old.path).exists()
    assert (root / edge.path).exists()
    assert (root / new.path).exists()
    remaining = set(
        await session.scalars(select(Evidence.id).where(Evidence.incident_id == incident.id))
    )
    assert remaining == {edge.id, new.id}
    assert await session.get(Incident, incident.id) is not None  # the incident record stays
    entries = list(
        await session.scalars(
            select(AuditLog).where(AuditLog.action == "retention.purge", AuditLog.at > NOW)
        )
    )
    assert any(e.details["deleted"] == 1 and e.details["retention_days"] == 90 for e in entries)

    # Nothing left to purge: no second audit entry for an empty run.
    before = len(entries)
    assert await purge_expired(app.state.session_factory, app.state.store, settings, at=NOW) == 0
    after = list(
        await session.scalars(select(AuditLog).where(AuditLog.action == "retention.purge"))
    )
    assert len(after) == before


def test_retention_period_is_bounded_to_one_year() -> None:
    assert Settings(retention_days=365).retention_days == 365
    for days in (0, 366):
        with pytest.raises(ValueError):
            Settings(retention_days=days)
