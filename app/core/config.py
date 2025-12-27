import os
from pathlib import Path
from typing import Optional

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str
    DEBUG: bool
    ENVIRONMENT: str

    # 数据库配置
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"  # 本地开发默认使用localhost
    POSTGRES_PORT: int = 5432

    # 日志配置
    LOG_LEVEL: str
    LOG_FORMAT: str

    # Docker配置
    POSTGRES_DATA_DIR: str

    # Notion 配置
    NOTION_TOKEN: Optional[str] = None
    NOTION_SLEEP_DATABASE_ID: Optional[str] = None
    NOTION_WAKE_DATABASE_ID: Optional[str] = None
    NOTION_GTD_DATABASE_ID: Optional[str] = None

    # Bark 配置
    BARK_BASE_URL: str = "https://api.day.app"
    BARK_DEFAULT_DEVICE_KEY: Optional[str] = None

    # 视频处理配置
    FFMPEG_PATH: str = "ffmpeg"  # ffmpeg可执行文件路径
    MEDIA_URL_PREFIX: str = "/downloads"  # 媒体文件访问前缀

    # AI服务配置
    AI_PROVIDER: str = "siliconflow"  # AI服务提供商：siliconflow, openai
    SILICONFLOW_API_KEY: Optional[str] = None  # 硅基AI API密钥
    OPENAI_API_KEY: Optional[str] = None  # OpenAI API密钥
    AI_VOICE_MODEL: str = "FunAudioLLM/SenseVoiceSmall"  # 语音识别模型（硅基AI推荐）
    AI_SUMMARY_MODEL: str = "Qwen/QwQ-32B"  # 文本总结模型
    
    # Telegram 配置
    TG_API_ID: Optional[int] = None
    TG_API_HASH: Optional[str] = None
    TG_SESSION: Optional[str] = None
    TG_DOWNLOAD_PATH: str = "temp/telegram_downloads/"
    TG_DOUYIN_BOT: str = "@DouYintg_bot"
    TG_X_BOT: str = "@xx_video_download_bot"

    @property
    def DATABASE_URL(self) -> str:
        # 直接返回连接字符串，不使用 PostgresDsn
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True

        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            # 打印环境文件路径
            env_file = str(Path(__file__).parent.parent.parent / ".env")
            print(f"Looking for .env file at: {env_file}")
            print(f"File exists: {Path(env_file).exists()}")

            # 打印当前环境变量
            print("Current environment variables:")
            for key in [
                    "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                    "POSTGRES_HOST", "POSTGRES_PORT"
            ]:
                print(f"{key}: {os.getenv(key)}")

            return (
                init_settings,
                env_settings,
                file_secret_settings,
            )


settings = Settings()
