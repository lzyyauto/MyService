import os
import time
from collections.abc import Iterator

import psycopg2
import pytest
import requests


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("FUNCTIONAL_TEST_BASE_URL", "http://127.0.0.1:18080")


@pytest.fixture(scope="session")
def api_key() -> str:
    return "functional-test-api-key"


@pytest.fixture(scope="session")
def prepared_backend(base_url: str, api_key: str) -> Iterator[None]:
    deadline = time.monotonic() + 60
    while True:
        try:
            response = requests.get(f"{base_url}/", timeout=2)
            response.raise_for_status()
            break
        except requests.RequestException:
            if time.monotonic() >= deadline:
                pytest.fail("功能测试服务在 60 秒内未就绪")
            time.sleep(1)

    db_port = int(os.environ.get("FUNCTIONAL_TEST_DB_PORT", "15432"))
    while True:
        try:
            connection = psycopg2.connect(
                host="127.0.0.1",
                port=db_port,
                user="functional",
                password="functional",
                dbname="functional",
            )
            break
        except psycopg2.OperationalError:
            if time.monotonic() >= deadline:
                pytest.fail("功能测试数据库在 60 秒内未就绪")
            time.sleep(1)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (id, api_key, created_at, updated_at)
                VALUES ('functional-user', %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET api_key = EXCLUDED.api_key
                """,
                (api_key,),
            )
    connection.close()
    yield


@pytest.fixture(scope="session")
def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}
