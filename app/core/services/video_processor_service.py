"""
视频处理服务
整合视频下载、音频提取、语音识别、AI总结等全部功能
完全迁移至 Telegram 下载引擎，废弃第三方 API 服务
"""

import asyncio
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.services.bark_service import BarkService
from app.utils.ai_client import get_ai_client
from app.models.video_process_task import VideoProcessTask
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)


class VideoProcessorService:
    """视频处理服务"""

    def __init__(self, db: Session):
        """
        初始化视频处理服务

        Args:
            db: 数据库会话
        """
        self.db = db
        self.bark_service = BarkService(
            base_url=getattr(settings, 'BARK_BASE_URL', 'https://api.day.app'),
            default_device_key=getattr(settings, 'BARK_DEFAULT_DEVICE_KEY', None)
        )
        self.temp_dir = Path(settings.TG_DOWNLOAD_PATH)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.telegram_service = telegram_service

    def extract_video_url(self, text: str) -> Optional[str]:
        """从文本中提取视频URL"""
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        if match:
            actual_url = match.group()
            logger.info(f"提取到URL: {actual_url}")
            return actual_url
        else:
            logger.error(f"无法从文本提取视频URL: {text}")
            return None

    async def process_video(self, task_id: str, video_url: str) -> Dict[str, Any]:
        """处理视频的完整流程"""
        task = self.db.query(VideoProcessTask).filter(
            VideoProcessTask.id == task_id
        ).first()

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        try:
            # 更新状态为处理中
            task.status = VideoProcessTask.STATUS_PROCESSING
            self.db.commit()

            # 1. 下载内容 (优先使用 Telegram)
            logger.info(f"开始下载内容: {video_url}")
            
            # 使用 TelegramService 统一处理下载
            downloaded_files = await self.telegram_service.get_and_download_video(video_url)
            
            if not downloaded_files:
                raise Exception("内容下载失败: Telegram 返回空")
                
            logger.info(f"下载成功，共 {len(downloaded_files)} 个文件")
            
            # 逻辑分支：检查是否包含视频
            video_files = [f for f in downloaded_files if f.lower().endswith('.mp4')]
            
            if video_files:
                # 情况 1: 有视频，取第一个进行后续处理
                video_path = Path(video_files[0])
                logger.info(f"识别到视频文件，准备进入全流程: {video_path}")
                task.video_path = str(video_path)
                task.media_type = "video"
                task.original_url = video_url
                self.db.commit()
                
                # 继续后续流程
                # 2. 提取音频
                logger.info("开始提取音频")
                audio_path = await self._extract_audio(video_path)
                if not audio_path or not audio_path.exists():
                    raise Exception("音频提取失败")
                task.audio_path = str(audio_path)
                self.db.commit()

                # 3. 语音识别
                logger.info("开始语音识别")
                subtitle_text = await self._recognize_speech(audio_path)
                if not subtitle_text:
                    raise Exception("语音识别失败")
                task.subtitle_text = subtitle_text
                self.db.commit()

                # 4. AI总结
                logger.info("开始AI总结")
                ai_summary = await self._generate_summary(subtitle_text)
                if not ai_summary:
                    raise Exception("AI总结失败")
                task.ai_summary = ai_summary
                self.db.commit()

                # 5. 更新为完成
                task.status = VideoProcessTask.STATUS_COMPLETED
                self.db.commit()

                # 发送 Bark 通知
                try:
                    await self.bark_service.send_video_process_complete_notification(
                        device_key=self.bark_service.default_device_key,
                        task_id=task_id,
                        video_summary=ai_summary
                    )
                except Exception as bark_err:
                    logger.error(f"Bark通知发送失败: {bark_err}")

                return {
                    "success": True,
                    "task_id": task_id,
                    "video_path": str(video_path),
                    "audio_path": str(audio_path),
                    "subtitle_text": subtitle_text,
                    "ai_summary": ai_summary
                }
            else:
                # 情况 2: 只有图片，直接结束
                logger.info("未识别到视频文件，仅包含图片。流程结束。")
                task.video_path = str(downloaded_files[0])
                task.media_type = "image"
                task.download_urls = json.dumps(downloaded_files)
                task.status = VideoProcessTask.STATUS_COMPLETED
                self.db.commit()
                
                # 发送图片完成通知
                try:
                    await self.bark_service.send_notification(
                        title="内容下载完成 (图片)",
                        content=f"任务ID: {task_id}\n共下载 {len(downloaded_files)} 张图片。",
                        level="active"
                    )
                except Exception as bark_err:
                    logger.error(f"Bark通知发送失败: {bark_err}")

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "图片下载完成，流程结束",
                    "file_paths": downloaded_files
                }

        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            logger.error(f"[Task {task_id}] {error_msg}")
            if task:
                task.status = VideoProcessTask.STATUS_FAILED
                task.error_message = str(e)
                self.db.commit()
                try:
                    await self.bark_service.send_notification(
                        title="任务处理失败",
                        content=f"任务ID: {task_id}\n错误: {str(e)}",
                        level="timeSensitive"
                    )
                except: pass
            return {"success": False, "task_id": task_id, "error": str(e)}

    async def _extract_audio(self, video_path: Path) -> Optional[Path]:
        """使用ffmpeg提取音频"""
        try:
            if not shutil.which(self.ffmpeg_path):
                raise Exception(f"ffmpeg未找到: {self.ffmpeg_path}")
            audio_path = self.temp_dir / f"{video_path.stem}.mp3"
            cmd = [self.ffmpeg_path, "-i", str(video_path), "-vn", "-acodec", "mp3", "-ab", "192k", "-y", str(audio_path)]
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await process.communicate()
            return audio_path if audio_path.exists() else None
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return None

    async def _recognize_speech(self, audio_path: Path) -> Optional[str]:
        """语音识别"""
        try:
            ai_client = get_ai_client()
            return await ai_client.recognize_speech(audio_path)
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None

    async def _generate_summary(self, text: str) -> Optional[str]:
        """AI总结"""
        try:
            ai_client = get_ai_client()
            return await ai_client.summarize_text(text)
        except Exception as e:
            logger.error(f"AI总结失败: {e}")
            return None

    async def parse_video_url(self, video_url: str, user_id: str) -> Dict[str, Any]:
        """仅解析 URL 获取下载链接，不下载文件（如果是直接媒体则执行最小下载以提供链接）"""
        try:
            actual_url = self.extract_video_url(video_url)
            if not actual_url:
                return {"success": False, "error": "无法提取URL"}

            # 简单的路由逻辑
            target_bot = self.telegram_service.douyin_bot
            if "x.com" in actual_url.lower() or "twitter.com" in actual_url.lower():
                target_bot = self.telegram_service.x_bot

            logger.info(f"通过 Telegram 机器人 {target_bot} 解析链接: {actual_url}")
            
            # 使用 Telegram 获取链接
            urls, media_msgs = await self.telegram_service.get_video_url_from_bot(actual_url, target_bot=target_bot)
            
            download_urls = list(urls.values()) if urls else []
            
            # 如果 Bot 直接返回了媒体文件（如图片），下载并转换为本地链接
            if media_msgs:
                logger.info(f"Bot 直接返回了 {len(media_msgs)} 个媒体文件，转换为本地访问链接...")
                local_paths = await self.telegram_service.download_media(media_msgs)
                for path in local_paths:
                    filename = Path(path).name
                    # 构造本地访问链接 (使用配置中的前缀)
                    prefix = settings.MEDIA_URL_PREFIX.rstrip('/')
                    local_url = f"{prefix}/{filename}"
                    download_urls.append(local_url)
            
            return {
                "success": True,
                "download_urls": download_urls,
                "buttons": urls # 返回原始按钮文本和链接的映射
            }
        except Exception as e:
            logger.error(f"解析URL失败: {e}")
            return {"success": False, "error": str(e)}

    async def cleanup_temp_files(self, task_id: str):
        """清理临时文件"""
        try:
            for file_path in self.temp_dir.glob(f"{task_id}_*"):
                if file_path.is_file(): file_path.unlink()
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    def check_existing_task(self, video_url: str) -> Optional[VideoProcessTask]:
        """检查是否已存在处理记录"""
        actual_url = self.extract_video_url(video_url)
        if not actual_url: return None
        return self.db.query(VideoProcessTask).filter(
            VideoProcessTask.original_url == actual_url,
            VideoProcessTask.status == VideoProcessTask.STATUS_COMPLETED
        ).first()
