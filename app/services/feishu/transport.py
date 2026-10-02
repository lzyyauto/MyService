"""飞书采集鉴权与基本表情回执；不发送总结或调用 AI。"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from app.services.feishu.config import App


class FeishuError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable


class FeishuTransport:
    def __init__(self, app: App, session: Any = None) -> None:
        self.app = app
        self.http = session or requests
        self.token, self.expires = "", 0.0

    def credentials(self) -> tuple[str, str]:
        app_id, secret = os.environ.get(self.app.app_id_env, ""), os.environ.get(self.app.app_secret_env, "")
        if not app_id or not secret:
            raise FeishuError("feishu_credentials_missing")
        return app_id, secret

    def _post(self, path: str, payload: dict[str, Any], authenticated: bool = True) -> dict:
        try:
            response = self.http.post(f"{self.app.base_url.rstrip('/')}{path}",
                headers={"Authorization": f"Bearer {self._token()}"} if authenticated else {},
                json=payload, timeout=10)
        except requests.RequestException as error:
            raise FeishuError("feishu_network_error", True) from error
        if response.status_code >= 400:
            raise FeishuError(f"feishu_http_{response.status_code}", response.status_code == 429 or response.status_code >= 500)
        try:
            body = response.json()
            code = body["code"]
        except (ValueError, TypeError, KeyError) as error:
            raise FeishuError("feishu_invalid_response") from error
        if code != 0:
            if code in {99991661, 99991663, 99991664, 99991668}:
                self.token, self.expires = "", 0.0
            raise FeishuError(f"feishu_code_{code}", code in {99991400, 99991661, 99991663, 99991664, 99991668})
        return body

    def _token(self) -> str:
        if self.token and self.expires > time.time() + 60:
            return self.token
        app_id, secret = self.credentials()
        body = self._post("/open-apis/auth/v3/tenant_access_token/internal",
                          {"app_id": app_id, "app_secret": secret}, authenticated=False)
        token = body.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("feishu_token_missing")
        self.token, self.expires = token, time.time() + int(body.get("expire", 7200))
        return token

    def reaction(self, message_id: str) -> None:
        self._post(f"/open-apis/im/v1/messages/{message_id}/reactions", {"reaction_type": {"emoji_type": "OK"}})

    def bot_open_id(self) -> str | None:
        """只有 require_at 配置需要时调用；无需该配置则不请求机器人资料。"""
        try:
            response = self.http.get(f"{self.app.base_url.rstrip('/')}/open-apis/bot/v3/info",
                headers={"Authorization": f"Bearer {self._token()}"}, timeout=10)
            body = response.json()
            if response.status_code != 200 or body.get("code") != 0:
                return None
            return body.get("bot", {}).get("open_id")
        except (requests.RequestException, ValueError, TypeError):
            return None
