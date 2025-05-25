from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import gtd, rest_records
from app.core.config import settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    init_db()
    yield
    # 关闭时的清理工作（如果需要）


app = FastAPI(
    title="Z收集系统",
    description=
    "用于收集和管理用户休息数据的 API 系统\n\n认证方式：在请求头中添加 `Authorization: Bearer <token>`",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "docExpansion": "none",
    },
    lifespan=lifespan,
)

# 添加接口分组说明
app.openapi_tags = [{
    "name": "作息健康相关",
    "description": "作息记录管理",
}, {
    "name": "任务管理",
    "description": "GTD任务管理",
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
    tags=["作息健康相关"],
)

app.include_router(
    gtd.router,
    prefix="/api/v1/gtd-tasks",
    tags=["任务管理"],
)


@app.get("/", tags=["系统"])
async def root():
    """系统根路径，返回欢迎信息"""
    return {"message": "欢迎使用 Z收集系统 API"}
