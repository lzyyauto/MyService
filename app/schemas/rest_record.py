from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, conint, validator


def to_cn_timezone(timestamp: int) -> datetime:
    """将时间戳转换为北京时间"""
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    cn_time = utc_time.astimezone(timezone(timedelta(hours=8)))
    return cn_time


class RestRecordBase(BaseModel):
    rest_type: Optional[int] = Field(None,
                           ge=0,
                           le=1,
                           description="休息类型：0-睡眠，1-起床",
                           example=0,
                           title="休息类型")
    wifi_name: Optional[str] = Field(None,
                                     description="当前连接的 WiFi 名称",
                                     example="Home_WiFi",
                                     title="WiFi名称")
    latitude: Optional[float] = Field(None,
                                      description="当前位置纬度",
                                      example=39.9042,
                                      title="纬度")
    longitude: Optional[float] = Field(None,
                                       description="当前位置经度",
                                       example=116.4074,
                                       title="经度")
    city: Optional[str] = Field(None,
                                description="所在城市",
                                example="北京",
                                title="城市")


class RestRecordCreate(RestRecordBase):
    pass


class RestRecordInDB(RestRecordBase):
    id: UUID = Field(..., description="记录ID")
    user_id: str = Field(..., description="用户ID")
    rest_time: int = Field(..., description="休息时间戳")
    month_str: str = Field(..., description="月份字符串，格式：MM月")
    created_at: int = Field(..., description="创建时间戳")
    updated_at: int = Field(..., description="更新时间戳")

    @validator('rest_time', 'created_at', 'updated_at', pre=True)
    def convert_timestamp_to_datetime(cls, v):
        if isinstance(v, datetime):
            return int(v.timestamp())
        return v

    class Config:
        from_attributes = True


class RestRecord(RestRecordInDB):
    rest_time: datetime = Field(..., description="休息时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @validator('rest_time', 'created_at', 'updated_at', pre=True)
    def convert_timestamp_to_datetime(cls, v):
        if isinstance(v, int):
            return to_cn_timezone(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.strftime('%Y-%m-%d %H:%M:%S')}


class AnnualOverview(BaseModel):
    year: str
    total_days_logged: int
    distinct_cities_count: int
    distinct_wake_cities_count: int
    avg_sleep_time: str  # 格式 HH:MM
    avg_wake_time: str   # 格式 HH:MM
    avg_duration_hrs: float


class AnnualExtreme(BaseModel):
    date: str
    value: str
    description: str


class AnnualExtremes(BaseModel):
    latest_sleep: AnnualExtreme
    earliest_wake: AnnualExtreme
    longest_sleep: AnnualExtreme
    shortest_sleep: AnnualExtreme


class ConsistencyStats(BaseModel):
    max_streak: int
    consistency_score: int  # 0-100
    remark: str


class SpatialStat(BaseModel):
    name: str
    count: int
    type: str  # 'city' or 'wifi'


class MonthlyStat(BaseModel):
    month: str
    avg_duration: float
    record_count: int


class DataIntegrity(BaseModel):
    missing_sleep_dates: list[str]
    missing_wake_dates: list[str]
    total_missing_count: int


class AnnualSummaryResponse(BaseModel):
    overview: AnnualOverview
    extremes: AnnualExtremes
    consistency: ConsistencyStats
    spatial: list[SpatialStat]
    monthly_trends: list[MonthlyStat]
    data_integrity: DataIntegrity
    persona_tags: list[str]
    summary_text: str


class AnnualSummaryTableRecord(BaseModel):
    date: str
    sleep_time: Optional[str] = None
    wake_time: Optional[str] = None
    duration: Optional[float] = None
    city: Optional[str] = None
    wifi: Optional[str] = None


class AnnualSummaryTableResponse(BaseModel):
    year: str
    count: int
    records: list[AnnualSummaryTableRecord]
