"""把飞书事件转为不依赖 SDK 的消息，路由默认接收所有用户来源。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.feishu.config import ConfigSnapshot, Pipeline


@dataclass(frozen=True)
class Message:
    app: str
    app_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    user_id: str | None
    timestamp_ms: int
    text: str | None
    message_type: str
    mentions: tuple[str, ...] = ()
    mentioned_bot: bool | None = None
    sender_type: str = "user"


def parse_event(data: Any, app: str, app_id: str, bot_open_id: str | None = None) -> Message:
    event, message, sender = data.event, data.event.message, data.event.sender
    ids = sender.sender_id
    mention_ids = tuple(getattr(item.id, "open_id", "") for item in (message.mentions or []))
    text = json.loads(message.content).get("text", "") if message.message_type == "text" else None
    if not message.message_id or not message.chat_id or not getattr(ids, "open_id", None):
        raise ValueError("缺少消息／会话／用户标识")
    timestamp = int(message.create_time)
    if text is not None and not isinstance(text, str):
        raise ValueError("文本格式错误")
    return Message(app, app_id, message.message_id, message.chat_id, message.chat_type,
                   ids.open_id, getattr(ids, "user_id", None), timestamp, text,
                   message.message_type, mention_ids, bot_open_id in mention_ids if bot_open_id else None,
                   sender.sender_type)


def match_route(snapshot: ConfigSnapshot, message: Message) -> tuple[Pipeline | None, str]:
    if message.sender_type != "user":
        return None, "non_user"
    routes = [route for route in snapshot.config.routes if route.app == message.app
              and (route.chat_id is None or route.chat_id == message.chat_id)
              and (route.chat_type is None or route.chat_type == message.chat_type)]
    routes.sort(key=lambda route: (route.chat_id is not None, route.chat_type is not None), reverse=True)
    if routes:
        route = routes[0]
        if route.allowed_sender_ids and message.sender_id not in route.allowed_sender_ids:
            return None, "sender_filtered"
        if route.require_at and message.mentioned_bot is not True:
            return None, "at_filtered"
        pipeline, label = snapshot.pipeline(route.pipeline), route.id
    else:
        pipeline, label = snapshot.pipeline(snapshot.app(message.app).default_pipeline), "default"
    return (pipeline, label) if pipeline.enabled else (None, "pipeline_disabled")
