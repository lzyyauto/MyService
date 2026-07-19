import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.services.inspiration import FeishuInspirationCollector

pytestmark = pytest.mark.functional


class FeishuStubHandler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_POST(self) -> None:
        self.__class__.requests.append(self.path)
        body = (
            {"code": 0, "tenant_access_token": "stub-token", "expire": 7200}
            if self.path.endswith("/tenant_access_token/internal")
            else {"code": 0}
        )
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        return


def test_event_to_markdown_and_reaction_pipeline(tmp_path) -> None:
    FeishuStubHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FeishuStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = tmp_path / "inspirations.md"
        collector = FeishuInspirationCollector(
            app_id="app-id",
            app_secret="secret",
            target_path=target,
            base_url=f"http://127.0.0.1:{server.server_port}",
        )
        message = SimpleNamespace(
            message_id="message-1",
            message_type="text",
            content=json.dumps({"text": "功能测试灵感"}),
            create_time="0",
        )

        collector.handle_event(SimpleNamespace(event=SimpleNamespace(message=message)))
        assert collector.process_next(timeout=1)

        assert target.read_text(encoding="utf-8") == "- [08:00:00] 功能测试灵感\n"
        assert FeishuStubHandler.requests == [
            "/open-apis/auth/v3/tenant_access_token/internal",
            "/open-apis/im/v1/messages/message-1/reactions",
        ]
    finally:
        server.shutdown()
        server.server_close()
