"""
视频处理任务数据库模型
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base


class VideoProcessTask(Base):
    """视频处理任务模型"""

    __tablename__ = "video_process_tasks"

    # 任务状态常量
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="任务ID")
    user_id = Column(String, nullable=False, index=True, comment="用户ID")

    # 视频信息
    douyin_id = Column(String, nullable=True, index=True, comment="抖音视频ID（去重用）")
    original_url = Column(String, nullable=False, comment="原始视频URL")
    converted_url = Column(String, nullable=True, comment="转换后的视频URL（如果适用）")

    # 文件路径
    video_path = Column(String, nullable=True, comment="本地视频文件路径")
    audio_path = Column(String, nullable=True, comment="本地音频文件路径")

    # 处理结果
    subtitle_text = Column(Text, nullable=True, comment="语音识别结果（字幕文字）")
    ai_summary = Column(Text, nullable=True, comment="AI总结结果")

    # 状态和错误
    status = Column(
        String,
        nullable=False,
        default=STATUS_PENDING,
        index=True,
        comment="任务状态：pending-等待处理, processing-处理中, completed-已完成, failed-失败"
    )
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 时间戳
    created_at = Column(
        BigInteger,
        default=lambda: int(datetime.utcnow().timestamp()),
        comment="创建时间戳"
    )
    updated_at = Column(
        BigInteger,
        default=lambda: int(datetime.utcnow().timestamp()),
        onupdate=lambda: int(datetime.utcnow().timestamp()),
        comment="更新时间戳"
    )
