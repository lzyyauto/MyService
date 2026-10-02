"""采集事务用 mock、文档用 tmp_path；不访问数据库或网络。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.feishu import FeishuMessage, FeishuSource, FeishuStream
from app.services.feishu.collection import CollectionService
from app.services.feishu.config import ConfigManager
from app.services.feishu.files import identity
from app.services.feishu.store import Store, database_url
from app.services.feishu.transport import FeishuError
from tests.unit.test_feishu_config_and_events import config_path, make_message

@pytest.fixture
def fake_db():
    db = MagicMock()
    queries = {}
    def query(model):
        if model not in queries:
            q = MagicMock()
            for method in ("filter", "filter_by", "with_for_update", "order_by", "limit", "offset"):
                getattr(q, method).return_value = q
            q.first.return_value = None
            q.all.return_value = []
            queries[model] = q
        return queries[model]
    db.query.side_effect = query
    db.get.return_value = None
    return db


@pytest.fixture
def store(fake_db):
    instance = Store.__new__(Store)
    instance.engine = MagicMock()
    instance.engine.dialect.name = "sqlite"
    instance.sessions = MagicMock()
    instance.sessions.return_value.__enter__.return_value = fake_db
    return instance


@pytest.fixture
def stream(config_path):
    manager = ConfigManager(config_path)
    path = config_path.parent / "data" / "oc_any" / "messages.md"
    path.parent.mkdir(parents=True)
    path.write_text("- [2026-10-02 00:30:00+08:00] 原始想法\n")
    return FeishuStream(id="stream", pipeline="inspiration", input_path=str(path), batch_id="batch",
        context={"app_id": "cli_personal", "chat_id": "oc_any", "pipeline_id": "inspiration"},
        materialized=True, file_identity=identity(path), started_at=0)


def test_discovery_does_not_extend_on_reloads_and_explicit_stop_wins(store, fake_db) -> None:
    existing = SimpleNamespace(value={"version": "unchanged", "until": 9999999999})
    fake_db.get.return_value = existing
    store.configured_discovery("unchanged", True, 600)
    fake_db.merge.assert_not_called()
    store.configured_discovery("changed", True, 600)
    assert fake_db.merge.call_args.args[0].value["version"] == "changed"
    fake_db.get.return_value = SimpleNamespace(value={"override": True, "until": 0})
    assert not store.is_discovering("personal")
    store.discover("personal", 0)
    assert fake_db.merge.call_args.args[0].value["until"] == 0
    with pytest.raises(ValueError):
        store.discover("personal", 99999)


def test_source_query_and_pruning_are_metadata_only(store, fake_db) -> None:
    message = make_message()
    assert store.observe(message)
    source = fake_db.add.call_args.args[0]
    assert isinstance(source, FeishuSource) and source.chat_id == "oc_any"
    fake_db.query(FeishuSource).all.return_value = [source]
    rows = store.sources("personal", "group", 20, 10)
    assert rows[0]["sender_id"] == "ou_any" and "text" not in rows[0]
    fake_db.query(FeishuSource.id).all.return_value = [SimpleNamespace(id="old")]
    store.maintain_sources(90, 10)
    assert fake_db.query(FeishuSource).delete.call_count == 2


def test_accept_deduplicates_before_any_file_write_and_rotates_deleted_batch(store, fake_db, stream) -> None:
    from pathlib import Path
    message = make_message()
    fake_db.get.return_value = SimpleNamespace(id="existing")
    assert not store.accept(message, "inspiration", Path(stream.input_path), stream.context)
    fake_db.add.assert_not_called()
    fake_db.get.return_value = None
    fake_db.query(FeishuStream).first.return_value = stream
    Path(stream.input_path).unlink()
    assert store.accept(message, "inspiration", Path(stream.input_path), stream.context)
    assert stream.batch_id != "batch" and stream.materialized is False
    assert fake_db.add.call_args.args[0].batch_id == stream.batch_id


def test_accept_creates_new_stream_and_rejects_cross_pipeline_path(store, fake_db, tmp_path) -> None:
    path = tmp_path / "messages.md"
    assert store.accept(make_message(), "inspiration", path, {"chat_id": "oc_any"})
    assert any(isinstance(call.args[0], FeishuStream) for call in fake_db.add.call_args_list)
    fake_db.query(FeishuStream.id).first.return_value = SimpleNamespace(id="other")
    with pytest.raises(ValueError):
        store.accept(make_message(), "other", path, {})


def test_collection_defaults_and_filters_without_network(config_path) -> None:
    store = MagicMock()
    store.is_discovering.return_value = False
    store.observe.return_value = True
    store.accept.return_value = True
    service = CollectionService(ConfigManager(config_path), store)
    assert service.receive(make_message())
    assert not service.receive(make_message(chat_id="oc_restricted"))
    assert not service.receive(make_message(text=None, message_type="image"))
    assert store.accept.call_count == 1
    assert service.counts["received"] == 3


def test_collection_flush_persists_before_reaction_and_clears_raw_text(config_path, store, fake_db, stream, monkeypatch) -> None:
    from pathlib import Path
    message = FeishuMessage(id="message", message_id="om_unit", app="personal", app_id="cli_personal", stream_id="stream",
        batch_id="batch", text="新原文", sender_id="ou_sender", create_time=0, status="pending", attempts=0, reaction_status="pending")
    fake_db.get.side_effect = lambda model, key: stream if model is FeishuStream else (message if model is FeishuMessage else None)
    fake_db.query(FeishuMessage.id).all.return_value = [SimpleNamespace(id="message")]
    fake_db.query(FeishuMessage).one.return_value = message
    fake_db.query(FeishuStream).one.return_value = stream
    transport = MagicMock()
    transport.credentials.return_value = ("cli_personal", "test-placeholder")
    def reaction(identifier):
        assert "新原文" in Path(stream.input_path).read_text() and message.text is None
    transport.reaction.side_effect = reaction
    monkeypatch.setattr("app.services.feishu.collection.FeishuTransport", lambda app: transport)
    service = CollectionService(ConfigManager(config_path), store)
    assert service.flush("personal") == 1
    assert message.reaction_status == "sent"
    transport.reaction.assert_called_once_with("om_unit")



def test_transaction_commits_or_rolls_back(store, fake_db):
    with store.transaction() as db:
        assert db is fake_db
    fake_db.commit.assert_called_once()
    with pytest.raises(RuntimeError), store.transaction():
        raise RuntimeError("local failure")
    fake_db.rollback.assert_called_once()
    assert fake_db.execute.call_count == 2


def test_database_defaults_to_project_pg_and_supports_explicit_override(monkeypatch, config_path):
    snapshot = ConfigManager(config_path).current
    monkeypatch.delenv("FEISHU_STATE_DATABASE_URL", raising=False)
    values = {"POSTGRES_USER": "pg_user", "POSTGRES_PASSWORD": "p@ss:/%word",
              "POSTGRES_DB": "project_db", "POSTGRES_HOST": "db", "POSTGRES_PORT": "5433"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    url = database_url(snapshot)
    assert url.get_backend_name() == "postgresql"
    assert (url.username, url.password, url.database, url.host, url.port) == ("pg_user", "p@ss:/%word", "project_db", "db", 5433)
    assert "p@ss" not in str(url)
    monkeypatch.setenv("FEISHU_STATE_DATABASE_URL", "postgresql://invalid.test/private")
    assert database_url(snapshot) == "postgresql://invalid.test/private"
    monkeypatch.setenv("FEISHU_STATE_DATABASE_URL", "sqlite:///existing.sqlite3")
    assert database_url(snapshot) == "sqlite:///existing.sqlite3"
    monkeypatch.setenv("FEISHU_STATE_DATABASE_URL", "mysql://invalid.test/private")
    with pytest.raises(ValueError): database_url(snapshot)
    monkeypatch.delenv("FEISHU_STATE_DATABASE_URL")


def test_explicit_sqlite_backend_remains_isolated(monkeypatch, config_path):
    monkeypatch.delenv("FEISHU_STATE_DATABASE_URL", raising=False)
    config_path.write_text(config_path.read_text().replace('root_dir = "."', 'root_dir = "."\nstate_backend = "sqlite"'))
    snapshot = ConfigManager(config_path).current
    assert database_url(snapshot) == f"sqlite:///{config_path.parent}/data/feishu/state.sqlite3"


def test_store_auto_initializes_only_collection_tables_without_real_database(monkeypatch, tmp_path):
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    table = MagicMock()
    create = MagicMock(return_value=engine)
    monkeypatch.setattr("app.services.feishu.store.create_engine", create)
    monkeypatch.setattr("app.services.feishu.store.FEISHU_TABLES", [table])
    instance = Store(f"sqlite:///{tmp_path}/state.sqlite3")
    table.create.assert_called_once_with(engine, checkfirst=True)
    engine.connect.assert_not_called()
    instance.close()
    for invalid in ['mysql://invalid.test/db','sqlite:///:memory:']:
        with pytest.raises(ValueError): Store(invalid)


def test_collection_status_counts_and_closes_store(store, fake_db):
    fake_db.query(FeishuMessage).count.return_value = 2
    assert store.counts() == {name:2 for name in ['pending_messages','failed_messages','pending_receipts','failed_receipts']}
    store.close()
    store.engine.dispose.assert_called_once()


def test_receipt_failure_does_not_rewrite_document(config_path, store, fake_db, stream, monkeypatch):
    message = FeishuMessage(id="message", message_id="om_unit", app="personal", app_id="cli_personal", stream_id="stream",
        batch_id="batch", text="新原文", sender_id="ou_sender", create_time=0, status="pending", attempts=0, reaction_status="pending")
    fake_db.get.side_effect = lambda model, key: stream if model is FeishuStream else (message if model is FeishuMessage else None)
    fake_db.query(FeishuMessage.id).all.return_value = [SimpleNamespace(id="message")]
    fake_db.query(FeishuMessage).one.return_value = message
    fake_db.query(FeishuStream).one.return_value = stream
    transport = MagicMock()
    transport.credentials.return_value = ("cli_personal", "test-placeholder")
    transport.reaction.side_effect = FeishuError("feishu_http_503", True)
    monkeypatch.setattr("app.services.feishu.collection.FeishuTransport", lambda app: transport)
    service = CollectionService(ConfigManager(config_path), store)
    assert service.flush("personal") == 1
    assert message.status == "written" and message.reaction_status == "pending" and message.text is None
    first = Path(stream.input_path).read_text()
    transport.reaction.side_effect = None
    service.flush("personal")
    assert message.reaction_status == "sent" and Path(stream.input_path).read_text() == first


def test_postgres_store_checks_schema_without_creating_tables(monkeypatch):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    create = MagicMock(return_value=engine)
    monkeypatch.setattr("app.services.feishu.store.create_engine", create)
    table = MagicMock()
    monkeypatch.setattr("app.services.feishu.store.FEISHU_TABLES", [table])
    monkeypatch.setattr("app.services.feishu.store.select", lambda table: MagicMock())
    sessions = MagicMock()
    monkeypatch.setattr("app.services.feishu.store.sessionmaker", lambda **kwargs: sessions)
    instance = Store("postgresql://invalid.test/db")
    table.create.assert_not_called()
    assert create.call_args.kwargs["pool_pre_ping"] is True
    assert create.call_args.kwargs["pool_size"] == 2
    engine.connect.return_value.__enter__.return_value.execute.assert_called_once()
    with instance.transaction() as session:
        session.execute.assert_not_called()
    session.commit.assert_called_once()


def test_missing_postgres_schema_is_safe_and_closes_engine(monkeypatch):
    from sqlalchemy.exc import ProgrammingError
    from app.services.feishu.store import StateSchemaError
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    error = ProgrammingError("private SQL", {"secret": "private"}, SimpleNamespace(pgcode="42P01"))
    engine.connect.return_value.__enter__.return_value.execute.side_effect = error
    monkeypatch.setattr("app.services.feishu.store.create_engine", lambda *args, **kwargs: engine)
    with pytest.raises(StateSchemaError) as result:
        Store("postgresql://invalid.test/db")
    assert "private" not in str(result.value)
    engine.dispose.assert_called_once()
