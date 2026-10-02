"""统一功能测试的一次性 PostgreSQL：采集恢复及旧 SQLite 状态导入。"""

import os
import threading
from http.server import ThreadingHTTPServer

import pytest
from sqlalchemy.engine import URL

from app.services.feishu.collection import CollectionService
from app.services.feishu.config import ConfigManager
from app.services.feishu.events import Message
from app.services.feishu.state_transfer import import_sqlite
from app.services.feishu.store import Store
from scripts.feishu_local_demo import Stub, exercise

pytestmark = pytest.mark.functional


def test_postgres_collection_and_sqlite_import(prepared_backend, tmp_path, monkeypatch):
    # 只连接统一入口的一次性库，与项目 .env 隔离。
    url = URL.create("postgresql+psycopg2", username="functional", password="functional",
                     host="127.0.0.1", port=int(os.environ.get("FUNCTIONAL_TEST_DB_PORT", "15432")),
                     database="functional")
    monkeypatch.setenv("FEISHU_DEMO_STATE_OVERRIDE", url.render_as_string(hide_password=False))
    monkeypatch.setenv("FEISHU_DEMO_APP_ID", "cli_demo")
    monkeypatch.setenv("FEISHU_DEMO_SECRET", "local-placeholder")
    Stub.receipt_requests = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert exercise(tmp_path, f"http://127.0.0.1:{server.server_port}")["ok"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    old_path = tmp_path / "old-state.sqlite3"
    monkeypatch.delenv("FEISHU_DEMO_STATE_OVERRIDE")
    configs = ConfigManager(tmp_path / "demo.toml")
    source = Store(f"sqlite:///{old_path}")
    target = Store(url)
    try:
        collector = CollectionService(configs, source)
        message = Message("demo", "cli_import", "om_import", "oc_import", "p2p", "ou_import",
                          None, 0, "仅隔离数据", "text")
        assert collector.receive(message)
        with pytest.raises(ValueError, match="待处理"):
            import_sqlite(old_path, target)
        assert not target.sources("demo", "p2p") or all(s["app_id"] != "cli_import" for s in target.sources())
        assert collector.flush("demo", acknowledge=False) == 1
        result = import_sqlite(old_path, target)
        assert result["tables"]["feishu_messages"]["inserted"] == 1
        assert result["source_modified"] is False
        repeated = import_sqlite(old_path, target)
        assert repeated["tables"]["feishu_messages"] == {"inserted": 0, "skipped": 1}
        assert not CollectionService(configs, target).receive(message)
    finally:
        source.close()
        target.close()
