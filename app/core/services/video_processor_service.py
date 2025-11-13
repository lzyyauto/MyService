"""
视频处理服务
整合视频下载、音频提取、语音识别、AI总结等全部功能
使用第三方API服务下载抖音视频
"""

import asyncio
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import aiohttp
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.services.bark_service import BarkService
from app.utils.ai_client import get_ai_client
from app.models.video_process_task import VideoProcessTask

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
        self.temp_dir = Path(settings.VIDEO_PROCESSING_TEMP_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.api_url = settings.THIRD_PARTY_DOUYIN_API_URL
        logger.info(f"使用第三方API服务: {self.api_url}")

    def extract_video_url(self, text: str) -> Optional[str]:
        """
        从文本中提取视频URL

        Args:
            text: 包含视频URL的文本

        Returns:
            视频URL，提取失败返回None
        """
        # 从输入中提取真正的URL
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        if match:
            actual_url = match.group()
            logger.info(f"提取到URL: {actual_url}")
            return actual_url
        else:
            logger.error(f"无法从文本提取视频URL: {text}")
            return None

    async def fetch_video_info(self, video_url: str) -> Optional[Dict]:
        """
        使用第三方API获取视频信息

        Args:
            video_url: 视频URL

        Returns:
            视频信息字典，如果获取失败返回None
        """
        try:
            # 构建第三方API请求URL（使用minimal=true获取简化结构）
            api_url = f"{self.api_url}?url={quote(video_url)}&minimal=true"
            logger.info(f"调用第三方API: {api_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=30) as response:
                    logger.info(f"第三方API响应状态: {response.status}")

                    if response.status != 200:
                        logger.error(f"第三方API请求失败，状态码: {response.status}")
                        return None

                    text = await response.text()
                    if not text:
                        logger.error("第三方API响应为空")
                        return None

                    try:
                        data = json.loads(text)
                        logger.info(f"第三方API返回数据: {json.dumps(data, indent=2)}")

                        # 检查响应码
                        if data.get('code') != 200:
                            logger.error(f"第三方API返回错误码: {data.get('code')}")
                            return None

                        # 返回数据部分
                        video_data = data.get('data')
                        if video_data:
                            logger.info("第三方API成功获取视频信息")
                            return video_data
                        else:
                            logger.error("第三方API返回的数据中没有 data 字段")

                    except json.JSONDecodeError as e:
                        logger.error(f"第三方API JSON解析失败: {e}")
                        logger.error(f"原始响应内容: {text}")
                        return None

        except Exception as e:
            logger.error(f"第三方API获取视频信息失败: {e}")

        return None

    def get_video_url(self, video_info: Dict) -> Optional[str]:
        """
        从视频信息中获取视频URL
        基于simplified结构（minimal=true）

        Args:
            video_info: 视频信息字典

        Returns:
            视频URL，如果获取失败返回None
        """
        try:
            # 从第三方API响应中提取视频URL
            # 简化结构中，URL在 data.video_data.nwm_video_url_HQ 或 nwm_video_url 中
            video_data = video_info.get('video_data', {})

            # 优先使用无水印高清链接
            video_url = video_data.get('nwm_video_url_HQ') or video_data.get('nwm_video_url')

            if video_url:
                logger.info(f"从第三方API获取到视频URL: {video_url}")
                return video_url

            logger.error("第三方API返回的数据中没有找到视频URL")
            return None

        except Exception as e:
            logger.error(f"获取视频URL失败: {e}")
            return None

    async def download_file(self, url: str, save_path: Path) -> bool:
        """
        下载文件

        Args:
            url: 文件URL
            save_path: 保存路径

        Returns:
            下载成功返回True，失败返回False
        """
        try:
            if save_path.exists():
                logger.info(f"文件已存在，跳过: {save_path.name}")
                return True

            # 添加请求头以绕过访问限制
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=60) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        logger.info(f"文件下载成功: {save_path}")
                        return True
                    else:
                        logger.error(f"下载失败，状态码: {response.status}")
                        logger.error(f"响应头: {response.headers}")
                        return False

        except Exception as e:
            logger.error(f"下载文件失败 {url}: {e}")
            return False

    async def download_video(self, video_url: str) -> Optional[Path]:
        """
        下载视频的完整流程

        Args:
            video_url: 视频URL（可能包含其他文字）

        Returns:
            下载的视频文件路径，失败返回None
        """
        try:
            # 1. 提取视频URL
            actual_url = self.extract_video_url(video_url)
            if not actual_url:
                logger.error(f"无法从URL提取视频URL: {video_url}")
                return None

            logger.info(f"使用第三方API下载视频: {actual_url}")

            # 2. 获取视频信息
            video_info = await self.fetch_video_info(actual_url)
            if not video_info:
                logger.error(f"无法获取视频信息")
                return None

            # 3. 获取视频URL和视频ID
            video_download_url = self.get_video_url(video_info)
            if not video_download_url:
                logger.error(f"无法获取视频下载URL")
                return None

            # 4. 确定视频文件名（优先使用第三方API返回的aweme_id）
            # 从第三方API响应中提取aweme_id
            video_id = video_info.get('aweme_id')
            if not video_id:
                # 备用：从URL中提取
                video_id = actual_url.split('/')[-1].split('?')[0]

            # 如果还是空的，使用时间戳
            if not video_id or video_id == '':
                import time
                video_id = f"video_{int(time.time())}"

            logger.info(f"使用视频ID作为文件名: {video_id}")
            video_path = self.temp_dir / f"{video_id}.mp4"

            success = await self.download_file(video_download_url, video_path)
            if success:
                logger.info(f"视频下载完成: {video_path}")
                return video_path
            else:
                logger.error(f"视频下载失败")
                return None

        except Exception as e:
            logger.error(f"下载视频异常: {e}")
            return None

    async def process_video(self, task_id: str, video_url: str) -> Dict[str, Any]:
        """
        处理视频的完整流程

        Args:
            task_id: 任务ID
            video_url: 视频URL

        Returns:
            处理结果字典
        """
        task = self.db.query(VideoProcessTask).filter(
            VideoProcessTask.id == task_id
        ).first()

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        try:
            # 更新状态为处理中
            task.status = VideoProcessTask.STATUS_PROCESSING
            self.db.commit()

            # 1. 下载视频
            logger.info(f"开始下载视频: {video_url}")
            video_path = await self.download_video(video_url)

            if not video_path or not video_path.exists():
                raise Exception("视频下载失败")

            task.video_path = str(video_path)
            task.original_url = video_url
            self.db.commit()

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
                raise Exception("语音识别失败，返回空结果")

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

            logger.info(f"视频处理完成: {task_id}")

            # 发送Bark通知 - 任务完成
            try:
                await self.bark_service.send_video_process_complete_notification(
                    device_key=self.bark_service.default_device_key,
                    task_id=task_id,
                    video_summary=ai_summary
                )
                logger.info(f"Bark通知已发送 - 任务完成: {task_id}")
            except Exception as bark_error:
                logger.error(f"Bark通知发送失败: {bark_error}")

            return {
                "success": True,
                "task_id": task_id,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "subtitle_text": subtitle_text,
                "ai_summary": ai_summary
            }

        except Exception as e:
            error_msg = f"视频处理失败: {str(e)}"
            logger.error(f"[Task {task_id}] {error_msg}")

            if task:
                task.status = VideoProcessTask.STATUS_FAILED
                task.error_message = str(e)
                self.db.commit()

                # 发送Bark通知
                try:
                    await self.bark_service.send_notification(
                        title="视频处理失败",
                        content=f"任务ID: {task_id}\n错误: {str(e)}",
                        level="timeSensitive"
                    )
                except Exception as bark_error:
                    logger.error(f"Bark通知发送失败: {bark_error}")

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e)
            }

    async def _extract_audio(self, video_path: Path) -> Optional[Path]:
        """
        使用ffmpeg从视频中提取音频

        Args:
            video_path: 视频文件路径

        Returns:
            音频文件路径，失败返回None
        """
        try:
            # 检查ffmpeg是否可用
            if not shutil.which(self.ffmpeg_path):
                raise Exception(f"ffmpeg未找到: {self.ffmpeg_path}")

            # 输出音频路径
            audio_path = self.temp_dir / f"{video_path.stem}.mp3"

            # 构建ffmpeg命令
            cmd = [
                self.ffmpeg_path,
                "-i", str(video_path),  # 输入视频
                "-vn",                  # 不包含视频
                "-acodec", "mp3",       # 使用MP3编码
                "-ab", "192k",          # 音频比特率
                "-y",                   # 覆盖输出文件
                str(audio_path)
            ]

            logger.info(f"执行ffmpeg命令: {' '.join(cmd)}")

            # 执行命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "未知错误"
                logger.error(f"ffmpeg执行失败: {error_msg}")
                raise Exception(f"ffmpeg执行失败: {error_msg}")

            # 检查输出文件
            if not audio_path.exists():
                raise Exception("ffmpeg未生成音频文件")

            logger.info(f"音频提取成功: {audio_path}")
            return audio_path

        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return None

    async def _recognize_speech(self, audio_path: Path) -> Optional[str]:
        """
        语音识别 - 将音频转换为文字

        Args:
            audio_path: 音频文件路径

        Returns:
            识别出的文字，失败返回None
        """
        try:
            # 获取AI客户端
            ai_client = get_ai_client()

            # 语音识别
            subtitle_text = await ai_client.recognize_speech(audio_path)

            if subtitle_text and subtitle_text.strip():
                logger.info(f"语音识别成功，文字长度: {len(subtitle_text)}")
                return subtitle_text.strip()
            else:
                logger.warning("语音识别返回空结果")
                return None

        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            raise

    async def _generate_summary(self, text: str) -> Optional[str]:
        """
        AI总结 - 对字幕进行总结和精简

        Args:
            text: 字幕文字

        Returns:
            总结结果，失败返回None
        """
        try:
            # 获取AI客户端
            ai_client = get_ai_client()

            # 文本总结
            summary = await ai_client.summarize_text(text)

            if summary and summary.strip():
                logger.info(f"AI总结成功，长度: {len(summary)}")
                return summary.strip()
            else:
                logger.warning("AI总结返回空结果")
                return None

        except Exception as e:
            logger.error(f"AI总结失败: {e}")
            raise

    async def cleanup_temp_files(self, task_id: str):
        """
        清理临时文件

        Args:
            task_id: 任务ID
        """
        try:
            # 查找该任务相关的临时文件
            for file_path in self.temp_dir.glob(f"{task_id}_*"):
                if file_path.is_file():
                    file_path.unlink()
                    logger.info(f"已删除临时文件: {file_path}")

            # 查找包含任务ID的子目录中的文件
            for subdir in self.temp_dir.glob("*/"):
                if subdir.is_dir():
                    for file_path in subdir.glob(f"{task_id}_*"):
                        if file_path.is_file():
                            file_path.unlink()
                            logger.info(f"已删除临时文件: {file_path}")

        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    def check_existing_task(self, video_url: str) -> Optional[VideoProcessTask]:
        """
        检查是否已存在处理记录（去重）

        Args:
            video_url: 视频URL

        Returns:
            已存在的任务，如果不存在返回None
        """
        # 提取视频URL
        video_url_extracted = self.extract_video_url(video_url)

        if not video_url_extracted:
            return None

        # 查找相同视频URL的已完成任务
        task = self.db.query(VideoProcessTask).filter(
            VideoProcessTask.original_url == video_url_extracted,
            VideoProcessTask.status == VideoProcessTask.STATUS_COMPLETED
        ).first()

        return task

    async def parse_video_url(self, video_url: str, user_id: str) -> Dict[str, Any]:
        """
        解析视频URL，支持视频、图片、Live Photo三种类型
        成功后创建任务记录

        Args:
            video_url: 视频URL（可能包含其他文字）
            user_id: 用户ID

        Returns:
            解析结果字典，包含媒体类型和下载链接
        """
        try:
            # 1. 提取视频URL
            actual_url = self.extract_video_url(video_url)
            if not actual_url:
                return {
                    "success": False,
                    "error": "无法从输入中提取URL"
                }

            logger.info(f"解析URL: {actual_url}")

            # 2. 获取视频信息
            video_info = await self.fetch_video_info(actual_url)
            if not video_info:
                return {
                    "success": False,
                    "error": "无法获取视频信息"
                }

            # 3. 检测媒体类型并提取下载链接
            media_type = self.detect_media_type(video_info)
            download_urls = self.extract_download_urls(video_info, media_type)

            if not download_urls:
                return {
                    "success": False,
                    "error": f"无法提取{media_type}的下载链接"
                }

            # 4. 提取基本信息
            aweme_id = video_info.get('aweme_id', '')
            desc = video_info.get('desc', '')
            author = video_info.get('author', {})
            nickname = author.get('nickname', '') if author else ''

            logger.info(f"成功解析{media_type}，提取到{len(download_urls)}个下载链接")

            # 5. 创建任务记录
            try:
                task = VideoProcessTask(
                    user_id=user_id,
                    task_type=VideoProcessTask.TASK_TYPE_PARSE,
                    original_url=actual_url,
                    aweme_id=aweme_id,
                    media_type=media_type,
                    desc=desc,
                    author=nickname,
                    download_urls=json.dumps(download_urls),
                    status=VideoProcessTask.STATUS_PARSED
                )
                self.db.add(task)
                self.db.commit()
                logger.info(f"创建解析任务记录成功: {task.id}")
            except Exception as db_error:
                logger.error(f"创建任务记录失败: {db_error}")
                # 不影响主流程，继续返回解析结果

            return {
                "success": True,
                "media_type": media_type,
                "aweme_id": aweme_id,
                "desc": desc,
                "author": nickname,
                "download_urls": download_urls
            }

        except Exception as e:
            logger.error(f"解析URL失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def detect_media_type(self, video_info: Dict) -> str:
        """
        检测媒体类型（视频、图片、Live Photo）
        基于simplified结构（minimal=true）的type字段

        Args:
            video_info: 视频信息字典

        Returns:
            媒体类型: "video", "image", 或 "live_photo"
        """
        # 简化结构中，类型信息在data.type字段中
        media_type = video_info.get('type', '')

        # 检查是否是Live Photo（简化结构中可能标记为image但有特殊标识）
        if media_type == 'image':
            # 进一步检查是否有Live Photo标记
            # 简化结构中，Live Photo可能通过其他字段标识
            # 根据示例，Live Photo的图片列表可能包含视频信息
            image_data = video_info.get('image_data', {})
            no_watermark_list = image_data.get('no_watermark_image_list', [])

            # 如果图片数量较少且可能是Live Photo
            # 注意：简化结构中Live Photo可能与普通图片在字段上区别不明显
            # 这里暂时基于type判断，Live Photo处理在extract_download_urls中特殊处理
            if no_watermark_list:
                # 通过其他方式判断是否为Live Photo
                # 例如：检查是否有特殊的图片数量或格式
                # 简化结构中Live Photo可能需要通过返回的数据特征判断
                pass

        return media_type

    def extract_download_urls(self, video_info: Dict, media_type: str) -> List[str]:
        """
        根据媒体类型提取下载链接
        基于simplified结构（minimal=true）

        Args:
            video_info: 视频信息字典
            media_type: 媒体类型

        Returns:
            下载链接列表
        """
        download_urls = []

        if media_type == "video":
            # 视频：从 video_data.nwm_video_url_HQ 或 nwm_video_url 获取
            video_data = video_info.get('video_data', {})

            # 优先返回无水印高清链接
            if video_data.get('nwm_video_url_HQ'):
                download_urls.append(video_data['nwm_video_url_HQ'])

            # 如果没有高清，再返回标准无水印链接
            if video_data.get('nwm_video_url') and len(download_urls) < 2:
                download_urls.append(video_data['nwm_video_url'])

            # 如果需要更多备选，可以添加备用链接（但不推荐使用带水印的）
            # if video_data.get('wm_video_url_HQ') and len(download_urls) < 3:
            #     download_urls.append(video_data['wm_video_url_HQ'])

        elif media_type == "image":
            # 图片：从 image_data.no_watermark_image_list 获取无水印链接
            image_data = video_info.get('image_data', {})
            no_watermark_list = image_data.get('no_watermark_image_list', [])

            # 添加所有无水印链接（最多3个）
            download_urls = no_watermark_list[:3]

        elif media_type == "live_photo":
            # Live Photo：与图片相同处理，但需要标记
            # 注意：简化结构中Live Photo可能不包含视频部分
            # 如果需要视频部分，可能需要修改第三方API调用添加更多参数
            image_data = video_info.get('image_data', {})
            no_watermark_list = image_data.get('no_watermark_image_list', [])

            # 对于Live Photo，返回格式为 "image:URL"
            # 如果有视频信息，可能需要添加 "video:URL" 格式
            for url in no_watermark_list[:3]:
                download_urls.append(f"image:{url}")

            # 注意：简化结构可能不包含Live Photo的视频URL
            # 如果需要完整支持，可能需要：
            # 1. 修改API调用添加更多参数，或
            # 2. 根据类型特征额外调用API获取视频信息

        return download_urls
