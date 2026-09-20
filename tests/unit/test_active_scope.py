import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.deprecation import create_disabled_router
from app.main import app, create_app


def test_only_active_http_routes_are_registered(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_PUBLIC_REQUEST_DUMP", False)
    disabled_app = create_app()
    paths = {route.path for route in disabled_app.routes}

    assert paths == {
        "/",
        "/api/v1/openapi.json",
        "/api/v1/notion-ingest/",
        "/api/v1/notion-ingest/mappings",
        "/api/v1/notion-ingest/mappings/{database_id}",
        "/api/v1/rest-records/",
        "/api/v1/rest-records/annual-summary/{year}",
        "/api/v1/rest-records/annual-summary/{year}/table",
        "/docs",
        "/redoc",
    }
    assert not any(
        path.startswith(("/api/v1/gtd-tasks", "/api/v1/telegram", "/api/v1/video-process"))
        for path in paths
    )
    assert "/downloads" not in paths
    assert "app.services.telegram" not in sys.modules
    assert set(disabled_app.openapi()["paths"]) == {
        "/",
        "/api/v1/notion-ingest/",
        "/api/v1/notion-ingest/mappings",
        "/api/v1/notion-ingest/mappings/{database_id}",
        "/api/v1/rest-records/",
        "/api/v1/rest-records/annual-summary/{year}",
        "/api/v1/rest-records/annual-summary/{year}/table",
    }


def test_public_request_dump_is_registered_only_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_PUBLIC_REQUEST_DUMP", True)

    enabled_app = create_app()

    assert "/api/v1/public-request-dump/" in {route.path for route in enabled_app.routes}
    assert "/api/v1/public-request-dump/" in enabled_app.openapi()["paths"]


def test_disabled_router_rejects_calls() -> None:
    disabled_router = create_disabled_router("测试功能")

    @disabled_router.get("/")
    async def unreachable() -> dict[str, bool]:
        return {"called": True}

    test_app = FastAPI()
    test_app.include_router(disabled_router, prefix="/disabled")

    response = TestClient(test_app).get("/disabled/")

    assert response.status_code == 410
    assert response.json() == {"detail": "测试功能已废弃并禁止调用"}
