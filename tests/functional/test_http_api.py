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
