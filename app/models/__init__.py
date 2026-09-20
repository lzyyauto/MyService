"""集中注册模型。

GTD 与视频模型虽已废弃，仍需注册以兼容既有数据库和 Alembic 历史。
"""

from app.models.gtd_task import GtdTask
from app.models.notion_ingest import (
    ExerciseRecord,
    NotionDatabaseMapping,
    NotionDelivery,
    NotionIngestEvent,
)
from app.models.rest_record import RestRecord
from app.models.user import User
from app.models.video_process_task import VideoProcessTask

__all__ = [
    "ExerciseRecord",
    "GtdTask",
    "NotionDatabaseMapping",
    "NotionDelivery",
    "NotionIngestEvent",
    "RestRecord",
    "User",
    "VideoProcessTask",
]
