# Z 收集系统

基于 FastAPI 的个人数据收集 API，提供作息记录、GTD、视频处理和通知能力。

## 🌟 主要功能

### 📊 作息健康管理
- 睡眠/起床时间记录
- 地理位置和WiFi信息追踪
- 数据自动同步到Notion数据库

### ✅ GTD任务管理
- 任务创建、状态管理
- Todo / 进行中 / 已完成 / 已取消状态
- 任务同步到Notion（可选）

### 🎬 视频智能处理
- 抖音视频链接解析和下载
- 无水印视频提取
- 音频分离和提取
- AI语音识别转文字
- 智能内容总结

### 🔔 通知服务
- Bark推送通知
- 错误告警和状态提醒

## 🛠 技术栈

| 领域 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.104.1 |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 |
| 认证授权 | HTTP Bearer + 数据库 API Key |
| 数据验证 | Pydantic 2.5.2 |
| 任务队列 | FastAPI BackgroundTasks |
| 数据库迁移 | Alembic 1.12.1 |
| 测试框架 | pytest + pytest-asyncio |
| 外部集成 | Notion API、Bark通知 |
| 部署 | Docker + Docker Compose |

## 🚀 快速开始

### 环境要求
- Python 3.11
- uv 0.5.24+
- PostgreSQL 14+
- Docker (可选)

### 安装启动

**方式一：Docker Compose**
```bash
docker compose up --build -d
```

**方式二：本地开发**
```bash
# 按 uv.lock 安装依赖；首次执行会自动创建项目根目录的 .venv
uv sync --locked

# 配置环境变量
cp .env.example .env

# 启动服务
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 常用检查

```bash
uv run pytest -q
uv run python -m compileall -q app alembic
uv run alembic heads
```

`.venv/` 由 uv 管理并被 Git 忽略。如需进入虚拟环境，可执行
`source .venv/bin/activate`；通常直接使用 `uv run <命令>` 更简单。

依赖统一维护在 `pyproject.toml`，解析结果锁定在 `uv.lock`：

```bash
uv add <运行依赖>
uv add --dev <开发依赖>
uv remove <依赖>
uv lock
```

### API文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json

## 📝 API端点概览

### 作息记录
- `POST /api/v1/rest-records/` - 创建作息记录
- `GET /api/v1/rest-records/` - 获取作息记录列表

### GTD任务
- `POST /api/v1/gtd-tasks/` - 创建任务

### 视频处理
- `POST /api/v1/video-process/` - 提交视频处理任务
- `GET /api/v1/video-process/{task_id}` - 查询处理状态
- `POST /api/v1/video-process/parse-url` - 仅解析视频URL（快速获取下载链接）

## 🔐 认证方式

除根路径和 API 文档外，业务请求需要在 Header 中添加：
```
Authorization: Bearer <token>
```

## 📁 项目结构

```
app/
├── api/v1/endpoints/    # HTTP 路由
├── core/                # 配置与安全等横切能力
├── db/                  # 引擎、会话与初始化
├── models/              # SQLAlchemy 模型
├── schemas/             # Pydantic 模型
├── services/            # 业务服务与外部集成
└── utils/               # 通用工具
alembic/                 # 数据库迁移
scripts/                 # 人工运维脚本
tests/                   # 自动化测试
docs/                    # 中文设计与变更文档
temp/                    # 运行时下载文件（不纳入 Git）
pyproject.toml           # 项目元数据与直接依赖
uv.lock                  # 完整锁定的依赖图
```

## ⚙️ 配置说明

主要环境变量（`.env`）：

```env
# 数据库
POSTGRES_HOST=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=myservice

# Notion集成
NOTION_TOKEN=secret_xxx
NOTION_SLEEP_DATABASE_ID=xxx
NOTION_WAKE_DATABASE_ID=xxx
NOTION_GTD_DATABASE_ID=xxx

# Bark通知
BARK_BASE_URL=https://api.day.app
BARK_DEFAULT_DEVICE_KEY=xxx

# 视频处理与 Telegram
FFMPEG_PATH=/opt/homebrew/bin/ffmpeg
TG_DOWNLOAD_PATH=temp/telegram_downloads/
TG_API_ID=xxx
TG_API_HASH=xxx
TG_SESSION=xxx
```

## 📄 许可证

MIT License
