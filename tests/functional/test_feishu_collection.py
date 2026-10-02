"""纯采集链路使用临时 SQLite 与本地 HTTP 回执替身，不接触业务库。"""

import threading
from http.server import ThreadingHTTPServer

import pytest

from scripts.feishu_local_demo import Stub,exercise

pytestmark=pytest.mark.functional


def test_collection_local_state_and_receipt_recovery(tmp_path,monkeypatch):
    monkeypatch.setenv('FEISHU_DEMO_APP_ID','cli_demo')
    monkeypatch.setenv('FEISHU_DEMO_SECRET','local-placeholder')
    monkeypatch.delenv('FEISHU_DEMO_STATE_OVERRIDE',raising=False)
    Stub.receipt_requests=0
    server=ThreadingHTTPServer(('127.0.0.1',0),Stub)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        result=exercise(tmp_path,f'http://127.0.0.1:{server.server_port}')
        assert result['ok'] and result['ai_requests'] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
