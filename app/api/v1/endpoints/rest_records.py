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
                                  rest_time=int(now.timestamp()),
                                  month_str=now.strftime('%m月'))
    db.add(rest_record)
    db.commit()
    db.refresh(rest_record)
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
