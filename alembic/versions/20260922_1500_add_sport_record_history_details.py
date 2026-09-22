"""Add retained historical detail fields to sport_record.

Revision ID: 20260922_sport_details
Revises: 20260921_select_options
Create Date: 2026-09-22 15:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_sport_details"
down_revision = "20260921_select_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """保留历史 sport_data 附加文本，不扩展现有业务接口。"""
    op.add_column("sport_record", sa.Column("detail", sa.Text(), nullable=True))
    op.add_column("sport_record", sa.Column("detail2", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sport_record", "detail2")
    op.drop_column("sport_record", "detail")
