"""新增飞书统一接入和 AI 任务，不修改已有业务表。

Revision ID: 20261002_feishu
Revises: 20260922_sport_details
"""

import sqlalchemy as sa
from alembic import op

revision = "20261002_feishu"
down_revision = "20260922_sport_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("feishu_sources",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("app", sa.String(), nullable=False),
        sa.Column("app_id", sa.String(), nullable=False), sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("chat_type", sa.String(), nullable=False), sa.Column("sender_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String()), sa.Column("first_seen", sa.BigInteger(), nullable=False),
        sa.Column("last_seen", sa.BigInteger(), nullable=False), sa.Column("message_count", sa.Integer(), nullable=False))
    for field in ("app", "chat_id", "last_seen"):
        op.create_index(f"ix_feishu_sources_{field}", "feishu_sources", [field])
    op.create_table("feishu_streams",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("pipeline", sa.String(), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False, unique=True), sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=False), sa.Column("materialized", sa.Boolean(), nullable=False),
        sa.Column("file_identity", sa.String()), sa.Column("started_at", sa.BigInteger(), nullable=False))
    op.create_index("ix_feishu_streams_pipeline", "feishu_streams", ["pipeline"])
    op.create_table("feishu_messages",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("app", sa.String(), nullable=False),
        sa.Column("app_id", sa.String(), nullable=False), sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String()),
        sa.Column("stream_id", sa.String(), nullable=False), sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text()), sa.Column("sender_id", sa.String(), nullable=False),
        sa.Column("create_time", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("reaction_status", sa.String(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.BigInteger(), nullable=False), sa.Column("received_at", sa.BigInteger(), nullable=False))
    for field in ("stream_id", "status"):
        op.create_index(f"ix_feishu_messages_{field}", "feishu_messages", [field])
    op.create_table("feishu_runs",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("trigger_key", sa.String(), nullable=False, unique=True),
        sa.Column("stream_id", sa.String(), nullable=False), sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("pipeline", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("snapshot", sa.Text()), sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("generated", sa.Text()), sa.Column("output_saved", sa.Boolean(), nullable=False),
        sa.Column("sent_parts", sa.Integer(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.BigInteger(), nullable=False), sa.Column("locked_until", sa.BigInteger()),
        sa.Column("owner", sa.String()), sa.Column("last_error", sa.String()),
        sa.Column("created_at", sa.BigInteger(), nullable=False), sa.Column("updated_at", sa.BigInteger(), nullable=False))
    for field in ("stream_id", "pipeline", "status"):
        op.create_index(f"ix_feishu_runs_{field}", "feishu_runs", [field])
    op.create_table("feishu_controls", sa.Column("id", sa.String(), primary_key=True), sa.Column("value", sa.JSON(), nullable=False))


def downgrade() -> None:
    # 有新业务数据时不要直接 downgrade；应先备份并导出。
    for table in ("feishu_controls", "feishu_runs", "feishu_messages", "feishu_streams", "feishu_sources"):
        op.drop_table(table)
