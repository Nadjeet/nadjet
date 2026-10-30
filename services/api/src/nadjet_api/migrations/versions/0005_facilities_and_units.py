"""Facilities and units for dispatch (FR-ADM-001, FR-DSP-001, FR-DSP-002).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("wilaya", sa.String(64)),
        sa.Column(
            "capabilities",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ready_state", sa.String(8), server_default="ready", nullable=False),
        sa.Column("contact_sms", sa.String(32)),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('hospital','civil_protection','gendarmerie','police')",
            name="facilities_kind_valid",
        ),
        sa.CheckConstraint("ready_state IN ('ready','divert')", name="facilities_ready_valid"),
    )
    op.execute("ALTER TABLE facilities ADD COLUMN geom geometry(Point,4326) NOT NULL")
    op.execute("CREATE INDEX facilities_geom_idx ON facilities USING gist (geom)")
    op.create_index("facilities_kind_idx", "facilities", ["kind"])

    op.create_table(
        "units",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "facility_id", sa.String(64), sa.ForeignKey("facilities.id"), nullable=False
        ),
        sa.Column("agency", sa.String(32), nullable=False),
        sa.Column("callsign", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), server_default="available", nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "agency IN ('civil_protection','gendarmerie','police','samu')",
            name="units_agency_valid",
        ),
        sa.CheckConstraint(
            "status IN ('available','dispatched','busy','offline')", name="units_status_valid"
        ),
    )
    op.execute("ALTER TABLE units ADD COLUMN geom geometry(Point,4326) NOT NULL")
    op.execute("CREATE INDEX units_geom_idx ON units USING gist (geom)")
    op.create_index("units_facility_idx", "units", ["facility_id"])


def downgrade() -> None:
    op.drop_table("units")
    op.drop_table("facilities")
