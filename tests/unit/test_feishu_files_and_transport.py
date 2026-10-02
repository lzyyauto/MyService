import logging
import os
import time
from unittest.mock import MagicMock

import pytest
import requests

from app.services.feishu.config import App, Observability
from app.services.feishu.files import append_record, current_batch, identity
from app.services.feishu.observability import LimitedLogHandler
from app.services.feishu.transport import FeishuError, FeishuTransport


def test_partial_write_recovery_and_multiline_do_not_duplicate(tmp_path):
    path = tmp_path / "messages.md"
    path.write_text("<!-- myservice-message:message1 -->\n半条")
    before = identity(path)
    append_record(path, "message1", "完整\n第二行", 0, "ou_sender", "batch", "oc_source")
    append_record(path, "message1", "完整\n第二行", 0, "ou_sender", "batch", "oc_source")
    assert identity(path) == before and path.read_text().count("完整") == 1
    assert "1970-01-01 08:00:00+08:00" in path.read_text()
    assert "第二行" in path.read_text() and "chat=oc_source" in path.read_text()
    assert current_batch(path, before, "batch")


def test_deleted_document_only_recreates_with_new_message(tmp_path):
    path = tmp_path / "messages.md"
    append_record(path, "message1", "旧内容", 0, "ou_sender", "old")
    before = identity(path)
    path.unlink()
    assert not current_batch(path, before, "old")
    append_record(path, "message2", "新内容", 0, "ou_sender", "new")
    assert "旧内容" not in path.read_text()
    assert current_batch(path, identity(path), "new")


def test_log_retention_and_size_never_touch_user_documents(tmp_path):
    expired = tmp_path / "feishu-2020-01-01-000000.log"
    expired.write_text("old")
    os.utime(expired, (time.time()-10*86400,)*2)
    protected = tmp_path / "messages.md"
    protected.write_text("原文")
    handler = LimitedLogHandler(tmp_path, Observability(max_file_mb=1,max_total_mb=1))
    assert not expired.exists() and protected.exists()
    for _ in range(150):
        handler.emit(logging.LogRecord("app.services.feishu.test", logging.INFO, "",0,"x"*8192,(),None))
    assert sum(p.stat().st_size for p in tmp_path.glob("feishu-*.log")) <= 1024*1024
    handler.close()


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("UNIT_APP_ID", "cli_unit")
    monkeypatch.setenv("UNIT_APP_SECRET", "test-placeholder")
    app = App(id="unit",app_id_env="UNIT_APP_ID",app_secret_env="UNIT_APP_SECRET",default_pipeline="unit")
    return FeishuTransport(app,MagicMock())


def test_cached_token_and_basic_reaction(transport):
    transport.http.post.return_value.status_code = 200
    transport.http.post.return_value.json.side_effect = [
        {"code":0,"tenant_access_token":"local-placeholder","expire":7200},{"code":0},{"code":0}]
    transport.reaction("om_1")
    transport.reaction("om_2")
    assert transport.http.post.call_count == 3
    assert transport.http.post.call_args.kwargs['json'] == {"reaction_type":{"emoji_type":"OK"}}


@pytest.mark.parametrize("status,retryable", [(401,False),(429,True),(503,True)])
def test_http_errors_hide_remote_payload(transport,status,retryable):
    transport.token,transport.expires = "local-placeholder",time.time()+7200
    transport.http.post.return_value.status_code = status
    transport.http.post.return_value.text = "private payload"
    with pytest.raises(FeishuError) as raised: transport.reaction("om_1")
    assert raised.value.retryable is retryable and 'private' not in str(raised.value)


def test_business_failure_and_network_errors(transport):
    transport.http.post.return_value.status_code=200
    transport.http.post.return_value.json.return_value={"code":99991672,"msg":"private payload"}
    with pytest.raises(FeishuError,match='feishu_code_99991672'): transport.reaction('om_1')
    transport.http.post.side_effect=requests.Timeout()
    with pytest.raises(FeishuError,match='feishu_network_error'): transport.reaction('om_1')
