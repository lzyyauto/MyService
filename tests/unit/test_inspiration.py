import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.inspiration import (
    FeishuInspirationCollector,
    InspirationMessage,
    append_inspiration,
)


def build_event(
    message_id: str = "message-1",
    text: str = "一个灵感",
    message_type: str = "text",
) -> SimpleNamespace:
    message = SimpleNamespace(
        message_id=message_id,
        message_type=message_type,
        content=json.dumps({"text": text}),
        create_time="0",
    )
    return SimpleNamespace(event=SimpleNamespace(message=message))


def test_append_inspiration_uses_original_markdown_format(tmp_path) -> None:
    target = tmp_path / "nested" / "inspirations.md"

    path = append_inspiration(
        InspirationMessage("message-1", "测试灵感", "0"),
        target,
    )

    assert path == target.resolve()
    assert target.read_text(encoding="utf-8") == "- [08:00:00] 测试灵感\n"


def test_collector_queues_text_message_once(tmp_path) -> None:
    collector = FeishuInspirationCollector("app-id", "secret", tmp_path / "notes.md")
    event = build_event()

    collector.handle_event(event)
    collector.handle_event(event)

    assert collector._messages.qsize() == 1


def test_collector_ignores_non_text_message(tmp_path) -> None:
    collector = FeishuInspirationCollector("app-id", "secret", tmp_path / "notes.md")

    collector.handle_event(build_event(message_type="image"))

    assert collector._messages.empty()


def test_collector_persists_before_sending_reaction(tmp_path, monkeypatch) -> None:
    target = tmp_path / "notes.md"
    collector = FeishuInspirationCollector("app-id", "secret", target)
    reaction_calls: list[str] = []
    monkeypatch.setattr(collector, "add_reaction", reaction_calls.append)
    collector.handle_event(build_event())

    assert collector.process_next(timeout=0.1)
    assert target.read_text(encoding="utf-8") == "- [08:00:00] 一个灵感\n"
    assert reaction_calls == ["message-1"]


def test_collector_rejects_missing_credentials(tmp_path) -> None:
    with pytest.raises(ValueError, match="不能为空"):
        FeishuInspirationCollector("", "", tmp_path / "notes.md")


def test_tenant_token_is_cached_across_reactions(tmp_path, monkeypatch) -> None:
    token_response = MagicMock()
    token_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "tenant-token",
        "expire": 7200,
    }
    reaction_response = MagicMock()
    post = MagicMock(
        side_effect=[token_response, reaction_response, reaction_response]
    )
    monkeypatch.setattr("app.services.inspiration.requests.post", post)
    collector = FeishuInspirationCollector(
        "app-id",
        "secret",
        tmp_path / "notes.md",
    )

    collector.add_reaction("message-1")
    collector.add_reaction("message-2")

    assert post.call_count == 3
    assert post.call_args_list[0].args[0].endswith(
        "/tenant_access_token/internal"
    )
    assert post.call_args_list[1].kwargs["headers"]["Authorization"] == (
        "Bearer tenant-token"
    )
    token_response.raise_for_status.assert_called_once()
    assert reaction_response.raise_for_status.call_count == 2
