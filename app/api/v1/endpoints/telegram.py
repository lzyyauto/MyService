import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.telegram import TelegramDownloadRequest, TelegramDownloadResponse
from app.services.telegram_service import telegram_service

router = APIRouter()
logger = logging.getLogger(__name__)

async def background_download(url: str, user_id: str):
    """后台执行下载"""
    try:
        logger.info(f"Starting background download for user {user_id}: {url}")
        file_paths = await telegram_service.get_and_download_video(url)
        if file_paths:
            logger.info(f"Background download success for user {user_id}: {len(file_paths)} files saved.")
            for path in file_paths:
                logger.info(f" - {path}")
        else:
            logger.warning(f"Background download failed or timeout for user {user_id}: {url}")
    except Exception as e:
        logger.error(f"Error in background download for user {user_id}: {str(e)}", exc_info=True)

@router.post("/download", 
             response_model=TelegramDownloadResponse,
             summary="通过 Telegram 下载抖音或 Twitter 视频",
             description="""
    发送视频链接，后端将立即返回“开始下载”。
    真实的下载逻辑将通过 Telegram Userbot 在后台异步执行。
    支持的域名：
    - 抖音: douyin.com, iesdouyin.com, v.douyin.com
    - Twitter/X: x.com, twitter.com
    """)
async def download_via_telegram(
    request: TelegramDownloadRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
) -> TelegramDownloadResponse:
    """
    接收 URL，触发异步 Telegram 下载逻辑。
    """
    try:
        logger.info(f"User {current_user.id} requested Telegram download for URL: {request.url}")
        
        # 添加到后台任务
        background_tasks.add_task(background_download, request.url, str(current_user.id))
        
        return TelegramDownloadResponse(
            success=True,
            message="任务已提交，后台开始下载"
        )
            
    except Exception as e:
        logger.error(f"Telegram download API error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"任务提交失败: {str(e)}"
        )
