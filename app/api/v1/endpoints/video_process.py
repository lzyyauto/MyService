"""
视频处理API端点
提供视频下载、音频提取、语音识别、AI总结等功能
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, status, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.video_process_task import VideoProcessTask
from app.schemas.video_process_task import (
    VideoProcessRequest,
    VideoProcessResponse,
    VideoProcessTaskResponse
)
from app.core.services.video_processor_service import VideoProcessorService

router = APIRouter()


async def process_video_task(
    task_id: str,
    video_url: str,
    db: Session
):
    """后台视频处理任务"""
    try:
        processor = VideoProcessorService(db)
        await processor.process_video(task_id, video_url)
    except Exception as e:
        # 错误已在processor中处理并记录
        pass


@router.post("/",
             response_model=VideoProcessResponse,
             status_code=status.HTTP_201_CREATED,
             summary="提交视频处理任务",
             description="""
    提交抖音视频链接进行完整处理，包括以下步骤：

    1. **视频下载**: 自动解析URL，提取无水印视频
    2. **音频提取**: 使用ffmpeg将视频转换为音频
    3. **语音识别**: 调用AI服务将音频转换为文字
    4. **AI总结**: 对字幕进行智能总结和精简

    - **URL格式**: 支持抖音短链接或完整链接，可包含其他文字
    - **处理方式**: 异步处理，立即返回task_id供后续查询
    - **去重机制**: 相同视频ID的任务不会重复处理
    """,
             responses={
                 201: {
                     "description": "任务创建成功"
                 },
                 400: {
                     "description": "URL格式无效或不是抖音链接"
                 },
                 401: {
                     "description": "未授权"
                 },
                 409: {
                     "description": "视频已处理完成，返回已有结果"
                 },
                 422: {
                     "description": "请求参数验证失败"
                 },
                 500: {
                     "description": "服务器内部错误"
                 },
             })
async def create_video_process_task(
    *,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks,
    request: VideoProcessRequest,
    current_user: User = Depends(get_current_user)
) -> VideoProcessResponse:
    """
    创建新的视频处理任务

    接收视频URL，创建任务并立即返回task_id，后台异步执行处理流程。
    """
    # 检查是否已存在处理记录（去重）
    processor = VideoProcessorService(db)
    existing_task = processor.check_existing_task(request.video_url)

    if existing_task:
        # 已存在完成的任务，直接返回
        return VideoProcessResponse(
            task_id=existing_task.id,
            status=existing_task.status,
            message="视频已处理完成，返回已有结果"
        )

    # 创建新任务
    task = VideoProcessTask(
        user_id=current_user.id,
        original_url=request.video_url,
        status=VideoProcessTask.STATUS_PENDING
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 添加后台任务
    background_tasks.add_task(
        process_video_task,
        task_id=str(task.id),
        video_url=request.video_url,
        db=db
    )

    return VideoProcessResponse(
        task_id=task.id,
        status=task.status,
        message="任务已创建，正在后台处理中..."
    )


@router.get("/{task_id}",
            response_model=VideoProcessTaskResponse,
            summary="查询任务状态",
            description="""
    根据task_id查询视频处理任务的详细状态和结果。

    - **状态说明**:
        - pending: 等待处理
        - processing: 处理中
        - completed: 已完成
        - failed: 处理失败

    - **返回结果**:
        - 完成后返回：视频路径、音频路径、字幕文字、AI总结
        - 处理中返回：当前状态
        - 失败时返回：错误信息
    """,
            responses={
                 200: {
                     "description": "查询成功"
                 },
                 401: {
                     "description": "未授权"
                 },
                 403: {
                     "description": "无权限访问此任务"
                 },
                 404: {
                     "description": "任务不存在"
                 },
             })
async def get_video_process_task(
    *,
    db: Session = Depends(get_db),
    task_id: str,
    current_user: User = Depends(get_current_user)
) -> VideoProcessTaskResponse:
    """
    获取视频处理任务的状态和结果

    通过task_id查询任务的详细状态，如果是已完成的任务，同时返回处理结果。
    """
    # 查询任务
    task = db.query(VideoProcessTask).filter(
        VideoProcessTask.id == task_id
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )

    # 检查权限（只能查看自己的任务）
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限访问此任务"
        )

    # 根据状态返回不同的响应
    if task.status == VideoProcessTask.STATUS_COMPLETED:
        # 完成任务返回完整结果
        return VideoProcessTaskResponse(
            task_id=task.id,
            status=task.status,
            summary=task.ai_summary,
            original_url=task.original_url,
            video_path=task.video_path,
            audio_path=task.audio_path,
            subtitle_text=task.subtitle_text,
            message="查询成功"
        )
    else:
        # 未完成任务返回状态信息
        return VideoProcessTaskResponse(
            task_id=task.id,
            status=task.status,
            summary=None,
            original_url=task.original_url,
            video_path=None,
            audio_path=None,
            subtitle_text=None,
            message="查询成功"
        )
