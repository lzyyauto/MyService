from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
import requests

pytestmark = pytest.mark.functional


def test_root_and_openapi_expose_only_active_http_features(
    base_url: str,
    prepared_backend: None,
) -> None:
    root = requests.get(f"{base_url}/", timeout=5)
    assert root.status_code == 200
    assert root.json()["message"] == "欢迎使用 Z 收集系统 API"

    schema = requests.get(f"{base_url}/api/v1/openapi.json", timeout=5).json()
    paths = set(schema["paths"])
    assert paths == {
        "/",
        "/api/v1/notion-ingest/",
        "/api/v1/notion-ingest/mappings",
        "/api/v1/notion-ingest/mappings/{database_id}",
        "/api/v1/rest-records/",
        "/api/v1/rest-records/annual-summary/{year}",
        "/api/v1/rest-records/annual-summary/{year}/table",
    }


def test_authentication_and_input_boundaries(
    base_url: str,
    auth_headers: dict[str, str],
    prepared_backend: None,
) -> None:
    assert requests.get(f"{base_url}/api/v1/rest-records/", timeout=5).status_code == 401
    assert requests.post(f"{base_url}/api/v1/notion-ingest/", timeout=5).status_code == 401
    assert requests.get(
        f"{base_url}/api/v1/rest-records/",
        headers={"Authorization": "Bearer invalid"},
        timeout=5,
    ).status_code == 401
    assert requests.post(
        f"{base_url}/api/v1/rest-records/",
        headers=auth_headers,
        json={"rest_type": 2},
        timeout=5,
    ).status_code == 422
    assert requests.get(
        f"{base_url}/api/v1/rest-records/?skip=-1",
        headers=auth_headers,
        timeout=5,
    ).status_code == 422
    assert requests.get(
        f"{base_url}/api/v1/rest-records/annual-summary/1900",
        headers=auth_headers,
        timeout=5,
    ).status_code == 422


def test_sleep_record_full_http_flow(
    base_url: str,
    auth_headers: dict[str, str],
    prepared_backend: None,
) -> None:
    sleep = requests.post(
        f"{base_url}/api/v1/rest-records/",
        headers=auth_headers,
        json={
            "rest_type": 0,
            "city": "上海",
            "wifi_name": "Functional-WiFi",
            "latitude": 31.2304,
            "longitude": 121.4737,
        },
        timeout=5,
    )
    assert sleep.status_code == 201, sleep.text

    wake = requests.post(
        f"{base_url}/api/v1/rest-records/",
        headers=auth_headers,
        json={"city": "上海"},
        timeout=5,
    )
    assert wake.status_code == 201, wake.text
    assert wake.json()["rest_type"] == 1

    year = datetime.now().year
    china_tz = timezone(timedelta(hours=8))
    sleep_at = int(datetime(year, 1, 2, 23, 0, tzinfo=china_tz).timestamp())
    wake_at = int(datetime(year, 1, 3, 7, 0, tzinfo=china_tz).timestamp())
    connection = psycopg2.connect(
        host="127.0.0.1",
        port=int(__import__("os").environ.get("FUNCTIONAL_TEST_DB_PORT", "15432")),
        user="functional",
        password="functional",
        dbname="functional",
    )
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE rest_records SET rest_time = %s, month_str = '01月' WHERE id = %s",
                (sleep_at, sleep.json()["id"]),
            )
            cursor.execute(
                "UPDATE rest_records SET rest_time = %s, month_str = '01月' WHERE id = %s",
                (wake_at, wake.json()["id"]),
            )
    connection.close()

    records = requests.get(
        f"{base_url}/api/v1/rest-records/?limit=1",
        headers=auth_headers,
        timeout=5,
    )
    assert records.status_code == 200
    assert len(records.json()) == 1
    assert records.json()[0]["rest_type"] == 1

    table = requests.get(
        f"{base_url}/api/v1/rest-records/annual-summary/{year}/table",
        headers=auth_headers,
        timeout=5,
    )
    assert table.status_code == 200, table.text
    assert table.json()["count"] == 1
    assert table.json()["records"][0]["duration"] == 8.0

    summary = requests.get(
        f"{base_url}/api/v1/rest-records/annual-summary/{year}",
        headers=auth_headers,
        timeout=5,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["overview"]["avg_duration_hrs"] == 8.0


def test_notion_ingest_maps_exercise_and_keeps_unmapped_events(
    base_url: str,
    auth_headers: dict[str, str],
    prepared_backend: None,
) -> None:
    database_id = "exercise-database-id"
    mapping = requests.put(
        f"{base_url}/api/v1/notion-ingest/mappings/{database_id}",
        headers=auth_headers,
        json={
            "business_type": "exercise",
            "display_name": "日常运动记录",
            "description": "来自 iOS 快捷指令；时长单位为小时。",
        },
        timeout=5,
    )
    assert mapping.status_code == 200, mapping.text

    connection = psycopg2.connect(
        host="127.0.0.1",
        port=int(__import__("os").environ.get("FUNCTIONAL_TEST_DB_PORT", "15432")),
        user="functional",
        password="functional",
        dbname="functional",
    )
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO notion_select_option_mappings (option_id, name) VALUES (%s, %s)",
                ("exercise-option-running", "跑步"),
            )
    connection.close()

    payload = {
        "parent": {"type": "database_id", "database_id": database_id},
        "properties": {
            "运动类型": {
                "type": "select",
                "select": {
                    "id": "exercise-option-running",
                    "name": "exercise-option-running",
                    "color": "blue",
                },
            },
            "月份": {
                "type": "title",
                "title": [{"type": "text", "text": {"content": "09月"}}],
            },
            "城市": {
                "type": "rich_text",
                "rich_text": [{"type": "text", "text": {"content": "上海市"}}],
            },
            "时长": {"type": "number", "number": 1},
            "记录时间": {
                "type": "date",
                "date": {"start": "2026-09-02T16:01:35+08:00"},
            },
            "日期": {"type": "date", "date": {"start": "2026-09-02"}},
        },
        "idempotency_key": "exercise-event-1",
    }
    accepted = requests.post(
        f"{base_url}/api/v1/notion-ingest/",
        headers=auth_headers,
        json=payload,
        timeout=5,
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["business_type"] == "exercise"
    assert accepted.json()["mapping_name"] == "日常运动记录"
    assert accepted.json()["delivery_status"] == "pending"

    duplicate = requests.post(
        f"{base_url}/api/v1/notion-ingest/",
        headers=auth_headers,
        json=payload,
        timeout=5,
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["event_id"] == accepted.json()["event_id"]

    invalid = {**payload, "idempotency_key": "exercise-event-invalid"}
    invalid["properties"] = {**payload["properties"], "时长": {"type": "number", "number": -1}}
    rejected = requests.post(
        f"{base_url}/api/v1/notion-ingest/",
        headers=auth_headers,
        json=invalid,
        timeout=5,
    )
    assert rejected.status_code == 422

    unmapped = requests.post(
        f"{base_url}/api/v1/notion-ingest/",
        headers=auth_headers,
        json={
            "parent": {"type": "database_id", "database_id": "unmapped-database-id"},
            "properties": {"名称": {"type": "title", "title": []}},
            "idempotency_key": "unmapped-event-1",
        },
        timeout=5,
    )
    assert unmapped.status_code == 202, unmapped.text
    assert unmapped.json()["business_type"] is None

    connection = psycopg2.connect(
        host="127.0.0.1",
        port=int(__import__("os").environ.get("FUNCTIONAL_TEST_DB_PORT", "15432")),
        user="functional",
        password="functional",
        dbname="functional",
    )
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT sport_type FROM sport_record")
            assert cursor.fetchone()[0] == "跑步"
            cursor.execute("SELECT count(*) FROM notion_ingest_events")
            assert cursor.fetchone()[0] == 2
            cursor.execute("SELECT count(*) FROM notion_deliveries WHERE status = 'pending'")
            assert cursor.fetchone()[0] == 2
    connection.close()


def test_deprecated_routes_are_unreachable(
    base_url: str,
    prepared_backend: None,
) -> None:
    for path in (
        "/api/v1/gtd-tasks/",
        "/api/v1/telegram/",
        "/api/v1/video-process/",
        "/downloads/example",
    ):
        assert requests.get(f"{base_url}{path}", timeout=5).status_code == 404
