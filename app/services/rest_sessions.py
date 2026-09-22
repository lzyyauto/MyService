"""把独立休息事件投影为可查询的睡眠会话。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from app.models.rest_record import RestRecord


CN_TIMEZONE = timezone(timedelta(hours=8))
MAX_SESSION_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class SleepSession:
    """一个配对完成或缺少一侧的睡眠会话。"""

    sleep: RestRecord | None
    wake: RestRecord | None

    @property
    def anchor_id(self):
        return (self.sleep or self.wake).id

    @property
    def sleep_date(self) -> date:
        """会话的统计日：完整会话按起床当天归属。

        单侧错误事件没有起床端点时，只能按现存原始事件的本地日期展示，
        并且不会参与统计。
        """
        reference = self.wake or self.sleep
        return datetime.fromtimestamp(reference.rest_time, tz=CN_TIMEZONE).date()

    @property
    def duration_hours(self) -> float | None:
        if self.sleep is None or self.wake is None:
            return None
        duration = self.wake.rest_time - self.sleep.rest_time
        if not 0 < duration < MAX_SESSION_SECONDS:
            return None
        return duration / 3600

    @property
    def error_code(self) -> str | None:
        """返回该原始事件组不应参与统计的原因。"""
        if self.sleep is None:
            return "missing_sleep"
        if self.wake is None:
            return "missing_wake"
        if self.duration_hours is None:
            return "invalid_duration"
        return None

    @property
    def is_complete(self) -> bool:
        return self.error_code is None


def pair_rest_events(records: Iterable[RestRecord]) -> list[SleepSession]:
    """按时间配对事件；重复入睡会让较早的一条成为不完整会话。"""

    sessions: list[SleepSession] = []
    pending_sleep: RestRecord | None = None

    for record in sorted(records, key=lambda item: item.rest_time):
        if record.rest_type == RestRecord.REST_TYPE_SLEEP:
            if pending_sleep is not None:
                sessions.append(SleepSession(sleep=pending_sleep, wake=None))
            pending_sleep = record
            continue

        if pending_sleep is None:
            sessions.append(SleepSession(sleep=None, wake=record))
            continue

        duration = record.rest_time - pending_sleep.rest_time
        if 0 < duration < MAX_SESSION_SECONDS:
            sessions.append(SleepSession(sleep=pending_sleep, wake=record))
            pending_sleep = None
            continue

        sessions.append(SleepSession(sleep=pending_sleep, wake=None))
        pending_sleep = None
        sessions.append(SleepSession(sleep=None, wake=record))

    if pending_sleep is not None:
        sessions.append(SleepSession(sleep=pending_sleep, wake=None))

    return sessions


def local_datetime(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=CN_TIMEZONE)


def session_payload(session: SleepSession) -> dict:
    sleep_at = local_datetime(session.sleep.rest_time) if session.sleep else None
    wake_at = local_datetime(session.wake.rest_time) if session.wake else None
    duration = session.duration_hours
    city = getattr(session.wake, "city", None) or getattr(session.sleep, "city", None)
    wifi_name = getattr(session.wake, "wifi_name", None) or getattr(
        session.sleep, "wifi_name", None
    )
    return {
        "anchor_record_id": session.anchor_id,
        "sleep_record_id": session.sleep.id if session.sleep else None,
        "wake_record_id": session.wake.id if session.wake else None,
        "sleep_date": session.sleep_date,
        "sleep_at": sleep_at,
        "wake_at": wake_at,
        "duration_hours": round(duration, 2) if duration is not None else None,
        "is_complete": session.is_complete,
        "error_code": session.error_code,
        "city": city,
        "wifi_name": wifi_name,
    }
