"""运动看板查询接口。"""

import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.notion_ingest import SportRecord
from app.models.user import User
from app.schemas.dashboard import SportDashboardResponse


router = APIRouter()
CN_TIMEZONE = timezone(timedelta(hours=8))
HEATMAP_HISTORY_YEARS = 3
TWO_MINUTE_MARKER_DURATION = 2.0
THIRTY_MINUTE_MARKER_DURATION = 30.0


def is_sport_marker(record: SportRecord) -> bool:
    """判断“其他 2 分钟”的红色个人标记，保留既有接口字段语义。"""
    return record.sport_type == "其他" and math.isclose(
        float(record.duration), TWO_MINUTE_MARKER_DURATION, rel_tol=0, abs_tol=0.001
    )


def is_thirty_minute_marker(record: SportRecord) -> bool:
    """判断“其他 30 分钟”的独立特殊标记。"""
    return record.sport_type == "其他" and math.isclose(
        float(record.duration), THIRTY_MINUTE_MARKER_DURATION, rel_tol=0, abs_tol=0.001
    )


def _date_range(
    scope: Literal["month", "year", "all"], period: str | None
) -> tuple[date | None, date | None, str | None]:
    today = datetime.now(tz=CN_TIMEZONE).date()
    try:
        if scope == "month":
            selected = datetime.strptime(period or today.strftime("%Y-%m"), "%Y-%m").date()
            start = selected.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            return start, next_month - timedelta(days=1), start.strftime("%Y-%m")
        if scope == "year":
            selected_year = int(period or today.year)
            if selected_year < 1970 or selected_year > 2100:
                raise ValueError
            return date(selected_year, 1, 1), date(selected_year, 12, 31), str(selected_year)
    except (TypeError, ValueError) as error:
        expected = "YYYY-MM" if scope == "month" else "YYYY"
        raise HTTPException(status_code=422, detail=f"period 必须使用 {expected} 格式") from error
    return None, None, None


def _recent_history_start(today: date) -> date:
    """返回滚动“最近三年”热力图的起始日，兼容闰日。"""
    try:
        return today.replace(year=today.year - HEATMAP_HISTORY_YEARS)
    except ValueError:
        return today.replace(year=today.year - HEATMAP_HISTORY_YEARS, day=28)


@router.get(
    "/",
    response_model=SportDashboardResponse,
    summary="查询运动记录看板",
)
async def get_sport_dashboard(
    scope: Literal["month", "year", "all"] = Query("month"),
    period: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SportDashboardResponse:
    start, end, normalized_period = _date_range(scope, period)
    records = (
        db.query(SportRecord)
        .filter(SportRecord.user_id == current_user.id)
        .order_by(SportRecord.occurred_on.desc(), SportRecord.occurred_at.desc())
        .all()
    )
    if start is not None and end is not None:
        records = [item for item in records if start <= item.occurred_on <= end]

    heatmap_records = records
    if scope == "all":
        heatmap_start = _recent_history_start(datetime.now(tz=CN_TIMEZONE).date())
        heatmap_records = [
            item for item in records if item.occurred_on >= heatmap_start
        ]

    daily = defaultdict(
        lambda: {"duration": 0.0, "count": 0, "markers": 0, "thirty_minute_markers": 0}
    )
    heatmap_daily = defaultdict(
        lambda: {"duration": 0.0, "count": 0, "markers": 0, "thirty_minute_markers": 0}
    )
    types = defaultdict(lambda: {"duration": 0.0, "count": 0})
    marker_count = 0
    thirty_minute_marker_count = 0
    for record in records:
        marker = is_sport_marker(record)
        thirty_minute_marker = is_thirty_minute_marker(record)
        marker_count += int(marker)
        thirty_minute_marker_count += int(thirty_minute_marker)
        daily[record.occurred_on]["duration"] += float(record.duration)
        daily[record.occurred_on]["count"] += 1
        daily[record.occurred_on]["markers"] += int(marker)
        daily[record.occurred_on]["thirty_minute_markers"] += int(thirty_minute_marker)
        types[record.sport_type]["duration"] += float(record.duration)
        types[record.sport_type]["count"] += 1

    for record in heatmap_records:
        marker = is_sport_marker(record)
        thirty_minute_marker = is_thirty_minute_marker(record)
        heatmap_daily[record.occurred_on]["duration"] += float(record.duration)
        heatmap_daily[record.occurred_on]["count"] += 1
        heatmap_daily[record.occurred_on]["markers"] += int(marker)
        heatmap_daily[record.occurred_on]["thirty_minute_markers"] += int(thirty_minute_marker)

    total = len(records)
    total_duration = sum(float(item.duration) for item in records)
    offset = (page - 1) * page_size
    page_records = records[offset:offset + page_size]
    response = {
        "scope": scope,
        "period": normalized_period,
        "summary": {
            "total_records": total,
            "total_duration_minutes": round(total_duration, 2),
            "average_duration_minutes": round(total_duration / total, 2) if total else None,
            "active_days": len(daily),
            "marker_count": marker_count,
            "thirty_minute_marker_count": thirty_minute_marker_count,
            "by_type": [
                {
                    "sport_type": sport_type,
                    "count": values["count"],
                    "total_duration_minutes": round(values["duration"], 2),
                }
                for sport_type, values in sorted(
                    types.items(), key=lambda item: item[1]["duration"], reverse=True
                )
            ],
        },
        "heatmap": [
            {
                "date": day,
                "total_duration_minutes": round(values["duration"], 2),
                "record_count": values["count"],
                "marker_count": values["markers"],
                "thirty_minute_marker_count": values["thirty_minute_markers"],
            }
            for day, values in sorted(heatmap_daily.items())
        ],
        "records": [
            {
                "id": record.id,
                "sport_type": record.sport_type,
                "duration_minutes": round(float(record.duration), 2),
                "occurred_at": record.occurred_at,
                "occurred_on": record.occurred_on,
                "city": record.city,
                "is_marker": is_sport_marker(record),
                "is_thirty_minute_marker": is_thirty_minute_marker(record),
            }
            for record in page_records
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        },
    }
    return SportDashboardResponse.model_validate(response)
