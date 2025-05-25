from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.gtd_task import GtdTask as GtdTaskModel
from app.models.user import User
from app.schemas.gtd_task import GtdTask, GtdTaskCreate

router = APIRouter()


@router.post("/",
             response_model=GtdTask,
             status_code=status.HTTP_201_CREATED,
             summary="创建任务",
             description="""
    创建新的任务记录。
    
    - **任务状态**:
        - 0: 待办
        - 1: 进行中
        - 2: 已完成
        - 3: 已取消
    - **优先级**: 0-10，数字越大优先级越高
    - **时间**: 使用时间戳格式
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
async def create_gtd_task(
    *,
    db: Session = Depends(get_db),
    task_in: GtdTaskCreate,
    current_user: User = Depends(get_current_user)
) -> GtdTask:
    task = GtdTaskModel(user_id=current_user.id,
                        name=task_in.name,
                        start_time=task_in.start_time,
                        end_time=task_in.end_time,
                        priority=task_in.priority,
                        category=task_in.category,
                        status=task_in.status)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
