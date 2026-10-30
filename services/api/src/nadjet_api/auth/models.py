"""``users`` table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from nadjet_api.db import Base

ROLE_VALUES = "('operator','supervisor','responder','hospital','auditor','admin')"
AGENCY_VALUES = "('civil_protection','gendarmerie','police','samu')"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN {ROLE_VALUES}", name="users_role_valid"),
        CheckConstraint(f"agency IS NULL OR agency IN {AGENCY_VALUES}", name="users_agency_valid"),
        CheckConstraint(
            "(role = 'responder') = (agency IS NOT NULL) "
            "AND (role = 'hospital') = (facility_id IS NOT NULL)",
            name="users_role_binding",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    agency: Mapped[str | None] = mapped_column(String(32), default=None)
    facility_id: Mapped[str | None] = mapped_column(String(64), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
