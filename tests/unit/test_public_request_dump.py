import base64
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.public_request_dump import router


def test_public_request_dump_echoes_raw_request_without_authentication(caplog) -> None:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1/public-request-dump")
    raw_body = b'{"source":"third-party","value":"\xff"}'

    with caplog.at_level(logging.WARNING):
        response = TestClient(test_app).post(
            "/api/v1/public-request-dump/?source=first&source=second",
            content=raw_body,
            headers={"X-Webhook-Token": "not-validated"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/v1/public-request-dump/"
    assert payload["query_params"] == [
        {"name": "source", "value": "first"},
        {"name": "source", "value": "second"},
    ]
    assert {item["name"]: item["value"] for item in payload["headers"]}["x-webhook-token"] == "not-validated"
    assert payload["body"] == {
        "size_bytes": len(raw_body),
        "utf8_text": raw_body.decode("utf-8", errors="replace"),
        "base64": base64.b64encode(raw_body).decode("ascii"),
    }
    assert payload["body"]["base64"] in caplog.text
