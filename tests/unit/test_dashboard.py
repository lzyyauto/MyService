from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import rest_records, sport_records
from app.services.rest_sessions import pair_rest_events


def timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


def rest_event(rest_type: int, value: str):
    return SimpleNamespace(
        id=uuid4(),
        rest_type=rest_type,
        rest_time=timestamp(value),
        city="上海",
        wifi_name="Home",
    )


def dashboard_query(records):
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = records
    return query


def test_sleep_date_uses_wake_day_for_before_and_after_midnight() -> None:
    before_midnight = pair_rest_events([
        rest_event(0, "2026-01-01T23:00:00+08:00"),
        rest_event(1, "2026-01-02T10:00:00+08:00"),
    ])[0]
    after_midnight = pair_rest_events([
        rest_event(0, "2026-01-02T01:30:00+08:00"),
        rest_event(1, "2026-01-02T11:30:00+08:00"),
    ])[0]

    assert before_midnight.sleep_date == date(2026, 1, 2)
    assert before_midnight.duration_hours == 11
    assert after_midnight.sleep_date == date(2026, 1, 2)
    assert after_midnight.duration_hours == 10


def test_pairing_keeps_repeated_sleep_as_incomplete() -> None:
    first = rest_event(0, "2026-01-01T22:00:00+08:00")
    second = rest_event(0, "2026-01-01T23:00:00+08:00")
    wake = rest_event(1, "2026-01-02T07:00:00+08:00")

    sessions = pair_rest_events([first, second, wake])

    assert len(sessions) == 2
    assert not sessions[0].is_complete
    assert sessions[1].duration_hours == 8


def test_pairing_marks_missing_counterpart_as_an_error() -> None:
    orphan_wake = rest_event(1, "2026-01-02T08:00:00+08:00")
    orphan_sleep = rest_event(0, "2026-01-02T23:00:00+08:00")

    sessions = pair_rest_events([orphan_wake, orphan_sleep])

    assert [session.error_code for session in sessions] == [
        "missing_sleep",
        "missing_wake",
    ]
    assert all(not session.is_complete for session in sessions)


@pytest.mark.asyncio
async def test_sleep_dashboard_defaults_to_selected_month() -> None:
    sleep = rest_event(0, "2026-09-01T23:00:00+08:00")
    wake = rest_event(1, "2026-09-02T07:00:00+08:00")
    outside = rest_event(0, "2026-08-20T23:00:00+08:00")
    db = MagicMock()
    db.query.return_value = dashboard_query([sleep, wake, outside])

    result = await rest_records.get_sleep_sessions(
        scope="month",
        period="2026-09",
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.total_sessions == 1
    assert result.summary.average_duration_hours == 8
    assert result.records[0].sleep_date == date(2026, 9, 2)


@pytest.mark.asyncio
async def test_sleep_dashboard_returns_highlights_and_wake_city_ranking() -> None:
    first_sleep = rest_event(0, "2026-09-01T23:00:00+08:00")
    first_wake = rest_event(1, "2026-09-02T08:00:00+08:00")
    first_wake.city = "上海"
    second_sleep = rest_event(0, "2026-09-02T22:00:00+08:00")
    second_wake = rest_event(1, "2026-09-03T06:00:00+08:00")
    second_wake.city = "北京"
    db = MagicMock()
    db.query.return_value = dashboard_query(
        [first_sleep, first_wake, second_sleep, second_wake]
    )

    result = await rest_records.get_sleep_sessions(
        scope="month",
        period="2026-09",
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.longest_session.date == date(2026, 9, 2)
    assert result.summary.longest_session.duration_hours == 9
    assert result.summary.earliest_sleep.date == date(2026, 9, 3)
    assert result.summary.earliest_sleep.time == "22:00"
    assert result.summary.earliest_wake.date == date(2026, 9, 3)
    assert result.summary.earliest_wake.time == "06:00"
    assert {(item.city, item.count) for item in result.summary.wake_city_ranking} == {
        ("上海", 1),
        ("北京", 1),
    }
    heatmap = {item.date: item for item in result.heatmap}
    assert heatmap[date(2026, 9, 2)].is_longest_session
    assert heatmap[date(2026, 9, 3)].is_earliest_sleep
    assert heatmap[date(2026, 9, 3)].is_earliest_wake


@pytest.mark.asyncio
async def test_sleep_dashboard_excludes_errors_from_statistics_but_returns_them() -> None:
    sleep = rest_event(0, "2026-09-01T23:00:00+08:00")
    wake = rest_event(1, "2026-09-02T07:00:00+08:00")
    orphan_wake = rest_event(1, "2026-09-03T08:00:00+08:00")
    orphan_sleep = rest_event(0, "2026-09-04T23:00:00+08:00")
    db = MagicMock()
    db.query.return_value = dashboard_query([sleep, wake, orphan_wake, orphan_sleep])

    result = await rest_records.get_sleep_sessions(
        scope="month",
        period="2026-09",
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.total_sessions == 1
    assert result.summary.complete_sessions == 1
    assert result.summary.incomplete_sessions == 2
    assert result.summary.average_duration_hours == 8
    assert result.summary.average_sleep_time == "23:00"
    assert result.summary.average_wake_time == "07:00"
    assert result.pagination.total_items == 3
    assert {record.error_code for record in result.records} == {
        None,
        "missing_sleep",
        "missing_wake",
    }
    assert sum(item.error_count for item in result.heatmap) == 2


@pytest.mark.asyncio
async def test_all_sleep_history_limits_only_heatmap_to_recent_three_years() -> None:
    today = datetime.now(tz=rest_records.CN_TIMEZONE).date()
    heatmap_start = rest_records._recent_history_start(today)
    old_sleep_day = heatmap_start - timedelta(days=2)
    old_sleep = rest_event(0, f"{old_sleep_day}T22:00:00+08:00")
    old_wake = rest_event(1, f"{old_sleep_day + timedelta(days=1)}T06:00:00+08:00")
    recent_sleep = rest_event(0, f"{today - timedelta(days=1)}T23:00:00+08:00")
    recent_wake = rest_event(1, f"{today}T07:00:00+08:00")
    db = MagicMock()
    db.query.return_value = dashboard_query([old_sleep, old_wake, recent_sleep, recent_wake])

    result = await rest_records.get_sleep_sessions(
        scope="all",
        period=None,
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.total_sessions == 2
    assert result.pagination.total_items == 2
    assert [item.date for item in result.heatmap] == [today]


@pytest.mark.asyncio
async def test_delete_sleep_session_removes_both_paired_events() -> None:
    sleep = rest_event(0, "2026-09-01T23:00:00+08:00")
    wake = rest_event(1, "2026-09-02T07:00:00+08:00")
    db = MagicMock()
    db.query.return_value = dashboard_query([sleep, wake])

    result = await rest_records.delete_sleep_session(
        anchor_record_id=sleep.id,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.deleted_count == 2
    assert result.notion_copy_retained
    assert db.delete.call_count == 2
    db.commit.assert_called_once()


def sport_record(*, sport_type: str, duration: float, day: date):
    return SimpleNamespace(
        id=uuid4(),
        sport_type=sport_type,
        duration=duration,
        occurred_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
        occurred_on=day,
        city="上海",
    )


def test_sport_marker_uses_minutes_directly() -> None:
    assert sport_records.is_sport_marker(
        sport_record(sport_type="其他", duration=2, day=date(2026, 9, 1))
    )
    assert not sport_records.is_sport_marker(
        sport_record(sport_type="其他", duration=2 / 60, day=date(2026, 9, 1))
    )
    assert sport_records.is_thirty_minute_marker(
        sport_record(sport_type="其他", duration=30, day=date(2026, 9, 1))
    )
    assert not sport_records.is_thirty_minute_marker(
        sport_record(sport_type="跑步", duration=30, day=date(2026, 9, 1))
    )


@pytest.mark.asyncio
async def test_all_sport_history_limits_only_heatmap_to_recent_three_years() -> None:
    today = datetime.now(tz=sport_records.CN_TIMEZONE).date()
    old_day = sport_records._recent_history_start(today) - timedelta(days=1)
    records = [
        sport_record(sport_type="跑步", duration=30, day=old_day),
        sport_record(sport_type="游泳", duration=45, day=today),
    ]
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = records
    db.query.return_value = query

    result = await sport_records.get_sport_dashboard(
        scope="all",
        period=None,
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.total_records == 2
    assert result.summary.active_days == 2
    assert result.pagination.total_items == 2
    assert [item.date for item in result.heatmap] == [today]


@pytest.mark.asyncio
async def test_sport_dashboard_counts_markers() -> None:
    records = [
        sport_record(sport_type="其他", duration=2, day=date(2026, 9, 1)),
        sport_record(sport_type="其他", duration=30, day=date(2026, 9, 1)),
        sport_record(sport_type="跑步", duration=30, day=date(2026, 9, 2)),
    ]
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = records
    db.query.return_value = query

    result = await sport_records.get_sport_dashboard(
        scope="month",
        period="2026-09",
        page=1,
        page_size=20,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.summary.total_duration_minutes == 62
    assert result.summary.marker_count == 1
    assert result.summary.thirty_minute_marker_count == 1
    assert result.records[0].is_marker
    assert result.records[1].is_thirty_minute_marker
    assert result.heatmap[0].marker_count == 1
    assert result.heatmap[0].thirty_minute_marker_count == 1
