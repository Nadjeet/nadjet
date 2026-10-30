"""Dispatches of units and hospitals to incidents (FR-DSP-003).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatches",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("unit_id", sa.String(64), sa.ForeignKey("units.id")),
        sa.Column("hospital_id", sa.String(64), sa.ForeignKey("facilities.id")),
        sa.Column("eta_s", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("route", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="dispatched"),
        sa.Column("dispatched_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # A row dispatches one unit or one hospital, never both.
        sa.CheckConstraint("(unit_id IS NULL) <> (hospital_id IS NULL)", name="dispatches_one_target"),
        sa.CheckConstraint("status IN ('dispatched','replaced')", name="dispatches_status_valid"),
    )
    op.create_index("ix_dispatches_incident", "dispatches", ["incident_id"])
    op.create_index("ix_dispatches_hospital", "dispatches", ["hospital_id"])
    # A unit is dispatched once per incident, and an incident has one active hospital.
    op.create_index(
        "uq_dispatches_active_unit",
        "dispatches",
        ["incident_id", "unit_id"],
        unique=True,
        postgresql_where=sa.text("status = 'dispatched' AND unit_id IS NOT NULL"),
    )
    op.create_index(
        "uq_dispatches_active_hospital",
        "dispatches",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status = 'dispatched' AND hospital_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("dispatches")
