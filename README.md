# Z收集系统

基于FastAPI构建的多功能RESTful API系统，用于收集和管理用户数据。

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
| 认证授权 | JWT (python-jose) + bcrypt |
| 数据验证 | Pydantic 2.5.2 |
| 任务队列 | FastAPI BackgroundTasks |
| 数据库迁移 | Alembic 1.12.1 |
| 测试框架 | pytest + pytest-asyncio |
| 外部集成 | Notion API、Bark通知 |
| 部署 | Docker + Docker Compose |

## 🚀 快速开始

### 环境要求
- Python 3.9+
- PostgreSQL 14+
- Docker (可选)

### 安装启动

**方式一：Docker Compose**
```bash
docker-compose up -d
```

**方式二：本地开发**
```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env

# 启动服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
- `GET /api/v1/gtd-tasks/` - 获取任务列表

### 视频处理
- `POST /api/v1/video-process/` - 提交视频处理任务
- `GET /api/v1/video-process/{task_id}` - 查询处理状态

## 🔐 认证方式

所有API请求需要在Header中添加：
```
Authorization: Bearer <token>
```

## 📁 项目结构

```
app/
├── api/v1/endpoints/      # API路由
│   ├── rest_records.py   # 作息记录
│   ├── gtd.py           # GTD任务
│   └── video_process.py  # 视频处理
├── core/                 # 核心模块
│   ├── config.py        # 配置管理
│   ├── security.py      # 认证授权
│   └── services/        # 外部服务
│       ├── bark_service.py     # Bark通知
│       └── notion_service.py   # Notion集成
├── models/              # 数据模型
│   ├── user.py         # 用户模型
│   ├── rest_record.py  # 作息记录
│   ├── gtd_task.py     # GTD任务
│   └── video_process_task.py # 视频任务
└── schemas/             # 数据验证
```

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行覆盖率测试
pytest --cov=app

# 运行特定测试
pytest tests/test_video_processor_service.py
```

## ⚙️ 配置说明

主要环境变量（`.env`）：

```env
# 数据库
POSTGRES_SERVER=localhost
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

# 视频处理
THIRD_PARTY_DOUYIN_API_URL=http://localhost:8088/api/hybrid/video_data
```

## 📄 许可证

MIT License
