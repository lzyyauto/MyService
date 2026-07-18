import os
import asyncio
import logging
from typing import Optional, List, Any, Dict
import aiohttp
from telethon import TelegramClient, events
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.api_id = settings.TG_API_ID
        self.api_hash = settings.TG_API_HASH
        self.session_str = settings.TG_SESSION
        self.download_path = settings.TG_DOWNLOAD_PATH
        self.douyin_bot = settings.TG_DOUYIN_BOT
        self.x_bot = settings.TG_X_BOT
        
        # 确保下载目录存在
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
            
        self.client = None

    async def start(self):
        if not self.api_id or not self.api_hash:
            logger.warning("Telegram API_ID or API_HASH not configured. Telegram module disabled.")
            return

        from telethon.sessions import StringSession
        self.client = TelegramClient(
            StringSession(self.session_str) if self.session_str else 'my_userbot',
            self.api_id,
            self.api_hash
        )

        try:
            await self.client.start()
            me = await self.client.get_me()
            logger.info(f"Telegram Userbot started as: {me.first_name} (@{me.username})")
        except Exception as e:
            logger.error(f"Failed to start Telegram client: {str(e)}")
            self.client = None

    async def stop(self):
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram Userbot disconnected.")

    async def get_video_url_from_bot(self, share_text: str, target_bot: str = "@DouYintg_bot", timeout: int = 45):
        """
        发送分享文本给指定的 Bot 并提取链接。
        支持视频和图片（含多图 Album）。
        :param share_text: 分享文本
        :param target_bot: 目标 Bot 的用户名
        :param timeout: 超时时间（秒）
        :return: (urls, media_messages) 元组。media_messages 可能是单条消息或消息列表。
        """
        if not self.client:
            logger.error("Telegram client not started.")
            return None, None

        urls = {}
        # 收集到的媒体消息列表
        received_messages = []
        event_received = asyncio.Event()

        @self.client.on(events.NewMessage(from_users=target_bot))
        async def handler(event):
            msg = event.message
            logger.info(f"Received message {msg.id} from {target_bot}")
            
            # 如果是文本消息带按钮
            if msg.reply_markup:
                # 记录按钮链接
                has_buttons = False
                for row in msg.reply_markup.rows:
                    for button in row.buttons:
                        if hasattr(button, 'url') and button.url:
                            urls[button.text] = button.url
                            has_buttons = True
                
                # 如果收到带链接的按钮，也触发 Event
                if has_buttons:
                    event_received.set()
            
            # 检查是否有媒体
            if msg.video or msg.photo:
                received_messages.append(msg)
                
                # 收到媒体，触发 Event
                event_received.set()

        try:
            logger.info(f"Sending message to {target_bot}...")
            await self.client.send_message(target_bot, share_text)

            try:
                # 等待第一条回复
                await asyncio.wait_for(event_received.wait(), timeout=timeout)
                # 稍微多等一会儿（0.5s-1s），给多图（Album）传输留出时间
                await asyncio.sleep(1.0) 
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for response from {target_bot}")
                return None, None
            finally:
                self.client.remove_event_handler(handler)

            # 返回所有收集到的媒体消息
            return urls, received_messages if received_messages else None
        except Exception as e:
            logger.error(f"Error in bot interaction: {str(e)}", exc_info=True)
            self.client.remove_event_handler(handler)
            return None, None

    async def download_media(self, messages):
        """
        从消息中下载媒体（视频或图片）
        :param messages: 单个 Telethon 消息对象或列表
        :return: 下载文件的路径列表
        """
        if not self.client:
            logger.error("Telegram client not started.")
            return []

        if not messages:
            return []

        if not isinstance(messages, list):
            messages = [messages]

        downloaded_paths = []
        try:
            for i, msg in enumerate(messages):
                if not (msg.video or msg.photo):
                    continue
                
                media_info = "video" if msg.video else "photo"
                logger.info(f"Downloading {media_info} from message {msg.id}...")
                
                path = await msg.download_media(file=self.download_path)
                if path:
                    logger.info(f"Media downloaded to: {path}")
                    downloaded_paths.append(path)
            
            return downloaded_paths
        except Exception as e:
            logger.error(f"Error downloading media: {str(e)}")
            return downloaded_paths

    async def download_from_url(self, url: str) -> Optional[str]:
        """
        通过 URL 下载文件（用于按钮链接回退）
        :param url: 文件下载链接
        :return: 下载后的本地文件路径，失败返回 None
        """
        try:
            logger.info(f"Downloading file from URL: {url}")
            
            # 从 URL 解析文件名，或者生成一个
            import uuid
            file_ext = ".mp4" # 默认为 mp4
            if "?" in url:
                base_url = url.split("?")[0]
            else:
                base_url = url
                
            if base_url.lower().endswith((".mp4", ".mov", ".avi")):
                file_ext = os.path.splitext(base_url)[1]
            elif "image" in url.lower() or "jpg" in url.lower() or "png" in url.lower():
                file_ext = ".jpg"
                
            filename = f"url_dl_{uuid.uuid4().hex[:8]}{file_ext}"
            save_path = os.path.join(self.download_path, filename)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=300) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        logger.info(f"File downloaded from URL to: {save_path}")
                        return save_path
                    else:
                        logger.error(f"Failed to download from URL. Status: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading from URL: {str(e)}")
            return None

    async def get_and_download_video(self, share_text: str, timeout: int = 45):
        """
        整合流程：自动路由 Bot -> 发送文本 -> 获取消息 -> 下载所有媒体文件
        如果 Bot 返回了按钮链接（针对大文件），则通过 URL 下载。
        :param share_text: 分享文本
        :param timeout: 超时时间
        :return: 下载后的文件路径列表 (List[str]) 或 None
        """
        # 简单的路由逻辑
        target_bot = self.douyin_bot
        if "x.com" in share_text.lower() or "twitter.com" in share_text.lower():
            target_bot = self.x_bot
            
        urls, media_msgs = await self.get_video_url_from_bot(share_text, target_bot, timeout)
        
        # 1. 优先尝试直接媒体消息
        if media_msgs:
            return await self.download_media(media_msgs)
        
        # 2. 如果没有媒体消息，检查按钮链接（针对超大视频的回退）
        if urls:
            logger.info(f"No direct media messages, checking available URLs: {list(urls.keys())}")
            # 优先级：无水印链接 > 高清下载 > 原始链接
            priority_keys = ["无水印链接", "高清下载", "原始链接", "高清下载 (无水印)"]
            
            for key in priority_keys:
                if key in urls:
                    logger.info(f"Found priority URL key: {key}")
                    dl_path = await self.download_from_url(urls[key])
                    if dl_path:
                        return [dl_path]
            
            # 如果没匹配到优先级 Key，但有唯一链接，也试一下
            if len(urls) == 1:
                url = list(urls.values())[0]
                dl_path = await self.download_from_url(url)
                if dl_path:
                    return [dl_path]

        logger.warning(f"Bot {target_bot} did not return any media or valid download links.")
        return None

telegram_service = TelegramService()
