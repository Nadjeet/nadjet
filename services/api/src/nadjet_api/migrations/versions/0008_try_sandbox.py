"""Try-it-yourself sandbox: uploaded-clip jobs and live phone sessions.

Revision ID: 0008
Revises: 0006
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0006"  # re-point to the latest revision on origin/dev before merging
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "try_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Double(), nullable=False, server_default="0"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("has_video", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','processing','done','failed','rejected')",
            name="try_jobs_status_valid",
        ),
    )
    op.create_index("try_jobs_expires_at", "try_jobs", ["expires_at"])
    op.create_index("try_jobs_queue", "try_jobs", ["created_at"], postgresql_where=sa.text("status = 'queued'"))
    op.create_table(
        "try_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("path", sa.String(63), nullable=False, unique=True),
        sa.Column("events", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("try_sessions_expires_at", "try_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("try_sessions")
    op.drop_table("try_jobs")
