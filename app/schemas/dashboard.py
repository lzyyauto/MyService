"""睡眠和运动看板的对外数据结构。"""

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Pagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class SleepSessionItem(BaseModel):
    anchor_record_id: UUID
    sleep_record_id: Optional[UUID] = None
    wake_record_id: Optional[UUID] = None
    sleep_date: date
    sleep_at: Optional[datetime] = None
    wake_at: Optional[datetime] = None
    duration_hours: Optional[float] = None
    is_complete: bool
    error_code: Optional[Literal["missing_sleep", "missing_wake", "invalid_duration"]] = None
    city: Optional[str] = None
    wifi_name: Optional[str] = None


class SleepHeatDay(BaseModel):
    date: date
    duration_hours: Optional[float] = None
    session_count: int
    complete_count: int
    error_count: int
    is_longest_session: bool = False
    is_earliest_sleep: bool = False
    is_earliest_wake: bool = False


class SleepDurationHighlight(BaseModel):
    date: date
    duration_hours: float


class SleepClockHighlight(BaseModel):
    date: date
    time: str


class WakeCityRank(BaseModel):
    city: str
    count: int


class SleepSummary(BaseModel):
    total_sessions: int
    complete_sessions: int
    incomplete_sessions: int
    average_duration_hours: Optional[float] = None
    longest_duration_hours: Optional[float] = None
    shortest_duration_hours: Optional[float] = None
    average_sleep_time: Optional[str] = None
    average_wake_time: Optional[str] = None
    longest_session: Optional[SleepDurationHighlight] = None
    earliest_sleep: Optional[SleepClockHighlight] = None
    earliest_wake: Optional[SleepClockHighlight] = None
    wake_city_ranking: list[WakeCityRank] = Field(default_factory=list)


class SleepDashboardResponse(BaseModel):
    scope: Literal["month", "year", "all"]
    period: Optional[str] = None
    summary: SleepSummary
    heatmap: list[SleepHeatDay]
    records: list[SleepSessionItem]
    pagination: Pagination


class DeleteSleepSessionResponse(BaseModel):
    deleted_record_ids: list[UUID]
    deleted_count: int
    notion_copy_retained: bool = True


class SportRecordItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sport_type: str
    duration_minutes: float
    occurred_at: datetime
    occurred_on: date
    city: Optional[str] = None
    is_marker: bool
    is_thirty_minute_marker: bool


class SportTypeSummary(BaseModel):
    sport_type: str
    count: int
    total_duration_minutes: float


class SportSummary(BaseModel):
    total_records: int
    total_duration_minutes: float
    average_duration_minutes: Optional[float] = None
    active_days: int
    marker_count: int
    thirty_minute_marker_count: int
    by_type: list[SportTypeSummary]


class SportHeatDay(BaseModel):
    date: date
    total_duration_minutes: float
    record_count: int
    marker_count: int
    thirty_minute_marker_count: int


class SportDashboardResponse(BaseModel):
    scope: Literal["month", "year", "all"]
    period: Optional[str] = None
    summary: SportSummary
    heatmap: list[SportHeatDay]
    records: list[SportRecordItem]
    pagination: Pagination
