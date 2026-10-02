"""飞书采集内部状态；旧整理任务模型仅保留表结构兼容，不再运行。"""

from sqlalchemy import BigInteger, Boolean, Column, Integer, JSON, String, Text

from app.db.base_class import Base


class FeishuSource(Base):
    __tablename__ = "feishu_sources"
    id = Column(String, primary_key=True)
    app = Column(String, nullable=False, index=True)
    app_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=False, index=True)
    chat_type = Column(String, nullable=False)
    sender_id = Column(String, nullable=False)
    user_id = Column(String, nullable=True)
    first_seen = Column(BigInteger, nullable=False)
    last_seen = Column(BigInteger, nullable=False, index=True)
    message_count = Column(Integer, nullable=False, default=0)


class FeishuStream(Base):
    __tablename__ = "feishu_streams"
    id = Column(String, primary_key=True)
    pipeline = Column(String, nullable=False, index=True)
    input_path = Column(Text, nullable=False, unique=True)
    context = Column(JSON, nullable=False)
    batch_id = Column(String, nullable=False)
    materialized = Column(Boolean, nullable=False, default=False)
    file_identity = Column(String, nullable=True)
    started_at = Column(BigInteger, nullable=False)


class FeishuMessage(Base):
    __tablename__ = "feishu_messages"
    id = Column(String, primary_key=True)
    app = Column(String, nullable=False)
    app_id = Column(String, nullable=False)
    message_id = Column(String, nullable=False)
    chat_id = Column(String, nullable=True)
    stream_id = Column(String, nullable=False, index=True)
    batch_id = Column(String, nullable=False)
    text = Column(Text, nullable=True)
    sender_id = Column(String, nullable=False)
    create_time = Column(BigInteger, nullable=False)
    status = Column(String, nullable=False, index=True)
    reaction_status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(BigInteger, nullable=False, default=0)
    received_at = Column(BigInteger, nullable=False)


class FeishuRun(Base):
    """历史整理数据兼容；采集程序不创建、查询或消费此表。"""
    __tablename__ = "feishu_runs"
    id = Column(String, primary_key=True)
    trigger_key = Column(String, nullable=False, unique=True)
    stream_id = Column(String, nullable=False, index=True)
    batch_id = Column(String, nullable=False)
    pipeline = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    snapshot = Column(Text, nullable=True)
    specification = Column(JSON, nullable=False)
    generated = Column(Text, nullable=True)
    output_saved = Column(Boolean, nullable=False, default=False)
    sent_parts = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(BigInteger, nullable=False, default=0)
    locked_until = Column(BigInteger, nullable=True)
    owner = Column(String, nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class FeishuControl(Base):
    __tablename__ = "feishu_controls"
    id = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)


FEISHU_TABLES = [model.__table__ for model in (FeishuSource, FeishuStream, FeishuMessage, FeishuControl)]
