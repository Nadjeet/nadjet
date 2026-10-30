"""Notification delivery records, web-push subscriptions and facility availability."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadjet_api.db import Base

QUEUED, SENT, DELIVERED, FAILED = "queued", "sent", "delivered", "failed"


class Notification(Base):
    """One message to one recipient on one channel; unique per incident+kind (FR-NTF-007)."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("incident_id", "kind", "channel", "recipient", name="uq_notif_once"),
        CheckConstraint(
            "status IN ('queued','sent','delivered','failed')", name="notifications_status_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id"))
    kind: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    recipient: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(16), default=QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_ref: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FacilityStatus(Base):
    """Hospital Ready/Divert state, set by ``H <code> READY|DIVERT`` (FR-NTF-005)."""

    __tablename__ = "facility_status"
    __table_args__ = (
        CheckConstraint("state IN ('ready','divert')", name="facility_status_state_valid"),
    )

    facility_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
