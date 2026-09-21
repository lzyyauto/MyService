"""Add global Notion select option mappings.

Revision ID: 20260921_select_options
Revises: 20260921_sport_record
Create Date: 2026-09-21 14:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260921_select_options"
down_revision = "20260921_sport_record"
branch_labels = None
depends_on = None


OPTION_MAPPINGS = (
    ("9fadf1da-a372-428f-83bc-40d1e61a39da", "Just Dance"),
    ("8dd69b8b-e6f6-4d2a-a7f3-289940ac0b32", "跑步"),
    ("bb05a747-00a6-4c18-b7a2-32f834563dd6", "大冒险"),
    ("ca2f4e6e-5664-46a7-8ef2-197c81162e42", "FitBox"),
    ("4858501c-6e80-492d-b942-f44e6bd50306", "帕梅拉"),
    ("8146acbb-199f-4398-a03f-68adb09aae9c", "直播跳操"),
    ("d75833aa-cf96-4796-8ce1-d4aae31107af", "其他"),
    ("cb7ef7c0-11b8-46b0-93fb-a50c53f75799", "骑车"),
    ("283bab02-ca52-4949-8f2c-3d56e15c1a04", "暴走"),
    ("0735150f-0cad-439d-ab4c-ffdc9484e46b", "陆冲"),
)


def upgrade() -> None:
    op.create_table(
        "notion_select_option_mappings",
        sa.Column("option_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("option_id"),
    )
    mapping_table = sa.table(
        "notion_select_option_mappings",
        sa.column("option_id", sa.String()),
        sa.column("name", sa.String()),
    )
    op.bulk_insert(
        mapping_table,
        [{"option_id": option_id, "name": name} for option_id, name in OPTION_MAPPINGS],
    )


def downgrade() -> None:
    op.drop_table("notion_select_option_mappings")
