from typing import Optional, List
from pydantic import BaseModel, Field

class TelegramDownloadRequest(BaseModel):
    """Telegram 下载请求"""
    url: str = Field(..., description="抖音或 Twitter 视频链接", example="https://v.douyin.com/xxxxxx")

class TelegramDownloadResponse(BaseModel):
    """Telegram 下载响应"""
    success: bool = Field(..., description="是否下载成功")
    file_paths: Optional[List[str]] = Field(None, description="下载后的本地文件路径列表")
    error: Optional[str] = Field(None, description="错误信息")
    message: str = Field(..., description="响应消息")
