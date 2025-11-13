"""
视频处理任务API Schema
Pydantic模型用于请求验证和响应序列化
"""

from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl, validator
import re


class VideoProcessTaskBase(BaseModel):
    """视频处理任务基础模型"""

    status: str = Field(..., description="任务状态")
    original_url: str = Field(..., description="原始视频URL")
    video_path: Optional[str] = Field(None, description="视频文件路径")
    audio_path: Optional[str] = Field(None, description="音频文件路径")
    subtitle_text: Optional[str] = Field(None, description="字幕文字")
    ai_summary: Optional[str] = Field(None, description="AI总结")

    class Config:
        from_attributes = True


class VideoProcessRequest(BaseModel):
    """创建视频处理任务请求"""

    video_url: str = Field(
        ...,
        description="抖音视频链接（可包含其他文字）",
        example="请处理这个视频：https://v.douyin.com/iJgDkYhC/"
    )

    @validator('video_url')
    def validate_url(cls, v):
        """验证URL是否包含有效的视频链接"""
        # 检查是否包含http或https链接
        url_pattern = r'https?://[^\s]+'
        if not re.search(url_pattern, v):
            raise ValueError('必须包含有效的URL')

        # 提取URL并验证
        match = re.search(url_pattern, v)
        if match:
            url = match.group()
            # 验证是否为抖音相关URL
            if not any(domain in url for domain in ['douyin.com', 'iesdouyin.com', 'v.douyin.com']):
                raise ValueError('必须是抖音相关链接')

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "video_url": "请处理这个视频：https://v.douyin.com/iJgDkYhC/"
            }
        }


class VideoProcessResponse(BaseModel):
    """创建视频处理任务响应"""

    task_id: UUID = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="响应消息")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "任务已创建，正在处理中..."
            }
        }


class VideoProcessTaskResponse(BaseModel):
    """查询任务状态响应"""

    task_id: UUID = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    summary: Optional[str] = Field(None, description="AI总结（仅在完成时返回）")
    original_url: str = Field(..., description="原始URL")
    video_path: Optional[str] = Field(None, description="视频文件路径")
    audio_path: Optional[str] = Field(None, description="音频文件路径")
    subtitle_text: Optional[str] = Field(None, description="字幕文字")
    message: str = Field(..., description="响应消息")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "summary": "这是一个关于...的视频，主要讲述了...",
                "original_url": "https://v.douyin.com/iJgDkYhC/",
                "video_path": "temp/video/1234567890.mp4",
                "audio_path": "temp/video/1234567890.mp3",
                "subtitle_text": "大家好，今天我要分享的是...",
                "message": "查询成功"
            }
        }


class VideoProcessTaskUpdate(BaseModel):
    """更新任务模型（用于内部使用）"""

    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    subtitle_text: Optional[str] = None
    ai_summary: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== 新的URL解析接口Schema ====================

class VideoUrlRequest(BaseModel):
    """URL解析请求"""

    url: str = Field(
        ...,
        description="抖音链接（视频、图片或Live Photo，可包含其他文字）",
        example="请解析这个链接：https://v.douyin.com/iJgDkYhC/"
    )

    @validator('url')
    def validate_url(cls, v):
        """验证URL是否包含有效的链接"""
        # 检查是否包含http或https链接
        url_pattern = r'https?://[^\s]+'
        if not re.search(url_pattern, v):
            raise ValueError('必须包含有效的URL')

        # 提取URL并验证
        match = re.search(url_pattern, v)
        if match:
            url = match.group()
            # 验证是否为抖音相关URL
            if not any(domain in url for domain in ['douyin.com', 'iesdouyin.com', 'v.douyin.com']):
                raise ValueError('必须是抖音相关链接')

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "url": "请解析这个链接：https://v.douyin.com/iJgDkYhC/"
            }
        }


class VideoParseResponse(BaseModel):
    """URL解析响应"""

    success: bool = Field(..., description="是否成功")
    media_type: str = Field(..., description="媒体类型：video/image/live_photo")
    aweme_id: str = Field(..., description="作品ID")
    desc: str = Field(..., description="作品描述")
    author: str = Field(..., description="作者昵称")
    download_urls: List[str] = Field(..., description="下载链接列表")
    error: Optional[str] = Field(None, description="错误信息（失败时返回）")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "media_type": "video",
                "aweme_id": "7571858909406989683",
                "desc": "这是一个测试视频",
                "author": "作者昵称",
                "download_urls": [
                    "https://example.com/video1.mp4",
                    "https://example.com/video2.mp4"
                ]
            }
        }
