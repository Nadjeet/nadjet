"""Notifications, push subscriptions and call-back incidents (FR-NTF).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_ref", sa.String(64)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # FR-NTF-007: one notification per incident, kind, channel and recipient.
        sa.UniqueConstraint("incident_id", "kind", "channel", "recipient", name="uq_notif_once"),
        sa.CheckConstraint(
            "status IN ('queued','sent','delivered','failed')", name="notifications_status_valid"
        ),
    )
    op.create_index("ix_notifications_provider_ref", "notifications", ["provider_ref"])
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # An SMS report with only a free-text location has no position until an operator calls back.
    op.alter_column("incidents", "lat", nullable=True)
    op.alter_column("incidents", "lon", nullable=True)
    op.add_column("incidents", sa.Column("location_text", sa.Text()))


def downgrade() -> None:
    # incident_events is append-only (TD-33), so position-less incidents cannot be dropped here.
    stuck = op.get_bind().execute(sa.text("SELECT count(*) FROM incidents WHERE lat IS NULL"))
    if stuck.scalar_one():
        raise RuntimeError("downgrade needs every call-back incident to have a position first")
    op.drop_column("incidents", "location_text")
    op.alter_column("incidents", "lon", nullable=False)
    op.alter_column("incidents", "lat", nullable=False)
    op.drop_table("push_subscriptions")
    op.drop_index("ix_notifications_provider_ref", table_name="notifications")
    op.drop_table("notifications")
