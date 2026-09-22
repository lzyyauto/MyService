from unittest.mock import patch

from app.db import migration_baseline


def test_ensure_legacy_users_table_only_creates_the_required_table():
    """历史迁移前的兼容步骤不得退化为完整 create_all。"""
    with patch("app.db.migration_baseline.create_engine") as create_engine:
        engine = create_engine.return_value
        with patch.object(migration_baseline.User.__table__, "create") as create_table:
            migration_baseline.ensure_legacy_users_table()

    create_table.assert_called_once_with(bind=engine, checkfirst=True)
    engine.dispose.assert_called_once_with()
