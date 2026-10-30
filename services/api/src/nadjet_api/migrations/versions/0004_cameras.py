"""Camera registry table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("stream_path", sa.String(63), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("road", sa.String(64), nullable=False),
        sa.Column("pk_km", sa.Double()),
        sa.Column("heading_deg", sa.Double(), nullable=False, server_default="0"),
        sa.Column("wilaya", sa.String(64), nullable=False),
        sa.Column("zones", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('unknown','online','degraded','offline')", name="cameras_status_valid"
        ),
        sa.CheckConstraint("heading_deg >= 0 AND heading_deg < 360", name="cameras_heading_valid"),
    )
    # Point generated from lat/lon so spatial queries (nearest camera) can use the GiST index.
    op.execute(
        "ALTER TABLE cameras ADD COLUMN geom geometry(Point, 4326) "
        "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED"
    )
    op.execute("CREATE INDEX cameras_geom_idx ON cameras USING gist (geom)")


def downgrade() -> None:
    op.drop_table("cameras")
