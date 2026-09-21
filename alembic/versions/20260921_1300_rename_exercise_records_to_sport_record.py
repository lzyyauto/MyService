"""Rename the exercise projection to sport_record.

Revision ID: 20260921_sport_record
Revises: 20260902_notion_ingest
Create Date: 2026-09-21 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260921_sport_record"
down_revision = "20260902_notion_ingest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """原地重命名表和种类列，不复制、不删除既有运动记录。"""
    op.rename_table("exercise_records", "sport_record")
    op.alter_column(
        "sport_record",
        "exercise_type",
        new_column_name="sport_type",
        existing_type=sa.String(),
    )
    op.execute(
        "ALTER INDEX ix_exercise_records_user_id RENAME TO ix_sport_record_user_id"
    )
    op.execute(
        "ALTER INDEX ix_exercise_records_source_event_id "
        "RENAME TO ix_sport_record_source_event_id"
    )
    op.execute(
        "ALTER INDEX ix_exercise_records_occurred_at RENAME TO ix_sport_record_occurred_at"
    )
    op.execute(
        "ALTER INDEX ix_exercise_records_occurred_on RENAME TO ix_sport_record_occurred_on"
    )


def downgrade() -> None:
    """恢复旧表名和列名。"""
    op.execute(
        "ALTER INDEX ix_sport_record_user_id RENAME TO ix_exercise_records_user_id"
    )
    op.execute(
        "ALTER INDEX ix_sport_record_source_event_id "
        "RENAME TO ix_exercise_records_source_event_id"
    )
    op.execute(
        "ALTER INDEX ix_sport_record_occurred_at RENAME TO ix_exercise_records_occurred_at"
    )
    op.execute(
        "ALTER INDEX ix_sport_record_occurred_on RENAME TO ix_exercise_records_occurred_on"
    )
    op.alter_column(
        "sport_record",
        "sport_type",
        new_column_name="exercise_type",
        existing_type=sa.String(),
    )
    op.rename_table("sport_record", "exercise_records")
