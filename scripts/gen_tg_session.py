import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

# 获取环境变量或手动输入
API_ID = input("Enter your API_ID: ")
API_HASH = input("Enter your API_HASH: ")

async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        print("\n" + "="*50)
        print("YOUR TG_SESSION STRING (Save this to your .env file):")
        print("="*50)
        print(session_str)
        print("="*50 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
