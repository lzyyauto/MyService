"""Notion 标准页面载荷的本地采集、映射和投递模型。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base_class import Base


def _now_timestamp() -> int:
    return int(datetime.utcnow().timestamp())


class NotionDatabaseMapping(Base):
    """一个 Notion database ID 对应一个可识别的本地业务类型。"""

    __tablename__ = "notion_database_mappings"
    __table_args__ = (
        UniqueConstraint("user_id", "notion_database_id", name="uq_notion_mapping_user_database"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    notion_database_id = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    mapper_key = Column(String, nullable=False)
    created_at = Column(BigInteger, default=_now_timestamp, nullable=False)
    updated_at = Column(
        BigInteger,
        default=_now_timestamp,
        onupdate=_now_timestamp,
        nullable=False,
    )


class NotionIngestEvent(Base):
    """已接受的 Notion 页面请求；原始载荷用于本地留存和审计。"""

    __tablename__ = "notion_ingest_events"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_notion_event_user_idempotency"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    notion_database_id = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=True)
    business_type = Column(String, nullable=True)
    mapping_display_name = Column(String, nullable=True)
    mapper_key = Column(String, nullable=True)
    original_payload = Column(JSONB, nullable=False)
    created_at = Column(BigInteger, default=_now_timestamp, nullable=False)


class ExerciseRecord(Base):
    """从运动 Notion 页面严格解析出的本地业务记录。"""

    __tablename__ = "exercise_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    source_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notion_ingest_events.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    exercise_type = Column(String, nullable=False)
    duration = Column(Float, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    occurred_on = Column(Date, nullable=False, index=True)
    month_str = Column(String, nullable=False)
    city = Column(String, nullable=True)
    created_at = Column(BigInteger, default=_now_timestamp, nullable=False)
    updated_at = Column(
        BigInteger,
        default=_now_timestamp,
        onupdate=_now_timestamp,
        nullable=False,
    )


class NotionDelivery(Base):
    """向 Notion 投递一个页面的持久化任务。"""

    __tablename__ = "notion_deliveries"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notion_ingest_events.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    notion_payload = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default=STATUS_PENDING, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(BigInteger, nullable=False, default=_now_timestamp, index=True)
    locked_until = Column(BigInteger, nullable=True, index=True)
    notion_page_id = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(BigInteger, default=_now_timestamp, nullable=False)
    updated_at = Column(
        BigInteger,
        default=_now_timestamp,
        onupdate=_now_timestamp,
        nullable=False,
    )
