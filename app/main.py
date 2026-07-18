from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import rest_records
from app.db.init_db import init_db
from fastapi.openapi.docs import get_swagger_ui_html


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
    setup_logging()
    init_db()
    yield


app = FastAPI(
    title="Z 收集系统",
    description=
    "用于收集个人数据的 API 系统\n\n认证方式：在请求头中添加 `Authorization: Bearer <api-key>`",
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
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )

# 添加接口分组说明
app.openapi_tags = [{
    "name": "睡眠记录",
    "description": "睡眠、起床记录与年度统计",
}]

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(
    rest_records.router,
    prefix="/api/v1/rest-records",
    tags=["睡眠记录"],
)


@app.get("/", tags=["系统"])
async def root():
    """系统根路径，返回欢迎信息"""
    return {"message": "欢迎使用 Z 收集系统 API"}
