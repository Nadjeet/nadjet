"""Incidents, hash-chained incident events, evidence and casualties (FR-INC, FR-SEC-003).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OPEN = "status NOT IN ('rejected','merged','closed')"


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("short_code", sa.String(3), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("priority_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("to_assess", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mass_casualty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("needs_extrication", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("road", sa.String(64)),
        sa.Column("pk_km", sa.Float()),
        sa.Column("wilaya", sa.String(64)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("camera_id", sa.String(64)),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_status", sa.String(24)),
        sa.Column("ai_signals", postgresql.JSONB(), nullable=False),
        sa.Column("verifier_result", postgresql.JSONB(), nullable=False),
        sa.Column("quality_flags", postgresql.JSONB(), nullable=False),
        sa.Column("people_reported", sa.Integer()),
        sa.Column("trapped_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reject_reason", sa.String(16)),
        sa.Column("merged_into", sa.Uuid(), sa.ForeignKey("incidents.id")),
        sa.Column(
            "assigned_agencies", postgresql.ARRAY(sa.String()), nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "assigned_facilities", postgresql.ARRAY(sa.String()), nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 4", name="incidents_priority_range"),
        sa.CheckConstraint(
            "status IN ('candidate','verified','rejected','merged','dispatched','acknowledged',"
            "'en_route','on_scene','transporting','at_hospital','closed')",
            name="incidents_status_valid",
        ),
    )
    op.execute(
        "ALTER TABLE incidents ADD COLUMN geom geometry(Point, 4326) "
        "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED"
    )
    op.execute("CREATE INDEX ix_incidents_geog ON incidents USING gist ((geom::geography))")
    op.create_index(
        "uq_incidents_open_short_code",
        "incidents",
        ["short_code"],
        unique=True,
        postgresql_where=sa.text(OPEN),
    )
    op.create_index("ix_incidents_queue", "incidents", ["priority", sa.text("detected_at DESC")])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.execute("CREATE INDEX ix_incidents_agencies ON incidents USING gin (assigned_agencies)")

    op.create_table(
        "incident_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(128)),
    )
    op.create_index("ix_incident_events_incident", "incident_events", ["incident_id", "id"])
    op.create_index(
        "uq_incident_events_idempotency",
        "incident_events",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.execute(
        """
        CREATE FUNCTION append_only_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER incident_events_append_only BEFORE UPDATE OR DELETE ON incident_events "
        "FOR EACH ROW EXECUTE FUNCTION append_only_reject_change()"
    )
    op.execute(
        "CREATE TRIGGER incident_events_no_truncate BEFORE TRUNCATE ON incident_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION append_only_reject_change()"
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True)),
        sa.Column("end_ts", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('clip','keyframe','photo')", name="evidence_kind_valid"),
    )
    op.create_index("ix_evidence_incident", "evidence", ["incident_id"])

    op.create_table(
        "casualties",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("triage_tag", sa.String(8), nullable=False),
        sa.Column("avpu", sa.String(1)),
        sa.Column("resp_rate", sa.Integer()),
        sa.Column("pulse", sa.Integer()),
        sa.Column("spo2", sa.Integer()),
        sa.Column("bleeding", sa.Boolean()),
        sa.Column("notes", sa.Text()),
        sa.Column("reported_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "triage_tag IN ('red','yellow','green','black')", name="casualties_tag_valid"
        ),
        sa.CheckConstraint("source IN ('app','sms')", name="casualties_source_valid"),
    )
    op.create_index("ix_casualties_incident", "casualties", ["incident_id"])


def downgrade() -> None:
    op.drop_table("casualties")
    op.drop_table("evidence")
    op.execute("DROP TRIGGER IF EXISTS incident_events_no_truncate ON incident_events")
    op.execute("DROP TRIGGER IF EXISTS incident_events_append_only ON incident_events")
    op.drop_table("incident_events")
    op.execute("DROP FUNCTION IF EXISTS append_only_reject_change()")
    op.drop_table("incidents")
