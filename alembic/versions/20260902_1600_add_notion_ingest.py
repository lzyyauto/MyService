"""Add durable Notion ingest, delivery and exercise mapping tables.

Revision ID: 20260902_notion_ingest
Revises: 796f614d8ac3, a1b2c3d4e5f6
Create Date: 2026-09-02 16:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_notion_ingest"
down_revision = ("796f614d8ac3", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notion_database_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("notion_database_id", sa.String(), nullable=False),
        sa.Column("business_type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mapper_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "notion_database_id", name="uq_notion_mapping_user_database"),
    )
    op.create_index("ix_notion_database_mappings_user_id", "notion_database_mappings", ["user_id"])

    op.create_table(
        "notion_ingest_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("notion_database_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("business_type", sa.String(), nullable=True),
        sa.Column("mapping_display_name", sa.String(), nullable=True),
        sa.Column("mapper_key", sa.String(), nullable=True),
        sa.Column("original_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_notion_event_user_idempotency"),
    )
    op.create_index("ix_notion_ingest_events_user_id", "notion_ingest_events", ["user_id"])
    op.create_index("ix_notion_ingest_events_notion_database_id", "notion_ingest_events", ["notion_database_id"])

    op.create_table(
        "exercise_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_type", sa.String(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("month_str", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["source_event_id"], ["notion_ingest_events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_event_id"),
    )
    op.create_index("ix_exercise_records_user_id", "exercise_records", ["user_id"])
    op.create_index("ix_exercise_records_source_event_id", "exercise_records", ["source_event_id"])
    op.create_index("ix_exercise_records_occurred_at", "exercise_records", ["occurred_at"])
    op.create_index("ix_exercise_records_occurred_on", "exercise_records", ["occurred_on"])

    op.create_table(
        "notion_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notion_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.BigInteger(), nullable=False),
        sa.Column("locked_until", sa.BigInteger(), nullable=True),
        sa.Column("notion_page_id", sa.String(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["notion_ingest_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_notion_deliveries_event_id", "notion_deliveries", ["event_id"])
    op.create_index("ix_notion_deliveries_status", "notion_deliveries", ["status"])
    op.create_index("ix_notion_deliveries_next_attempt_at", "notion_deliveries", ["next_attempt_at"])
    op.create_index("ix_notion_deliveries_locked_until", "notion_deliveries", ["locked_until"])


def downgrade() -> None:
    op.drop_table("notion_deliveries")
    op.drop_table("exercise_records")
    op.drop_table("notion_ingest_events")
    op.drop_table("notion_database_mappings")
