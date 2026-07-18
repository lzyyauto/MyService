import json
from types import SimpleNamespace

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
