"""无 Docker／真实凭证的纯采集演示：临时 SQLite、本机回执替身和 Markdown。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect
from app.models.feishu import FeishuMessage
from app.services.feishu.collection import CollectionService
from app.services.feishu.config import ConfigManager
from app.services.feishu.events import Message
from app.services.feishu.store import Store,database_url


class Stub(BaseHTTPRequestHandler):
    receipt_requests=0

    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path.endswith('tenant_access_token/internal'):
            body={'code':0,'tenant_access_token':'local-placeholder','expire':7200}
        elif self.path.endswith('/reactions'):
            assert data == {'reaction_type':{'emoji_type':'OK'}}
            type(self).receipt_requests += 1
            if self.receipt_requests == 1:
                self.send_response(503)
                self.end_headers()
                return
            body={'code':0}
        else:
            raise AssertionError('采集演示不得请求 AI 或发送正文')
        encoded=json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self,*args):
        pass


def exercise(root:Path,endpoint:str,alias:str='demo') -> dict:
    """只读写调用者提供的临时目录，环境变量仅引用本地占位值。"""
    path=root/'demo.toml'
    path.write_text(f'''
[runtime]
root_dir = "."
state_backend = "sqlite"
database_url_env = "FEISHU_DEMO_STATE_OVERRIDE"
retry_seconds = 1
[[apps]]
id = "{alias}"
app_id_env = "FEISHU_DEMO_APP_ID"
app_secret_env = "FEISHU_DEMO_SECRET"
default_pipeline = "inspiration"
base_url = "{endpoint}"
[[pipelines]]
id = "inspiration"
input_path = "messages.md"
''')
    configs=ConfigManager(path)
    url=database_url(configs.current)
    store=Store(url)
    try:
        collection=CollectionService(configs,store)
        event=Message(alias,'cli_demo','om_first','oc_demo','group','ou_demo',None,int(time.time()*1000),'第一条\n多行记录','text')
        assert collection.receive(event)
        assert collection.flush(alias) == 1
        first=(root/'messages.md').read_text()
        assert '第一条\n多行记录' in first
        with store.transaction() as db:
            row=db.query(FeishuMessage).one()
            assert row.status == 'written' and row.text is None and row.reaction_status == 'pending'
            row.next_attempt_at=0
        store.close()
        store=Store(url)
        resumed=CollectionService(configs,store)
        assert not resumed.receive(event)
        assert resumed.flush(alias) == 0
        assert (root/'messages.md').read_text() == first
        assert store.counts()['pending_receipts'] == 0
        assert store.sources()[0]['sender_open_id'] == 'ou_demo'
        if store.engine.dialect.name == 'sqlite':
            assert 'feishu_runs' not in inspect(store.engine).get_table_names()
        (root/'messages.md').unlink()
        assert not resumed.receive(event)
        assert resumed.flush(alias) == 0 and not (root/'messages.md').exists()
        new=Message(alias,'cli_demo','om_second','oc_demo','p2p','ou_demo',None,int(time.time()*1000),'删除后的新记录','text')
        assert resumed.receive(new)
        assert resumed.flush(alias) == 1
        assert '删除后的新记录' in (root/'messages.md').read_text() and '第一条' not in (root/'messages.md').read_text()
        return {'ok':True,'mode':'collection_only_local_stubs','source_query':'passed','restart_deduplication':'passed',
                'receipt_retry_without_rewrite':'passed','deletion_and_new_message':'passed','ai_requests':0,'temporary_data_cleaned_on_exit':True}
    finally:
        store.close()


def main():
    Stub.receipt_requests=0
    server=ThreadingHTTPServer(('127.0.0.1',0),Stub)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    os.environ.update(FEISHU_DEMO_APP_ID='cli_demo',FEISHU_DEMO_SECRET='local-placeholder')
    os.environ.pop('FEISHU_DEMO_STATE_OVERRIDE',None)
    try:
        with tempfile.TemporaryDirectory(prefix='myservice-feishu-collect-') as directory:
            result=exercise(Path(directory),f'http://127.0.0.1:{server.server_port}')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
