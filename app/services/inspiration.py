"""飞书灵感消息的解析、去重、落盘和回执服务。"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import lark_oapi as lark
import requests

logger = logging.getLogger(__name__)

CHINA_TIMEZONE = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class InspirationMessage:
    message_id: str
    text: str
    create_time: str


def append_inspiration(
    message: InspirationMessage,
    target_path: str | Path,
) -> Path:
    """将一条灵感按原项目格式追加到 Markdown 文件。"""
    created_at = datetime.fromtimestamp(
        int(message.create_time) / 1000,
        tz=CHINA_TIMEZONE,
    )
    path = Path(target_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(f"- [{created_at:%H:%M:%S}] {message.text}\n")
    return path


class FeishuInspirationCollector:
    """接收飞书长连接事件，并在后台完成持久化和消息回执。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        target_path: str | Path,
        base_url: str = "https://open.feishu.cn",
        request_timeout: float = 10.0,
        deduplication_window: int = 2_000,
    ) -> None:
        if not app_id or not app_secret:
            raise ValueError("FEISHU_APP_ID 和 FEISHU_APP_SECRET 不能为空")

        self.app_id = app_id
        self.app_secret = app_secret
        self.target_path = Path(target_path)
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self._messages: queue.Queue[InspirationMessage | None] = queue.Queue()
        self._seen_ids: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._deduplication_window = deduplication_window
        self._deduplication_lock = threading.Lock()
        self._token = ""
        self._token_expires_at = 0

    def handle_event(self, data: Any) -> None:
        """快速解析并入队，避免阻塞飞书事件回调。"""
        try:
            message = data.event.message
            if message.message_type != "text":
                return

            text = json.loads(message.content).get("text", "").strip()
            message_id = message.message_id
            if not text or not message_id:
                return

            if not self._remember(message_id):
                return
            self._messages.put(
                InspirationMessage(
                    message_id=message_id,
                    text=text,
                    create_time=message.create_time,
                )
            )
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            logger.exception("无法解析飞书消息事件")

    def process_next(self, timeout: float | None = None) -> bool:
        """处理队列中的一条消息；返回 False 表示收到停止信号。"""
        message = self._messages.get(timeout=timeout)
        try:
            if message is None:
                return False
            path = append_inspiration(message, self.target_path)
            logger.info("灵感已写入 %s", path)
            self.add_reaction(message.message_id)
            return True
        finally:
            self._messages.task_done()

    def run(self) -> None:
        """启动后台消费者和阻塞式飞书 WebSocket 客户端。"""
        worker = threading.Thread(
            target=self._consume_messages,
            name="inspiration-writer",
            daemon=True,
        )
        worker.start()

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.handle_event)
            .build()
        )
        client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        logger.info("正在连接飞书 WebSocket，灵感文档：%s", self.target_path.resolve())
        try:
            client.start()
        finally:
            self._messages.put(None)
            worker.join(timeout=5)

    def add_reaction(self, message_id: str) -> None:
        """为已持久化的消息添加 OK 回执。"""
        response = requests.post(
            f"{self.base_url}/open-apis/im/v1/messages/{message_id}/reactions",
            headers={
                "Authorization": f"Bearer {self._get_tenant_access_token()}",
                "Content-Type": "application/json",
            },
            json={"reaction_type": {"emoji_type": "OK"}},
            timeout=self.request_timeout,
        )
        response.raise_for_status()

    def _get_tenant_access_token(self) -> str:
        now = int(datetime.now().timestamp())
        if self._token and self._token_expires_at > now + 60:
            return self._token

        response = requests.post(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 tenant_access_token 失败：{data}")

        self._token = data["tenant_access_token"]
        self._token_expires_at = now + data.get("expire", 7200)
        return self._token

    def _consume_messages(self) -> None:
        while True:
            try:
                if not self.process_next():
                    return
            except Exception:
                logger.exception("持久化灵感或添加飞书回执失败")

    def _remember(self, message_id: str) -> bool:
        with self._deduplication_lock:
            if message_id in self._seen_ids:
                return False
            self._seen_ids.add(message_id)
            self._seen_order.append(message_id)
            if len(self._seen_order) > self._deduplication_window:
                self._seen_ids.discard(self._seen_order.popleft())
            return True
