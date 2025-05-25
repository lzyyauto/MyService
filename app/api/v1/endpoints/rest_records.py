from ast import If
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.rest_record import RestRecord as RestRecordModel
from app.models.user import User
from app.schemas.rest_record import RestRecord, RestRecordCreate

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
    now = datetime.now()
    rest_record = RestRecordModel(user_id=current_user.id,
                                  rest_type=rest_record_in.rest_type,
                                  wifi_name=rest_record_in.wifi_name,
                                  latitude=rest_record_in.latitude,
                                  longitude=rest_record_in.longitude,
                                  city=rest_record_in.city,
                                  rest_time=int(now.timestamp()),
                                  month_str=now.strftime('%m月'))
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
                    if rest_record_in.rest_type == 1 else
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
    rest_records = db.query(RestRecordModel)\
        .filter(RestRecordModel.user_id == current_user.id)\
        .offset(skip)\
        .limit(limit)\
        .all()
    return rest_records
