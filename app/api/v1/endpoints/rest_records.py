from ast import If
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.rest_record import RestRecord as RestRecordModel
from app.models.user import User
from app.schemas.rest_record import (AnnualSummaryResponse,
                                     AnnualSummaryTableResponse, RestRecord,
                                     RestRecordCreate, to_cn_timezone)

router = APIRouter()


@router.post("/",
             response_model=RestRecord,
             status_code=status.HTTP_201_CREATED,
             summary="创建休息记录",
             description="""
    创建一条新的休息记录，记录用户的睡眠或起床时间。
    
    - **休息类型**:
        - 0: 睡眠
        - 1: 起床
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
    # 1. 确定休息类型
    rest_type = rest_record_in.rest_type
    if rest_type is None:
        # 获取最新的一条记录来判断
        last_record = db.query(RestRecordModel).filter(
            RestRecordModel.user_id == current_user.id
        ).order_by(RestRecordModel.rest_time.desc()).first()
        
        if last_record:
            rest_type = 1 - last_record.rest_type
        else:
            rest_type = 0  # 默认第一条是睡眠

    # 2. 处理时间（修复时区问题：确保 month_str 与 rest_time 统一基于北京时间）
    cn_now = to_cn_timezone(int(datetime.now().timestamp()))
    rest_time_ts = int(cn_now.timestamp())
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

    # --- 新增异步业务流程 ---
    import asyncio

    from app.core.config import settings
    from app.core.services.bark_service import BarkService
    from app.core.services.notion_service import NotionService

    async def notion_and_bark_task():
        notion_service = NotionService(token=settings.NOTION_TOKEN)
        bark_service = BarkService(
            base_url=settings.BARK_BASE_URL,
            default_device_key=settings.BARK_DEFAULT_DEVICE_KEY)
        retry_count = 0
        max_retries = 3
        while retry_count < max_retries:
            try:
                page_id = await notion_service.add_rest_record(
                    database_id=settings.NOTION_WAKE_DATABASE_ID
                    if rest_type == 1 else
                    settings.NOTION_SLEEP_DATABASE_ID,
                    record=rest_record)
                if not page_id:
                    raise Exception("Notion提交失败")
                break
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    # 重试3次后仍失败，发 Bark 通知
                    await bark_service.send_notification(
                        title="Notion同步失败",
                        content=f"休息记录同步失败（重试{max_retries}次）: {str(e)}")
                else:
                    # 重试间隔，例如 1 秒
                    await asyncio.sleep(1)

    asyncio.create_task(notion_and_bark_task())
    # --- 业务流程结束 ---

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
                           skip: int = 0,
                           limit: int = 100) -> List[RestRecord]:
    """
    获取当前用户的休息记录列表
    """
@router.get("/annual-summary/{year}/table",
            response_model=AnnualSummaryTableResponse,
            summary="获取年度睡眠总结明细表",
            description="返回一整年每一天的睡眠会话明细，包括入睡/起床时间、时长及位置，用于查漏补缺。")
async def get_annual_summary_table(
    year: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> AnnualSummaryTableResponse:
    # 复用统计算法中的配对逻辑
    from datetime import date, timedelta
    start_ts = int(datetime.strptime(f"{year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp())
    end_ts = int(datetime.strptime(f"{year}-12-31 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp())
    records = db.query(RestRecordModel).filter(
        RestRecordModel.user_id == current_user.id,
        RestRecordModel.rest_time >= start_ts,
        RestRecordModel.rest_time <= end_ts
    ).order_by(RestRecordModel.rest_time.asc()).all()

    if not records:
        return {"year": year, "count": 0, "records": []}

    # 核心配对算法
    sessions = []
    i = 0
    used_records = set()
    while i < len(records):
        if i in used_records:
            i += 1
            continue
        
        r = records[i]
        if r.rest_type == 0: # 睡眠
            found_wake = False
            for j in range(i + 1, min(i + 10, len(records))):
                if records[j].rest_type == 1: # 起床
                    dt_s = to_cn_timezone(r.rest_time)
                    dt_w = to_cn_timezone(records[j].rest_time)
                    dur = (records[j].rest_time - r.rest_time) / 3600.0
                    if 0 < dur < 24:
                        sessions.append({
                            "date": dt_w.strftime('%Y-%m-%d'),
                            "sleep_time": dt_s.strftime('%H:%M'),
                            "wake_time": dt_w.strftime('%H:%M'),
                            "duration": round(dur, 2),
                            "city": records[j].city or r.city,
                            "wifi": records[j].wifi_name or r.wifi_name
                        })
                        used_records.add(i)
                        used_records.add(j)
                        found_wake = True
                        break
            if not found_wake:
                dt_s = to_cn_timezone(r.rest_time)
                sessions.append({
                    "date": dt_s.strftime('%Y-%m-%d'),
                    "sleep_time": dt_s.strftime('%H:%M'),
                    "wake_time": None,
                    "duration": None,
                    "city": r.city,
                    "wifi": r.wifi_name
                })
        else: # 未配对的起床
            dt_w = to_cn_timezone(r.rest_time)
            sessions.append({
                "date": dt_w.strftime('%Y-%m-%d'),
                "sleep_time": None,
                "wake_time": dt_w.strftime('%H:%M'),
                "duration": None,
                "city": r.city,
                "wifi": r.wifi_name
            })
        i += 1

    return {
        "year": year,
        "count": len(sessions),
        "records": sorted(sessions, key=lambda x: x['date'], reverse=True)
    }


@router.get("/annual-summary/{year}",
            response_model=AnnualSummaryResponse,
            summary="获取年度睡眠总结",
            description="从多个维度统计用户一整年的入睡和起床数据，生成年度报告。")
async def get_annual_summary(
    year: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> AnnualSummaryResponse:
    import statistics
    from collections import Counter
    from datetime import date, timedelta

    start_ts = int(datetime.strptime(f"{year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp())
    end_ts = int(datetime.strptime(f"{year}-12-31 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp())

    records = db.query(RestRecordModel).filter(
        RestRecordModel.user_id == current_user.id,
        RestRecordModel.rest_time >= start_ts,
        RestRecordModel.rest_time <= end_ts
    ).order_by(RestRecordModel.rest_time.asc()).all()

    if not records:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"未找到 {year} 年的休息记录")

    # --- 改进的配对与统计逻辑 ---
    sessions = []
    i = 0
    used_records = set()
    while i < len(records):
        if i in used_records:
            i += 1
            continue
        r = records[i]
        if r.rest_type == 0: # 睡眠
            found_wake = False
            for j in range(i + 1, min(i + 10, len(records))):
                if records[j].rest_type == 1:
                    dur = (records[j].rest_time - r.rest_time) / 3600.0
                    if 0 < dur < 24:
                        sessions.append({"sleep": r, "wake": records[j], "dur": dur})
                        used_records.add(i)
                        used_records.add(j)
                        found_wake = True
                        break
            if not found_wake:
                sessions.append({"sleep": r, "wake": None, "dur": None})
        else: # 孤立起床
            sessions.append({"sleep": None, "wake": r, "dur": None})
        i += 1

    # 建立日期索引（以起床日期为准）
    daily_sessions = {} # {date_str: session}
    for s in sessions:
        ref_record = s['wake'] or s['sleep']
        d_str = to_cn_timezone(ref_record.rest_time).strftime('%Y-%m-%d')
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

    for s in sessions:
        m_str = to_cn_timezone((s['wake'] or s['sleep']).rest_time).strftime('%m月')
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
            dt_w = to_cn_timezone(s['wake'].rest_time)
            if s['dur'] > longest_sleep["dur"]:
                longest_sleep = {"dur": s['dur'], "date": dt_w.strftime('%m-%d'), "val": f"{s['dur']:.1f}h"}
            if s['dur'] < shortest_sleep["dur"]:
                shortest_sleep = {"dur": s['dur'], "date": dt_w.strftime('%m-%d'), "val": f"{s['dur']:.1f}h"}

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
    all_cities = [r.city for r in records if r.city]
    distinct_cities_count = len(set(all_cities))
    wake_cities = [r.city for r in records if r.city and r.rest_type == 1]
    distinct_wake_cities_count = len(set(wake_cities))

    return {
        "overview": {
            "year": year,
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
