from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.feishu.config import ConfigManager, FeishuConfig
from app.services.feishu.events import Message, match_route, parse_event


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.toml"
    path.write_text('''
version = 1
[runtime]
root_dir = "."
[[apps]]
id = "personal"
app_id_env = "TEST_APP_ID"
app_secret_env = "TEST_SECRET"
default_pipeline = "inspiration"
[[routes]]
id = "restricted"
app = "personal"
chat_id = "oc_restricted"
pipeline = "inspiration"
allowed_sender_ids = ["ou_owner"]
require_at = true
[[pipelines]]
id = "inspiration"
input_path = "data/{chat_id}/messages.md"
''', encoding="utf-8")
    return path


def make_message(**changes) -> Message:
    return replace(Message("personal", "cli_personal", "om_1", "oc_any", "group", "ou_any", None, 0, "原文", "text"), **changes)


def test_hot_reload_is_atomic_and_keeps_last_valid_config(config_path):
    manager = ConfigManager(config_path)
    original = manager.current
    good = config_path.read_text()
    config_path.write_text(good.replace("messages.md", "new.md"))
    changed = manager.refresh()
    assert changed.pipeline("inspiration").input_path.endswith("new.md")
    assert original.pipeline("inspiration").input_path.endswith("messages.md")
    config_path.write_text("invalid = [")
    assert manager.refresh() is changed
    config_path.write_text(good)
    assert manager.refresh().pipeline("inspiration").input_path.endswith("messages.md")


@pytest.mark.parametrize("change", ['root_dir = ".."', 'state_path = "other.sqlite3"'])
def test_runtime_change_requires_restart(config_path, change):
    manager = ConfigManager(config_path)
    old = manager.current
    text = config_path.read_text()
    config_path.write_text(text.replace('root_dir = "."', change if change.startswith('root_dir') else 'root_dir = "."\n'+change))
    assert manager.refresh() is old


def test_log_directory_changes_require_restart(config_path):
    manager = ConfigManager(config_path)
    config_path.write_text(config_path.read_text() + '\n[observability]\nlog_dir = "different-logs"\n')
    assert manager.refresh().config.observability.log_dir != "different-logs"
    assert ConfigManager(config_path).current.config.observability.log_dir == "different-logs"


@pytest.mark.parametrize("kind", ["p2p", "group"])
def test_default_route_accepts_any_user_without_at(config_path, kind):
    pipeline, rule = match_route(ConfigManager(config_path).current, make_message(chat_type=kind))
    assert pipeline.id == "inspiration" and rule == "default"


def test_explicit_filter_does_not_fall_back_to_default(config_path):
    snapshot = ConfigManager(config_path).current
    assert match_route(snapshot, make_message(chat_id="oc_restricted")) == (None, "sender_filtered")
    assert match_route(snapshot, make_message(chat_id="oc_restricted", sender_id="ou_owner")) == (None, "at_filtered")
    assert match_route(snapshot, make_message(chat_id="oc_restricted", sender_id="ou_owner", mentioned_bot=True))[1] == "restricted"
    assert match_route(snapshot, make_message(sender_type="app")) == (None, "non_user")


@pytest.mark.parametrize("template", ['data/{run_id}.md','data/{date}.md','data/{unknown}.md','data/{chat_id:2}.md'])
def test_templates_only_allow_source_identifiers(config_path, template):
    snapshot = ConfigManager(config_path).current
    with pytest.raises(ValueError):
        snapshot.path("data/{chat_id}/messages.md", chat_id="../private")
    data = snapshot.config.model_dump()
    data["pipelines"][0]["input_path"] = template
    with pytest.raises(ValueError):
        FeishuConfig.model_validate(data)


def test_parse_event_keeps_multiline_and_identifies_bot_at():
    message = SimpleNamespace(message_id="om_1", chat_id="oc_1", chat_type="p2p", create_time="1000",
        message_type="text", content='{"text":"一行\\n二行"}', mentions=[SimpleNamespace(id=SimpleNamespace(open_id="ou_bot"))])
    sender = SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_sender", user_id=None), sender_type="user")
    parsed = parse_event(SimpleNamespace(event=SimpleNamespace(message=message, sender=sender)), "personal", "cli_1", "ou_bot")
    assert parsed.text == "一行\n二行" and parsed.mentioned_bot is True


@pytest.mark.parametrize("change", ["route", "default", "duplicate", "handler", "ai"])
def test_invalid_references_and_removed_ai_are_rejected(config_path, change):
    data = ConfigManager(config_path).current.config.model_dump()
    if change == "route": data["routes"][0]["app"] = "missing"
    elif change == "default": data["apps"][0]["default_pipeline"] = "missing"
    elif change == "duplicate": data["pipelines"].append(data["pipelines"][0])
    elif change == "handler": data["pipelines"][0]["handler"] = "agent"
    else: data["pipelines"][0]["ai"] = {"enabled": True}
    with pytest.raises(ValueError): FeishuConfig.model_validate(data)


@pytest.mark.parametrize("path", ['data/logs/feishu/user.md','data/feishu/state.sqlite3'])
def test_business_file_cannot_be_log_or_state_file(config_path, path):
    config_path.write_text(config_path.read_text().replace('data/{chat_id}/messages.md', path))
    with pytest.raises(ValueError): ConfigManager(config_path)
