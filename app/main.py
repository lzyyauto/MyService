from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import gtd, rest_records, video_process, telegram
from app.core.config import settings
from app.db.init_db import init_db
from app.services.telegram_service import telegram_service
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles


def setup_logging():
    """配置日志系统"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    # 设置第三方库的日志级别，减少干扰
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化日志
    setup_logging()
    # 启动时初始化数据库
    init_db()
    # 启动 Telegram 客户端
    await telegram_service.start()
    yield
    # 关闭时的清理工作
    await telegram_service.stop()


app = FastAPI(
    title="Z收集系统",
    description=
    "用于收集和管理用户休息数据的 API 系统\n\n认证方式：在请求头中添加 `Authorization: Bearer <token>`",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
    docs_url=None,  # 禁用默认 docs_url 以便手动重构
)

# 覆盖默认的 Swagger UI 路由，使用更稳定的 CDN
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Docs",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://lf3-cdn-tos.bytecdntp.com/cdn/expire-1-M/swagger-ui/4.15.5/swagger-ui-bundle.js",
        swagger_css_url="https://lf3-cdn-tos.bytecdntp.com/cdn/expire-1-M/swagger-ui/4.15.5/swagger-ui.min.css",
    )

# 添加接口分组说明
app.openapi_tags = [{
    "name": "作息健康相关",
    "description": "作息记录管理",
}, {
    "name": "任务管理",
    "description": "GTD任务管理",
}, {
    "name": "视频处理",
    "description": "视频下载、音频提取、语音识别、AI总结",
}, {
    "name": "Telegram 下载",
    "description": "通过 Telegram Bots 下载抖音、Twitter 视频",
}]

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载下载文件的静态目录
if not os.path.exists(settings.TG_DOWNLOAD_PATH):
    os.makedirs(settings.TG_DOWNLOAD_PATH)
app.mount("/downloads", StaticFiles(directory=settings.TG_DOWNLOAD_PATH), name="downloads")

# 注册路由
app.include_router(
    rest_records.router,
    prefix="/api/v1/rest-records",
    tags=["作息健康相关"],
)

app.include_router(
    gtd.router,
    prefix="/api/v1/gtd-tasks",
    tags=["任务管理"],
)

app.include_router(
    video_process.router,
    prefix="/api/v1/video-process",
    tags=["视频处理"],
)

app.include_router(
    telegram.router,
    prefix="/api/v1/telegram",
    tags=["Telegram 下载"],
)


@app.get("/", tags=["系统"])
async def root():
    """系统根路径，返回欢迎信息"""
    return {"message": "欢迎使用 Z收集系统 API"}
