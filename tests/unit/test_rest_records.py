from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import rest_records
from app.schemas.rest_record import RestRecordCreate


def query_returning(records):
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = records
    return query


@pytest.mark.asyncio
async def test_create_first_record_defaults_to_sleep(monkeypatch) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    schedule = MagicMock()
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", schedule)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(city="上海"),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.user_id == "user-1"
    assert record.rest_type == 0
    assert record.city == "上海"
    assert record.month_str.endswith("月")
    db.add.assert_called_once_with(record)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(record)
    schedule.assert_called_once_with(record, 0)


@pytest.mark.asyncio
async def test_create_automatically_toggles_last_type(monkeypatch) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(rest_type=0)
    )
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", MagicMock())

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 1


def test_schedule_sync_skips_when_notion_is_not_configured(monkeypatch) -> None:
    from app.core.config import settings

    create_task = MagicMock()
    monkeypatch.setattr(rest_records.asyncio, "create_task", create_task)
    monkeypatch.setattr(settings, "NOTION_TOKEN", None)
    monkeypatch.setattr(settings, "NOTION_SLEEP_DATABASE_ID", None)

    rest_records.schedule_rest_record_sync(SimpleNamespace(), 0)

    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_notion_sync_succeeds_without_retry(monkeypatch) -> None:
    from app.core.config import settings
    from app.services import notion

    add_rest_record = AsyncMock(return_value="page-id")
    monkeypatch.setattr(
        notion,
        "NotionService",
        lambda token: SimpleNamespace(add_rest_record=add_rest_record),
    )
    monkeypatch.setattr(settings, "NOTION_TOKEN", "token")
    monkeypatch.setattr(settings, "NOTION_SLEEP_DATABASE_ID", "sleep-db")

    record = SimpleNamespace(id="record-1")
    await rest_records.sync_rest_record_to_notion(record, 0)

    add_rest_record.assert_awaited_once_with(
        database_id="sleep-db",
        record=record,
    )


@pytest.mark.asyncio
async def test_notion_sync_retries_then_sends_bark(monkeypatch) -> None:
    from app.core.config import settings
    from app.services import bark, notion

    add_rest_record = AsyncMock(return_value=None)
    send_notification = AsyncMock(return_value=True)
    monkeypatch.setattr(
        notion,
        "NotionService",
        lambda token: SimpleNamespace(add_rest_record=add_rest_record),
    )
    monkeypatch.setattr(
        bark,
        "BarkService",
        lambda **kwargs: SimpleNamespace(send_notification=send_notification),
    )
    monkeypatch.setattr(rest_records.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(settings, "NOTION_TOKEN", "token")
    monkeypatch.setattr(settings, "NOTION_WAKE_DATABASE_ID", "wake-db")
    monkeypatch.setattr(settings, "BARK_DEFAULT_DEVICE_KEY", "device")

    await rest_records.sync_rest_record_to_notion(SimpleNamespace(id="record-1"), 1)

    assert add_rest_record.await_count == 3
    assert rest_records.asyncio.sleep.await_count == 2
    send_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_annual_table_pairs_sleep_and_wake() -> None:
    sleep = SimpleNamespace(
        rest_type=0,
        rest_time=1_704_207_600,
        city="上海",
        wifi_name="Home",
    )
    wake = SimpleNamespace(
        rest_type=1,
        rest_time=1_704_236_400,
        city=None,
        wifi_name=None,
    )
    db = MagicMock()
    db.query.return_value = query_returning([sleep, wake])

    result = await rest_records.get_annual_summary_table(
        year=2024,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["count"] == 1
    assert result["records"][0]["duration"] == 8.0
    assert result["records"][0]["city"] == "上海"


@pytest.mark.asyncio
async def test_annual_summary_reports_core_metrics() -> None:
    sleep = SimpleNamespace(
        rest_type=0,
        rest_time=1_704_207_600,
        city="上海",
        wifi_name="Home",
    )
    wake = SimpleNamespace(
        rest_type=1,
        rest_time=1_704_236_400,
        city="上海",
        wifi_name="Home",
    )
    db = MagicMock()
    db.query.return_value = query_returning([sleep, wake])

    result = await rest_records.get_annual_summary(
        year=2024,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["overview"]["year"] == "2024"
    assert result["overview"]["total_days_logged"] == 1
    assert result["overview"]["avg_duration_hrs"] == 8.0
    assert result["monthly_trends"][0]["record_count"] == 1
