import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deprecation import create_disabled_router
from app.main import app


def test_only_active_http_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert paths == {
        "/",
        "/api/v1/openapi.json",
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
    assert set(app.openapi()["paths"]) == {
        "/",
        "/api/v1/rest-records/",
        "/api/v1/rest-records/annual-summary/{year}",
        "/api/v1/rest-records/annual-summary/{year}/table",
    }


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
