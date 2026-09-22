from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import rest_records
from app.schemas.rest_record import RestRecordCreate
from app.services.rest_sessions import CN_TIMEZONE


def query_returning(records):
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = records
    return query


@pytest.mark.asyncio
async def test_create_first_record_defaults_to_sleep(monkeypatch) -> None:
    now = datetime(2026, 9, 20, 23, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    schedule = MagicMock()
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", schedule)
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

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
async def test_create_first_record_uses_wake_type_outside_sleep_window(monkeypatch) -> None:
    now = datetime(2026, 9, 21, 7, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", MagicMock())
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 1


@pytest.mark.asyncio
async def test_create_automatically_toggles_last_type(monkeypatch) -> None:
    now = datetime(2026, 9, 21, 7, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(rest_type=0, rest_time=int((now - timedelta(hours=8)).timestamp()))
    )
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", MagicMock())
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 1


@pytest.mark.asyncio
async def test_create_reanchors_to_sleep_after_long_gap_in_sleep_window(monkeypatch) -> None:
    now = datetime(2026, 9, 21, 23, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(rest_type=0, rest_time=int((now - timedelta(hours=24)).timestamp()))
    )
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", MagicMock())
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 0


@pytest.mark.asyncio
async def test_create_reanchors_to_wake_after_long_gap_outside_sleep_window(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(rest_type=1, rest_time=int((now - timedelta(hours=24)).timestamp()))
    )
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", MagicMock())
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 1


@pytest.mark.asyncio
async def test_create_rejects_rapid_automatic_duplicate(monkeypatch) -> None:
    now = datetime(2026, 9, 21, 23, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(rest_type=0, rest_time=int((now - timedelta(seconds=119)).timestamp()))
    )
    schedule = MagicMock()
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", schedule)
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    with pytest.raises(rest_records.HTTPException) as error:
        await rest_records.create_rest_record(
            db=db,
            rest_record_in=RestRecordCreate(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert error.value.status_code == 409
    db.add.assert_not_called()
    schedule.assert_not_called()


@pytest.mark.asyncio
async def test_create_honors_explicit_type_during_duplicate_guard_window(monkeypatch) -> None:
    now = datetime(2026, 9, 21, 23, 0, tzinfo=CN_TIMEZONE)
    db = MagicMock()
    schedule = MagicMock()
    monkeypatch.setattr(rest_records, "schedule_rest_record_sync", schedule)
    monkeypatch.setattr(rest_records, "_current_cn_time", lambda: now)

    record = await rest_records.create_rest_record(
        db=db,
        rest_record_in=RestRecordCreate(rest_type=1),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert record.rest_type == 1
    db.query.assert_not_called()
    schedule.assert_called_once_with(record, 1)


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


@pytest.mark.asyncio
async def test_annual_summary_excludes_single_sided_events_from_metrics() -> None:
    sleep = SimpleNamespace(rest_type=0, rest_time=1_704_207_600, city="上海", wifi_name="Home")
    wake = SimpleNamespace(rest_type=1, rest_time=1_704_236_400, city="上海", wifi_name="Home")
    orphan_wake = SimpleNamespace(rest_type=1, rest_time=1_704_322_800, city="北京", wifi_name="Elsewhere")
    db = MagicMock()
    db.query.return_value = query_returning([sleep, wake, orphan_wake])

    result = await rest_records.get_annual_summary(
        year=2024,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result["overview"]["total_days_logged"] == 1
    assert result["overview"]["avg_duration_hrs"] == 8.0
    assert result["overview"]["distinct_cities_count"] == 1
