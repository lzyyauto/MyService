"""采集内部 SQLite 状态：来源、去重、落盘恢复和回执，不依赖业务数据库。"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, or_, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.feishu import FEISHU_TABLES, FeishuControl, FeishuMessage, FeishuSource, FeishuStream
from app.services.feishu.config import ConfigSnapshot
from app.services.feishu.events import Message
from app.services.feishu.files import current_batch, file_lock, identity


def key_for(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def database_url(snapshot: ConfigSnapshot) -> str:
    configured = os.environ.get(snapshot.config.runtime.database_url_env)
    if configured:
        if make_url(configured).get_backend_name() != "sqlite":
            raise ValueError("采集内部状态仅使用本地 SQLite，请移除 PostgreSQL 状态库覆盖")
        return configured
    return f"sqlite:///{snapshot.path(snapshot.config.runtime.state_path)}"


class Store:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
            raise ValueError("采集状态库必须是持久化的本地 SQLite 文件")
        state_path = Path(parsed.database).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(parsed.set(database=str(state_path)), connect_args={"timeout": 10, "check_same_thread": False})
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.initialize_local()

    @contextmanager
    def transaction(self):
        with self.sessions() as db:
            try:
                db.execute(text("BEGIN IMMEDIATE"))
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def initialize_local(self) -> None:
        if self.engine.dialect.name != "sqlite":
            raise ValueError("采集状态库只允许 SQLite")
        for table in FEISHU_TABLES:
            table.create(self.engine, checkfirst=True)

    def close(self) -> None:
        self.engine.dispose()

    def control(self, name: str) -> dict[str, Any]:
        with self.sessions() as db:
            row = db.get(FeishuControl, name)
            return dict(row.value) if row else {}

    def set_control(self, name: str, value: dict[str, Any]) -> None:
        with self.transaction() as db:
            db.merge(FeishuControl(id=name, value=value))

    def discover(self, app: str, seconds: int) -> None:
        if not 0 <= seconds <= 3600:
            raise ValueError("发现模式持续时间必须为 0 至 3600 秒")
        self.set_control(f"discovery:{app}", {"until": int(time.time()) + seconds if seconds else 0, "override": True})

    def configured_discovery(self, version: str, enabled: bool, seconds: int) -> None:
        """使用发现字段指纹，不因其他配置重载续期。"""
        with self.transaction() as db:
            row = db.get(FeishuControl, "discovery:config")
            if row and row.value.get("version") == version:
                return
            db.merge(FeishuControl(id="discovery:config", value={"version": version,
                "until": int(time.time()) + seconds if enabled else 0}))

    def is_discovering(self, app: str) -> bool:
        explicit = self.control(f"discovery:{app}")
        if explicit.get("override"):
            return explicit.get("until", 0) > time.time()
        return self.control("discovery:config").get("until", 0) > time.time()

    def observe(self, message: Message) -> bool:
        """来源按应用、会话、发送者去重；返回是否首次看见此会话。"""
        identifier = key_for(message.app_id, message.chat_id, message.sender_id)
        for attempt in range(2):
            try:
                with self.transaction() as db:
                    row = db.query(FeishuSource).filter_by(id=identifier).with_for_update().first()
                    new_chat = db.query(FeishuSource.id).filter_by(app_id=message.app_id, chat_id=message.chat_id).first() is None
                    now = int(time.time())
                    if row is None:
                        row = FeishuSource(id=identifier, app=message.app, app_id=message.app_id, chat_id=message.chat_id,
                            chat_type=message.chat_type, sender_id=message.sender_id, user_id=message.user_id,
                            first_seen=now, last_seen=now, message_count=0)
                        db.add(row)
                    row.last_seen, row.app = now, message.app
                    row.message_count += 1
                return new_chat
            except IntegrityError:
                if attempt:
                    raise
        return False

    def sources(self, app: str | None = None, kind: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        with self.sessions() as db:
            query = db.query(FeishuSource)
            if app:
                query = query.filter_by(app=app)
            if kind:
                query = query.filter_by(chat_type=kind)
            return [{**{field: getattr(row, field) for field in ("app", "app_id", "chat_id", "chat_type", "sender_id", "user_id", "first_seen", "last_seen", "message_count")},
                     "sender_open_id": row.sender_id}
                    for row in query.order_by(FeishuSource.last_seen.desc(), FeishuSource.id).offset(offset).limit(limit).all()]

    def accept(self, message: Message, pipeline: str, path: Path, context: dict[str, str]) -> bool:
        stream_id = key_for(pipeline, str(path))
        message_key = key_for(message.app_id, message.message_id)
        with file_lock(path), self.transaction() as db:
            if db.get(FeishuMessage, message_key):
                return False
            stream = db.query(FeishuStream).filter_by(id=stream_id).with_for_update().first()
            now = int(time.time())
            if stream is None:
                if db.query(FeishuStream.id).filter_by(input_path=str(path)).first():
                    raise ValueError("不同流程不能共享同一个输入文件，请合并到一个流程")
                stream = FeishuStream(id=stream_id, pipeline=pipeline, input_path=str(path), context=context,
                    batch_id=str(uuid.uuid4()), materialized=False, file_identity=None, started_at=now)
                db.add(stream)
            elif stream.materialized and not current_batch(path, stream.file_identity, stream.batch_id):
                stream.batch_id, stream.materialized, stream.file_identity, stream.started_at = str(uuid.uuid4()), False, None, now
            db.add(FeishuMessage(id=message_key, app=message.app, app_id=message.app_id, message_id=message.message_id,
                chat_id=message.chat_id,
                stream_id=stream_id, batch_id=stream.batch_id, text=message.text, sender_id=message.sender_id,
                create_time=message.timestamp_ms, status="pending", reaction_status="pending", attempts=0,
                next_attempt_at=0, received_at=now))
        return True

    def streams(self, pipeline: str | None = None) -> list[FeishuStream]:
        with self.sessions() as db:
            query = db.query(FeishuStream)
            if pipeline:
                query = query.filter_by(pipeline=pipeline)
            return query.all()

    def pending_messages(self, app: str) -> list[str]:
        with self.sessions() as db:
            return [row.id for row in db.query(FeishuMessage.id).filter(FeishuMessage.app == app,
                FeishuMessage.next_attempt_at <= int(time.time()),
                or_(FeishuMessage.status == "pending", (FeishuMessage.status == "written") & (FeishuMessage.reaction_status == "pending")))
                .order_by(FeishuMessage.received_at, FeishuMessage.create_time, FeishuMessage.id).limit(50).all()]

    def counts(self) -> dict[str, int]:
        with self.sessions() as db:
            return {"pending_messages": db.query(FeishuMessage).filter_by(status="pending").count(),
                    "failed_messages": db.query(FeishuMessage).filter_by(status="failed").count(),
                    "pending_receipts": db.query(FeishuMessage).filter_by(status="written", reaction_status="pending").count(),
                    "failed_receipts": db.query(FeishuMessage).filter_by(status="written", reaction_status="failed").count()}

    def maintain_sources(self, days: int, maximum: int) -> None:
        with self.transaction() as db:
            db.query(FeishuSource).filter(FeishuSource.last_seen < int(time.time()) - days * 86400).delete()
            stale = [row.id for row in db.query(FeishuSource.id).order_by(FeishuSource.last_seen.desc()).offset(maximum).all()]
            if stale:
                db.query(FeishuSource).filter(FeishuSource.id.in_(stale)).delete(synchronize_session=False)
