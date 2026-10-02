"""状态导入使用模拟连接，禁止访问真实数据库。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.feishu.state_transfer import import_sqlite


@pytest.fixture
def transfer(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    path.touch()
    reader = MagicMock()
    old = reader.connect.return_value.__enter__.return_value
    old.execute.return_value.scalar_one.return_value = 0
    old.execute.return_value.mappings.return_value = []
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    new = engine.begin.return_value.__enter__.return_value
    new.execute.return_value.first.return_value = None
    create = MagicMock(return_value=reader)
    monkeypatch.setattr("app.services.feishu.state_transfer.create_engine", create)
    return path, SimpleNamespace(engine=engine), old, new, reader, create


def test_import_rejects_incomplete_source_before_writing(transfer):
    path, target, old, new, reader, _ = transfer
    old.execute.return_value.scalar_one.return_value = 1
    with pytest.raises(ValueError, match="待处理"):
        import_sqlite(path, target)
    new.execute.assert_not_called()
    assert target.engine.begin.return_value.__exit__.call_args.args[0] is ValueError
    reader.dispose.assert_called_once()


@pytest.mark.parametrize("existing", [True, False])
def test_import_is_read_only_and_keeps_existing_records(transfer, existing):
    path, target, old, new, reader, create = transfer
    count = MagicMock()
    count.scalar_one.return_value = 0
    empty = MagicMock()
    empty.mappings.return_value = []
    controls = MagicMock()
    controls.mappings.return_value = [{"id": "discovery:unit", "value": {"until": 0}}]
    old.execute.side_effect = [MagicMock(), count, empty, empty, empty, controls]
    new.execute.return_value.first.return_value = ("discovery:unit",) if existing else None
    result = import_sqlite(path, target)
    assert result["source_modified"] is False
    assert result["tables"]["feishu_controls"] == {"inserted": int(not existing), "skipped": int(existing)}
    assert create.call_args.args[0].query == {"mode": "ro", "uri": "true"}
    assert sum(bool(call.args[0].is_insert) for call in new.execute.call_args_list) == int(not existing)
    reader.dispose.assert_called_once()


def test_import_requires_postgres_target(transfer):
    path, target, _, _, reader, create = transfer
    target.engine.dialect.name = "sqlite"
    with pytest.raises(ValueError, match="PostgreSQL"):
        import_sqlite(path, target)
    create.assert_not_called()
