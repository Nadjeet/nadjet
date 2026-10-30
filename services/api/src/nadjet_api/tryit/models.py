"""Sandbox tables. Nothing here references ``incidents``: sandbox results stay in their row."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Double, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadjet_api.db import Base


class TryJob(Base):
    __tablename__ = "try_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','processing','done','failed','rejected')",
            name="try_jobs_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    stage: Mapped[str] = mapped_column(String(32), server_default=text("'queued'"))
    progress: Mapped[float] = mapped_column(Double, server_default=text("0"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    has_video: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrySession(Base):
    __tablename__ = "try_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    path: Mapped[str] = mapped_column(String(63), unique=True)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
