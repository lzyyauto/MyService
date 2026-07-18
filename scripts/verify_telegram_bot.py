"""已废弃：Telegram 人工诊断脚本，不属于当前睡眠记录系统。"""

import asyncio
import logging
import os
import sys

# 将代码路径加入 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.telegram import telegram_service
from dotenv import load_dotenv

# 加载配置
load_dotenv()

async def test_bot_interaction():
    print("Initializing Telegram Client...")
    await telegram_service.start()
    
    if not telegram_service.client:
        print("Failed to start client. Please check TG_API_ID, TG_API_HASH, and TG_SESSION.")
        return

    share_text = "3.30 A@g.Ox 02/24 VYm:/ 街头采访！在上海谈恋爱难吗？ # 街头采访 # 谈恋爱  https://v.douyin.com/V2rGjQs3SOM/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    print(f"\nSending text to bot:\n{share_text}\n")
    
    print("Processing (Send -> Receive -> Download)...")
    video_path = await telegram_service.get_and_download_video(share_text)
    
    if video_path:
        print(f"\n✅ Success! Video downloaded to local path:")
        print(f"👉 {video_path}")
    else:
        print("\n❌ Failed to download video directly from the bot.")
        print("Checking if URLs were available instead...")
        urls, _ = await telegram_service.get_video_url_from_bot(share_text)
        if urls:
            print("Found these backup URLs:")
            for text, url in urls.items():
                print(f"[{text}]: {url}")

    await telegram_service.stop()

if __name__ == "__main__":
    # 配置基础日志显示
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_bot_interaction())
