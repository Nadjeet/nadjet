"""Incident tables: incidents, incident_events (append-only), evidence, casualties.

``incidents.geom`` is a database-generated PostGIS point built from ``lat``/``lon``; queries use
it through raw SQL (``ST_DWithin`` on geography), the ORM only maps the coordinates.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadjet_api.db import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    short_code: Mapped[str] = mapped_column(String(3))
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(Integer)
    priority_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    to_assess: Mapped[bool] = mapped_column(Boolean, default=False)
    mass_casualty: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_extrication: Mapped[bool] = mapped_column(Boolean, default=False)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    road: Mapped[str | None] = mapped_column(String(64))
    pk_km: Mapped[float | None] = mapped_column(Float)
    wilaya: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    camera_id: Mapped[str | None] = mapped_column(String(64))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ai_status: Mapped[str | None] = mapped_column(String(24))
    ai_signals: Mapped[dict[str, float]] = mapped_column(JSONB)
    verifier_result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB)
    people_reported: Mapped[int | None] = mapped_column(Integer)
    trapped_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    reject_reason: Mapped[str | None] = mapped_column(String(16))
    merged_into: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("incidents.id"))
    # Filled by dispatch (#14); responders and hospitals only see incidents assigned to them.
    assigned_agencies: Mapped[list[str]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    assigned_facilities: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'")
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IncidentEvent(Base):
    """Append-only, hash-chained per incident, head signed with Ed25519 (FR-SEC-003)."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id"))
    kind: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str | None] = mapped_column(String(128))


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id"))
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    start_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Casualty(Base):
    __tablename__ = "casualties"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id"))
    triage_tag: Mapped[str] = mapped_column(String(8))
    avpu: Mapped[str | None] = mapped_column(String(1))
    resp_rate: Mapped[int | None] = mapped_column(Integer)
    pulse: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[int | None] = mapped_column(Integer)
    bleeding: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(8))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
