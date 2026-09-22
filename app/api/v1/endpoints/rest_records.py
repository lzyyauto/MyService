import asyncio
import logging
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import List, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.rest_record import RestRecord as RestRecordModel
from app.models.user import User
from app.schemas.dashboard import (
    DeleteSleepSessionResponse,
    SleepDashboardResponse,
)
from app.schemas.rest_record import (AnnualSummaryResponse,
                                     AnnualSummaryTableResponse, RestRecord,
                                     RestRecordCreate, to_cn_timezone)
from app.services.rest_sessions import (
    CN_TIMEZONE,
    local_datetime,
    pair_rest_events,
    session_payload,
)

router = APIRouter()
logger = logging.getLogger(__name__)


AUTO_REANCHOR_SECONDS = 12 * 60 * 60
AUTO_DUPLICATE_GUARD_SECONDS = 2 * 60
SLEEP_WINDOW_START_HOUR = 21
SLEEP_WINDOW_END_HOUR = 5
HEATMAP_HISTORY_YEARS = 3


def _current_cn_time() -> datetime:
    """返回用于休息事件判定和落库的当前北京时间。"""
    return datetime.now(tz=CN_TIMEZONE)


def _is_sleep_window(current_time: datetime) -> bool:
    """21:00（含）至次日 05:00（不含）属于用户确认的入睡窗口。"""
    return (
        current_time.hour >= SLEEP_WINDOW_START_HOUR
        or current_time.hour < SLEEP_WINDOW_END_HOUR
    )


def _infer_rest_type(
    requested_type: int | None,
    last_record: RestRecordModel | None,
    current_time: datetime,
    current_timestamp: int,
) -> int:
    """在快捷指令未提交类型时，按短间隔切换和长间隔作息窗口判定类型。"""
    if requested_type is not None:
        return requested_type

    if last_record is None:
        return (
            RestRecordModel.REST_TYPE_SLEEP
            if _is_sleep_window(current_time)
            else RestRecordModel.REST_TYPE_WAKE_UP
        )

    elapsed_seconds = current_timestamp - last_record.rest_time
    if elapsed_seconds < AUTO_DUPLICATE_GUARD_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="疑似重复打卡：未指定类型的提交距上一条记录不足 2 分钟",
        )

    if elapsed_seconds > AUTO_REANCHOR_SECONDS:
        return (
            RestRecordModel.REST_TYPE_SLEEP
            if _is_sleep_window(current_time)
            else RestRecordModel.REST_TYPE_WAKE_UP
        )

    return 1 - last_record.rest_type


async def sync_rest_record_to_notion(
    rest_record: RestRecordModel,
    rest_type: int,
) -> None:
    """同步已落库记录；外部服务失败不得影响主事务。"""
    from app.core.config import settings
    from app.services.bark import BarkService
    from app.services.notion import NotionService

    database_id = (
        settings.NOTION_WAKE_DATABASE_ID
        if rest_type == RestRecordModel.REST_TYPE_WAKE_UP
        else settings.NOTION_SLEEP_DATABASE_ID
    )
    if not settings.NOTION_TOKEN or not database_id:
        logger.debug("未配置完整 Notion 凭证，跳过休息记录同步")
        return

    notion_service = NotionService(token=settings.NOTION_TOKEN)
    for retry_count in range(1, 4):
        try:
            page_id = await notion_service.add_rest_record(
                database_id=database_id,
                record=rest_record,
            )
            if not page_id:
                raise RuntimeError("Notion 提交失败")
            return
        except Exception as error:
            if retry_count < 3:
                await asyncio.sleep(1)
                continue

            logger.exception("休息记录同步 Notion 失败")
            if settings.BARK_DEFAULT_DEVICE_KEY:
                bark_service = BarkService(
                    base_url=settings.BARK_BASE_URL,
                    default_device_key=settings.BARK_DEFAULT_DEVICE_KEY,
                )
                await bark_service.send_notification(
                    title="Notion同步失败",
                    content=f"休息记录同步失败（重试3次）: {error}",
                )


def schedule_rest_record_sync(
    rest_record: RestRecordModel,
    rest_type: int,
) -> None:
    """仅在配置完整时创建后台同步任务。"""
    from app.core.config import settings

    database_id = (
        settings.NOTION_WAKE_DATABASE_ID
        if rest_type == RestRecordModel.REST_TYPE_WAKE_UP
        else settings.NOTION_SLEEP_DATABASE_ID
    )
    if settings.NOTION_TOKEN and database_id:
        asyncio.create_task(sync_rest_record_to_notion(rest_record, rest_type))


@router.post("/",
             response_model=RestRecord,
             status_code=status.HTTP_201_CREATED,
             summary="创建休息记录",
             description="""
    创建一条新的休息记录，记录用户的睡眠或起床时间。
    
    - **休息类型**:
        - 0: 睡眠
        - 1: 起床
        - 未提交时：距上一条记录超过 12 小时则按北京时间 21:00–05:00 重新判定，
          其余情况按上一条类型切换
    - **位置信息**:
        - 可选填写 WiFi 名称、经纬度和城市信息
    """,
             responses={
                 201: {
                     "description": "创建成功"
                 },
                 401: {
                     "description": "未授权"
                 },
                 409: {
                     "description": "疑似重复的自动打卡"
                 },
                 422: {
                     "description": "请求参数验证失败"
                 },
             })
async def create_rest_record(
    *,
    db: Session = Depends(get_db),
    rest_record_in: RestRecordCreate,
    current_user: User = Depends(get_current_user)
) -> RestRecord:
    """
    创建新的休息记录
    
    休息类型说明：
    - 0: 睡眠
    - 1: 起床
    """
    # 1. 生成本次业务时间；自动判定必须使用 rest_time 而非数据库写入时间。
    cn_now = _current_cn_time()
    rest_time_ts = int(cn_now.timestamp())

    # 2. 确定休息类型。显式类型优先；快捷指令省略类型时按个人作息自动纠偏。
    last_record = None
    if rest_record_in.rest_type is None:
        last_record = db.query(RestRecordModel).filter(
            RestRecordModel.user_id == current_user.id
        ).order_by(RestRecordModel.rest_time.desc()).first()
    rest_type = _infer_rest_type(
        rest_record_in.rest_type,
        last_record,
        cn_now,
        rest_time_ts,
    )

    # 3. month_str 与 rest_time 统一基于北京时间。
    month_str = cn_now.strftime('%m月')

    rest_record = RestRecordModel(user_id=current_user.id,
                                  rest_type=rest_type,
                                  wifi_name=rest_record_in.wifi_name,
                                  latitude=rest_record_in.latitude,
                                  longitude=rest_record_in.longitude,
                                  city=rest_record_in.city,
                                  rest_time=rest_time_ts,
                                  month_str=month_str)
    db.add(rest_record)
    db.commit()
    db.refresh(rest_record)

    schedule_rest_record_sync(rest_record, rest_type)

    return rest_record


@router.get("/",
            response_model=List[RestRecord],
            summary="获取休息记录列表",
            description="""
    获取当前用户的休息记录列表。
    
    - **分页参数**:
        - skip: 跳过记录数
        - limit: 返回记录数限制
    """,
            responses={
                200: {
                    "description": "获取成功"
                },
                401: {
                    "description": "未授权"
                },
            })
async def get_rest_records(*,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user),
                           skip: int = Query(0, ge=0),
                           limit: int = Query(100, ge=1, le=500)) -> List[RestRecord]:
    """
    获取当前用户的休息记录列表
    """
    return (
        db.query(RestRecordModel)
        .filter(RestRecordModel.user_id == current_user.id)
        .order_by(RestRecordModel.rest_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def _dashboard_date_range(
    scope: Literal["month", "year", "all"],
    period: str | None,
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


def _clock_seconds(timestamp: int, *, sleep_time: bool = False) -> int:
    """将睡前凌晨时刻置于当晚 24:00 之后，便于比较作息时间。"""
    local = local_datetime(timestamp)
    value = local.hour * 3600 + local.minute * 60 + local.second
    return value + 24 * 3600 if sleep_time and local.hour < 12 else value


def _format_clock_time(seconds: int) -> str:
    seconds %= 24 * 3600
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def _average_clock_time(timestamps: list[int], *, sleep_time: bool = False) -> str | None:
    if not timestamps:
        return None
    average = int(sum(_clock_seconds(timestamp, sleep_time=sleep_time) for timestamp in timestamps) / len(timestamps))
    return _format_clock_time(average)


@router.get(
    "/sessions",
    response_model=SleepDashboardResponse,
    summary="查询睡眠会话看板",
)
async def get_sleep_sessions(
    scope: Literal["month", "year", "all"] = Query("month"),
    period: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SleepDashboardResponse:
    start, end, normalized_period = _dashboard_date_range(scope, period)
    records = (
        db.query(RestRecordModel)
        .filter(RestRecordModel.user_id == current_user.id)
        .order_by(RestRecordModel.rest_time.asc())
        .all()
    )
    sessions = pair_rest_events(records)
    if start is not None and end is not None:
        sessions = [item for item in sessions if start <= item.sleep_date <= end]
    sessions.sort(
        key=lambda item: (item.sleep_date, (item.sleep or item.wake).rest_time),
        reverse=True,
    )

    # 原始缺端事件会保留在 records 中供用户修正或删除，但不能污染任何时长、
    # 作息时间和热力统计。pagination 仍按全部会话计算，以便错误记录可被找到。
    complete = [item for item in sessions if item.is_complete]
    incomplete = [item for item in sessions if not item.is_complete]
    durations = [item.duration_hours for item in complete if item.duration_hours is not None]
    # “近三年”入口的统计和分页仍覆盖全部历史；只对热力图裁剪日期，
    # 防止一次响应和浏览器 DOM 随多年数据无限增长。
    heatmap_sessions = sessions
    if scope == "all":
        heatmap_start = _recent_history_start(datetime.now(tz=CN_TIMEZONE).date())
        heatmap_sessions = [
            item for item in sessions if item.sleep_date >= heatmap_start
        ]

    daily = defaultdict(
        lambda: {"duration": 0.0, "sessions": 0, "complete": 0, "errors": 0}
    )
    for item in heatmap_sessions:
        bucket = daily[item.sleep_date]
        if item.is_complete and item.duration_hours is not None:
            bucket["sessions"] += 1
            bucket["duration"] += item.duration_hours
            bucket["complete"] += 1
        else:
            bucket["errors"] += 1

    total = len(complete)
    longest_duration = max(durations) if durations else None
    earliest_sleep_value = min(
        (_clock_seconds(item.sleep.rest_time, sleep_time=True) for item in complete if item.sleep),
        default=None,
    )
    earliest_wake_value = min(
        (_clock_seconds(item.wake.rest_time) for item in complete if item.wake),
        default=None,
    )
    longest_session_ids = {
        item.anchor_id
        for item in complete
        if longest_duration is not None and item.duration_hours == longest_duration
    }
    earliest_sleep_ids = {
        item.anchor_id
        for item in complete
        if item.sleep is not None
        and earliest_sleep_value is not None
        and _clock_seconds(item.sleep.rest_time, sleep_time=True) == earliest_sleep_value
    }
    earliest_wake_ids = {
        item.anchor_id
        for item in complete
        if item.wake is not None
        and earliest_wake_value is not None
        and _clock_seconds(item.wake.rest_time) == earliest_wake_value
    }
    longest_session = next(
        (item for item in complete if item.anchor_id in longest_session_ids), None
    )
    earliest_sleep = next(
        (item for item in complete if item.anchor_id in earliest_sleep_ids), None
    )
    earliest_wake = next(
        (item for item in complete if item.anchor_id in earliest_wake_ids), None
    )
    wake_city_ranking = Counter(
        item.wake.city for item in complete if item.wake and item.wake.city
    ).most_common(3)
    offset = (page - 1) * page_size
    page_sessions = sessions[offset:offset + page_size]
    response = {
        "scope": scope,
        "period": normalized_period,
        "summary": {
            "total_sessions": total,
            "complete_sessions": len(complete),
            "incomplete_sessions": len(incomplete),
            "average_duration_hours": round(sum(durations) / len(durations), 2) if durations else None,
            "longest_duration_hours": round(longest_duration, 2) if longest_duration is not None else None,
            "shortest_duration_hours": round(min(durations), 2) if durations else None,
            "average_sleep_time": _average_clock_time(
                [item.sleep.rest_time for item in complete if item.sleep], sleep_time=True
            ),
            "average_wake_time": _average_clock_time(
                [item.wake.rest_time for item in complete if item.wake]
            ),
            "longest_session": (
                {
                    "date": longest_session.sleep_date,
                    "duration_hours": round(longest_session.duration_hours, 2),
                }
                if longest_session and longest_session.duration_hours is not None
                else None
            ),
            "earliest_sleep": (
                {
                    "date": earliest_sleep.sleep_date,
                    "time": _format_clock_time(_clock_seconds(earliest_sleep.sleep.rest_time, sleep_time=True)),
                }
                if earliest_sleep and earliest_sleep.sleep is not None
                else None
            ),
            "earliest_wake": (
                {
                    "date": earliest_wake.sleep_date,
                    "time": _format_clock_time(_clock_seconds(earliest_wake.wake.rest_time)),
                }
                if earliest_wake and earliest_wake.wake is not None
                else None
            ),
            "wake_city_ranking": [
                {"city": city, "count": count} for city, count in wake_city_ranking
            ],
        },
        "heatmap": [
            {
                "date": day,
                "duration_hours": round(values["duration"], 2) if values["complete"] else None,
                "session_count": values["sessions"],
                "complete_count": values["complete"],
                "error_count": values["errors"],
                "is_longest_session": day in {
                    item.sleep_date for item in complete if item.anchor_id in longest_session_ids
                },
                "is_earliest_sleep": day in {
                    item.sleep_date for item in complete if item.anchor_id in earliest_sleep_ids
                },
                "is_earliest_wake": day in {
                    item.sleep_date for item in complete if item.anchor_id in earliest_wake_ids
                },
            }
            for day, values in sorted(daily.items())
        ],
        "records": [session_payload(item) for item in page_sessions],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": len(sessions),
            "total_pages": math.ceil(len(sessions) / page_size) if sessions else 0,
        },
    }
    return SleepDashboardResponse.model_validate(response)


@router.delete(
    "/sessions/{anchor_record_id}",
    response_model=DeleteSleepSessionResponse,
    summary="删除本地睡眠会话",
)
async def delete_sleep_session(
    anchor_record_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeleteSleepSessionResponse:
    records = (
        db.query(RestRecordModel)
        .filter(RestRecordModel.user_id == current_user.id)
        .order_by(RestRecordModel.rest_time.asc())
        .all()
    )
    target = next(
        (
            item
            for item in pair_rest_events(records)
            if anchor_record_id in {
                getattr(item.sleep, "id", None),
                getattr(item.wake, "id", None),
            }
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="未找到该睡眠会话")

    deleted = [record for record in (target.sleep, target.wake) if record is not None]
    for record in deleted:
        db.delete(record)
    db.commit()
    return DeleteSleepSessionResponse(
        deleted_record_ids=[record.id for record in deleted],
        deleted_count=len(deleted),
    )


@router.get("/annual-summary/{year}/table",
            response_model=AnnualSummaryTableResponse,
            summary="获取年度睡眠总结明细表",
            description="返回一整年每一天的睡眠会话明细，包括入睡/起床时间、时长及位置，用于查漏补缺。")
async def get_annual_summary_table(
    year: int = Path(..., ge=1970, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> AnnualSummaryTableResponse:
    # 睡眠日按起床自然日跨年，因此先投影全部事件再按起床年过滤。
    records = db.query(RestRecordModel).filter(
        RestRecordModel.user_id == current_user.id,
    ).order_by(RestRecordModel.rest_time.asc()).all()
    sessions = []
    for item in pair_rest_events(records):
        if item.sleep_date.year != year:
            continue
        sleep_at = local_datetime(item.sleep.rest_time) if item.sleep else None
        wake_at = local_datetime(item.wake.rest_time) if item.wake else None
        sessions.append({
            "date": item.sleep_date.isoformat(),
            "sleep_time": sleep_at.strftime("%H:%M") if sleep_at else None,
            "wake_time": wake_at.strftime("%H:%M") if wake_at else None,
            "duration": round(item.duration_hours, 2) if item.duration_hours is not None else None,
            "city": getattr(item.wake, "city", None) or getattr(item.sleep, "city", None),
            "wifi": getattr(item.wake, "wifi_name", None) or getattr(item.sleep, "wifi_name", None),
            "error_code": item.error_code,
        })

    return {
        "year": str(year),
        "count": len(sessions),
        "records": sorted(sessions, key=lambda x: x['date'], reverse=True)
    }


@router.get("/annual-summary/{year}",
            response_model=AnnualSummaryResponse,
            summary="获取年度睡眠总结",
            description="从多个维度统计用户一整年的入睡和起床数据，生成年度报告。")
async def get_annual_summary(
    year: int = Path(..., ge=1970, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> AnnualSummaryResponse:
    import statistics
    from collections import Counter

    records = db.query(RestRecordModel).filter(
        RestRecordModel.user_id == current_user.id,
    ).order_by(RestRecordModel.rest_time.asc()).all()

    if not records:
        raise HTTPException(status_code=404, detail=f"未找到 {year} 年的休息记录")

    sessions = [
        {
            "sleep": item.sleep,
            "wake": item.wake,
            "dur": item.duration_hours,
            "sleep_date": item.sleep_date,
        }
        for item in pair_rest_events(records)
        if item.sleep_date.year == year
    ]
    if not sessions:
        raise HTTPException(status_code=404, detail=f"未找到 {year} 年的休息记录")

    # 缺少入睡或起床端点的事件只属于数据质量问题，不能进入年度指标、连续天数或位置统计。
    valid_sessions = [
        session for session in sessions
        if session["sleep"] is not None
        and session["wake"] is not None
        and session["dur"] is not None
    ]

    # 建立日期索引（以睡眠日，即起床当天为准）
    daily_sessions = {} # {date_str: session}
    for s in valid_sessions:
        d_str = s['sleep_date'].isoformat()
        daily_sessions[d_str] = s

    # --- 数据质量分析 ---
    start_date = date(int(year), 1, 1)
    end_date = min(date(int(year), 12, 31), date.today())
    missing_sleep = []
    missing_wake = []
    
    curr = start_date
    while curr <= end_date:
        d_str = curr.strftime('%Y-%m-%d')
        s = daily_sessions.get(d_str)
        if not s or not s['sleep']: missing_sleep.append(d_str)
        if not s or not s['wake']: missing_wake.append(d_str)
        curr += timedelta(days=1)

    # --- 核心指标计算 ---
    sleep_times = [] # 秒
    wake_times = []  # 秒
    durations = []   # 小时
    monthly = {}     # {month_str: {"total_dur": 0, "dur_count": 0, "record_count": 0}}

    latest_sleep = {"time": 0, "date": "", "val": ""}
    earliest_wake = {"time": 86400, "date": "", "val": ""}
    longest_sleep = {"dur": 0, "date": "", "val": ""}
    shortest_sleep = {"dur": 100, "date": "", "val": ""}

    for s in valid_sessions:
        m_str = s['sleep_date'].strftime('%m月')
        if m_str not in monthly: monthly[m_str] = {"total_dur": 0, "dur_count": 0, "record_count": 0}
        
        if s['sleep']:
            dt_s = to_cn_timezone(s['sleep'].rest_time)
            s_hour = dt_s.hour
            s_tod = s_hour * 3600 + dt_s.minute * 60 + dt_s.second
            if s_hour < 12: s_tod += 86400 # 跨天处理
            sleep_times.append(s_tod)
            if s_tod > latest_sleep["time"]:
                latest_sleep = {"time": s_tod, "date": dt_s.strftime('%m-%d'), "val": dt_s.strftime('%H:%M')}
            monthly[m_str]["record_count"] += 1

        if s['wake']:
            dt_w = to_cn_timezone(s['wake'].rest_time)
            w_tod = dt_w.hour * 3600 + dt_w.minute * 60 + dt_w.second
            wake_times.append(w_tod)
            if w_tod < earliest_wake["time"]:
                earliest_wake = {"time": w_tod, "date": dt_w.strftime('%m-%d'), "val": dt_w.strftime('%H:%M')}
            if not s['sleep']: # 如果是孤立起床，也计入频次
                monthly[m_str]["record_count"] += 1

        if s['dur'] and 1 < s['dur'] < 24:
            durations.append(s['dur'])
            monthly[m_str]["total_dur"] += s['dur']
            monthly[m_str]["dur_count"] += 1
            if s['dur'] > longest_sleep["dur"]:
                longest_sleep = {"dur": s['dur'], "date": s['sleep_date'].strftime('%m-%d'), "val": f"{s['dur']:.1f}h"}
            if s['dur'] < shortest_sleep["dur"]:
                shortest_sleep = {"dur": s['dur'], "date": s['sleep_date'].strftime('%m-%d'), "val": f"{s['dur']:.1f}h"}

    avg_s = sum(sleep_times)/len(sleep_times) if sleep_times else 0
    avg_w = sum(wake_times)/len(wake_times) if wake_times else 0
    avg_d = sum(durations)/len(durations) if durations else 0

    def format_tod(seconds):
        seconds = seconds % 86400
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h:02d}:{m:02d}"

    # --- 连续天数 ---
    max_streak = 0
    current_streak = 0
    all_active_days = sorted(daily_sessions.keys())
    if all_active_days:
        prev_d = datetime.strptime(all_active_days[0], '%Y-%m-%d').date()
        current_streak = 1
        max_streak = 1
        for i in range(1, len(all_active_days)):
            curr_d = datetime.strptime(all_active_days[i], '%Y-%m-%d').date()
            if (curr_d - prev_d).days == 1:
                current_streak += 1
            else:
                current_streak = 1
            max_streak = max(max_streak, current_streak)
            prev_d = curr_d

    stdev_s = statistics.stdev(sleep_times) if len(sleep_times) > 1 else 3600
    consistency_score = max(0, min(100, int(100 - (stdev_s / 3600) * 10))) 

    # --- 空间统计 ---
    relevant_records = [
        record
        for session in valid_sessions
        for record in (session["sleep"], session["wake"])
        if record is not None
    ]
    all_cities = [r.city for r in relevant_records if r.city]
    distinct_cities_count = len(set(all_cities))
    wake_cities = [r.city for r in relevant_records if r.city and r.rest_type == 1]
    distinct_wake_cities_count = len(set(wake_cities))

    return {
        "overview": {
            "year": str(year),
            "total_days_logged": len(daily_sessions),
            "distinct_cities_count": distinct_cities_count,
            "distinct_wake_cities_count": distinct_wake_cities_count,
            "avg_sleep_time": format_tod(avg_s),
            "avg_wake_time": format_tod(avg_w),
            "avg_duration_hrs": round(avg_d, 1)
        },
        "extremes": {
            "latest_sleep": {"date": latest_sleep["date"], "value": latest_sleep["val"], "description": "全年最晚入睡"},
            "earliest_wake": {"date": earliest_wake["date"], "value": earliest_wake["val"], "description": "全年最早起床"},
            "longest_sleep": {"date": longest_sleep["date"], "value": longest_sleep["val"], "description": "全年最长睡眠"},
            "shortest_sleep": {"date": shortest_sleep["date"], "value": shortest_sleep["val"], "description": "全年最短睡眠"}
        },
        "consistency": {
            "max_streak": max_streak,
            "consistency_score": consistency_score,
            "remark": "作息稳如泰山" if consistency_score > 85 else "作息略显随性"
        },
        "spatial": [{"name": n, "count": c, "type": "city"} for n, c in Counter(all_cities).most_common(2)],
        "monthly_trends": [
            {
                "month": m, 
                "avg_duration": round(float(v["total_dur"] / v["dur_count"]), 1) if v["dur_count"] > 0 else 0.0, 
                "record_count": v["record_count"]
            } for m, v in sorted(monthly.items())
        ],
        "data_integrity": {
            "missing_sleep_dates": missing_sleep,
            "missing_wake_dates": missing_wake,
            "total_missing_count": len(missing_sleep) + len(missing_wake)
        },
        "persona_tags": ["规律生活家" if consistency_score > 90 else "自由灵魂"],
        "summary_text": f"这一年，你像候鸟一样在 {distinct_cities_count} 个城市间穿梭。愿新的一年，无论身在何处，都能拥有高质量的软绵绵好梦。"
    }
