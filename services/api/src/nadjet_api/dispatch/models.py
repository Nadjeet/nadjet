"""``dispatches``: one row per dispatched unit and one per selected hospital (FR-DSP-003)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadjet_api.db import Base

DISPATCHED, REPLACED = "dispatched", "replaced"


class Dispatch(Base):
    __tablename__ = "dispatches"
    __table_args__ = (
        CheckConstraint("(unit_id IS NULL) <> (hospital_id IS NULL)", name="dispatches_one_target"),
        CheckConstraint("status IN ('dispatched','replaced')", name="dispatches_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("incidents.id"))
    # Foreign keys to units/facilities live in the migration: those tables have no ORM models.
    unit_id: Mapped[str | None] = mapped_column(String(64))
    hospital_id: Mapped[str | None] = mapped_column(String(64))
    eta_s: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float] = mapped_column(Float)
    route: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default=DISPATCHED)
    dispatched_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
