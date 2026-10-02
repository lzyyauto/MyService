"""采集事务、崩溃恢复、回执重试与稀疏运行日志。"""

from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path

from app.models.feishu import FeishuMessage, FeishuStream
from app.services.feishu.config import ConfigManager
from app.services.feishu.events import Message, match_route
from app.services.feishu.files import append_record, current_batch, file_lock, identity
from app.services.feishu.store import Store, key_for
from app.services.feishu.transport import FeishuError, FeishuTransport

logger = logging.getLogger(__name__)


class CollectionService:
    def __init__(self, configs: ConfigManager, store: Store) -> None:
        self.configs, self.store = configs, store
        self.counts: Counter = Counter()
        self.last_summary = time.monotonic()
        self.discovery_window, self.discovery_count = 0, 0
        self.discovery_active: dict[str, bool] = {}

    def sync_discovery(self, alias: str) -> None:
        settings = self.configs.refresh().config.observability.discovery
        self.store.configured_discovery(key_for(str(settings.enabled), str(settings.duration_seconds)), settings.enabled, settings.duration_seconds)
        active = self.store.is_discovering(alias)
        previous = self.discovery_active.get(alias, False)
        if previous != active:
            logger.info("event=feishu.discovery app=%s status=%s", alias, "enabled" if active else "expired_or_disabled")
        self.discovery_active[alias] = active

    def receive(self, message: Message) -> bool:
        snapshot = self.configs.refresh()
        self.counts["received"] += 1
        if message.sender_type != "user":
            self.counts["filtered"] += 1
            return False
        if self.store.observe(message):
            logger.info("event=feishu.new_source app=%s chat_type=%s chat_id=%s", message.app, message.chat_type, message.chat_id)
        pipeline, route = match_route(snapshot, message)
        self.sync_discovery(message.app)
        if self.store.is_discovering(message.app):
            minute = int(time.time()) // 60
            if self.discovery_window != minute:
                self.discovery_window, self.discovery_count = minute, 0
            if self.discovery_count < 60:
                logger.info("event=feishu.source app=%s chat_type=%s chat_id=%s sender_open_id=%s sender_user_id=%s message_id=%s message_type=%s mentions=%s mentioned_bot=%s route=%s",
                    message.app, message.chat_type, message.chat_id, message.sender_id, message.user_id or "unavailable", message.message_id,
                    message.message_type, ",".join(message.mentions), message.mentioned_bot if message.mentioned_bot is not None else "unknown", route)
                self.discovery_count += 1
            else:
                self.counts["discovery_suppressed"] += 1
        if pipeline is None or message.text is None or not message.text.strip():
            self.counts["filtered" if pipeline is None else "unsupported_or_empty"] += 1
            return False
        context = dict(app_id=message.app_id, chat_id=message.chat_id, pipeline_id=pipeline.id)
        path = snapshot.path(pipeline.input_path, **context)
        accepted = self.store.accept(message, pipeline.id, path, context)
        self.counts["accepted" if accepted else "duplicate"] += 1
        logger.debug("event=feishu.received app=%s message_id=%s route=%s path=%s", message.app, message.message_id, route, path)
        return accepted

    def flush(self, app_alias: str, acknowledge: bool = True) -> int:
        snapshot = self.configs.refresh()
        self.sync_discovery(app_alias)
        app = snapshot.app(app_alias)
        transport = FeishuTransport(app)
        written = 0
        for identifier in self.store.pending_messages(app_alias):
            try:
                with self.store.sessions() as db:
                    message = db.get(FeishuMessage, identifier)
                    stream = db.get(FeishuStream, message.stream_id)
                    path = Path(stream.input_path)
                with file_lock(path), self.store.transaction() as db:
                    message = db.query(FeishuMessage).filter_by(id=identifier).with_for_update().one()
                    stream = db.query(FeishuStream).filter_by(id=message.stream_id).with_for_update().one()
                    if message.status == "pending":
                        if message.batch_id != stream.batch_id or (stream.materialized and not current_batch(path, stream.file_identity, stream.batch_id)):
                            message.status, message.text, message.reaction_status = "cancelled", None, "cancelled"
                            continue
                        append_record(path, identifier, message.text or "", message.create_time, message.sender_id, stream.batch_id, message.chat_id)
                        stream.materialized, stream.file_identity = True, identity(path)
                        message.status, message.text, message.attempts = "written", None, 0
                        written += 1
                        self.counts["written"] += 1
                    message_id, app_id = message.message_id, message.app_id
                if acknowledge:
                    if transport.credentials()[0] != app_id:
                        raise FeishuError("feishu_app_changed")
                    transport.reaction(message_id)
                with self.store.transaction() as db:
                    message = db.get(FeishuMessage, identifier)
                    message.reaction_status, message.attempts = "sent" if acknowledge else "disabled", 0
            except (OSError, FeishuError) as error:
                code = error.code if isinstance(error, FeishuError) else "file_write_failed"
                with self.store.transaction() as db:
                    message = db.get(FeishuMessage, identifier)
                    message.attempts += 1
                    message.next_attempt_at = int(time.time()) + snapshot.config.runtime.retry_seconds
                    if message.attempts >= snapshot.config.runtime.max_attempts or (isinstance(error, FeishuError) and not error.retryable):
                        if message.status == "written":
                            message.reaction_status = "failed"
                        else:
                            message.status = "failed"
                self.counts["failed"] += 1
                logger.error("event=feishu.collection_failed app=%s message_key=%s error=%s", app_alias, identifier, code)
        if self.counts and time.monotonic() - self.last_summary >= snapshot.config.observability.summary_interval_seconds:
            logger.info("event=feishu.summary app=%s counts=%s", app_alias, dict(self.counts))
            self.counts.clear()
            self.last_summary = time.monotonic()
        return written
