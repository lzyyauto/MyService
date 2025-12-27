import os
import asyncio
import logging
from telethon import TelegramClient, events
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.api_id = settings.TG_API_ID
        self.api_hash = settings.TG_API_HASH
        self.session_str = settings.TG_SESSION
        self.download_path = settings.TG_DOWNLOAD_PATH
        
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
                for row in msg.reply_markup.rows:
                    for button in row.buttons:
                        if hasattr(button, 'url') and button.url:
                            urls[button.text] = button.url
            
            # 检查是否有媒体
            if msg.video or msg.photo:
                received_messages.append(msg)
                
                # 如果是分组消息（Album），需要等待一段时间手机后续图片
                if msg.grouped_id:
                    # 每次收到带 grouped_id 的消息都重置等待，直到一段时间没新消息
                    # 这里简化处理：如果是 Album，我们稍微延迟 set event
                    # 或者我们可以通过检查 grouped_id 自动处理，但简单起见，我们先收集
                    pass
                
                # 只要收到带媒体的消息或带按钮的消息，我们先触发 Event
                # 对于多图，由于 Bot 通常很快发完，我们稍微后面加个 delay
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

    async def get_and_download_video(self, share_text: str, timeout: int = 45):
        """
        整合流程：自动路由 Bot -> 发送文本 -> 获取消息 -> 下载所有媒体文件
        :param share_text: 分享文本
        :param timeout: 超时时间
        :return: 下载后的文件路径列表 (List[str]) 或 None
        """
        # 简单的路由逻辑
        target_bot = "@DouYintg_bot"
        if "x.com" in share_text.lower() or "twitter.com" in share_text.lower():
            target_bot = "@xx_video_download_bot"
            
        urls, media_msgs = await self.get_video_url_from_bot(share_text, target_bot, timeout)
        
        if media_msgs:
            return await self.download_media(media_msgs)
        
        logger.warning(f"Bot {target_bot} did not return any direct media files.")
        return None

telegram_service = TelegramService()
