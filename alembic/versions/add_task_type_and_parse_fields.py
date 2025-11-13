"""Add task_type and parse result fields to video_process_tasks

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2025-11-13 14:35:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    为 video_process_tasks 表添加新字段：
    - task_type: 任务类型（parse/process）
    - media_type: 媒体类型
    - aweme_id: 抖音视频ID
    - desc: 视频描述
    - author: 作者昵称
    - download_urls: 下载链接列表（JSON格式）
    - 添加 STATUS_PARSED 状态
    """
    # 检查表是否存在
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'video_process_tasks'
        );
    """))

    if not result.fetchone()[0]:
        print("表 video_process_tasks 不存在，跳过迁移")
        return

    # 检查字段是否已存在
    result = connection.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'video_process_tasks'
    """))

    existing_columns = [row[0] for row in result.fetchall()]

    # 添加 task_type 字段
    if 'task_type' not in existing_columns:
        # 先添加为可空列
        op.add_column('video_process_tasks',
                     sa.Column('task_type',
                              sa.String(),
                              nullable=True,
                              index=True,
                              comment='任务类型：parse-仅解析URL, process-完整处理'))
        # 更新现有记录为 process 类型
        connection.execute(sa.text("""
            UPDATE video_process_tasks
            SET task_type = 'process'
            WHERE task_type IS NULL
        """))
        # 修改为不可空
        op.alter_column('video_process_tasks', 'task_type',
                       nullable=False,
                       server_default='process')

    # 添加解析结果字段
    if 'media_type' not in existing_columns:
        op.add_column('video_process_tasks',
                     sa.Column('media_type',
                              sa.String(),
                              nullable=True,
                              comment='媒体类型：video/image/live_photo'))

    if 'aweme_id' not in existing_columns:
        op.add_column('video_process_tasks',
                     sa.Column('aweme_id',
                              sa.String(),
                              nullable=True,
                              comment='抖音视频ID'))

    if 'desc' not in existing_columns:
        op.add_column('video_process_tasks',
                     sa.Column('desc',
                              sa.Text(),
                              nullable=True,
                              comment='视频描述'))

    if 'author' not in existing_columns:
        op.add_column('video_process_tasks',
                     sa.Column('author',
                              sa.String(),
                              nullable=True,
                              comment='作者昵称'))

    if 'download_urls' not in existing_columns:
        op.add_column('video_process_tasks',
                     sa.Column('download_urls',
                              sa.Text(),
                              nullable=True,
                              comment='下载链接列表（JSON格式）'))

    print("数据库迁移完成 - 添加了 task_type 和解析结果字段")


def downgrade():
    """
    删除新增的字段
    """
    op.drop_column('video_process_tasks', 'download_urls')
    op.drop_column('video_process_tasks', 'author')
    op.drop_column('video_process_tasks', 'desc')
    op.drop_column('video_process_tasks', 'aweme_id')
    op.drop_column('video_process_tasks', 'media_type')
    op.drop_column('video_process_tasks', 'task_type')
    print("数据库回滚完成")
