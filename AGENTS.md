# AGENTS.md

这个文件为 Codex 在处理此代码库时提供指导。

## 项目概述

**Z 收集系统**用于收集和整理个人数据，由 FastAPI API 与独立 worker 组成。

当前有效业务范围：

- 记录睡眠和起床时间；
- 保存 WiFi、经纬度和城市等可选位置数据；
- 查询记录并生成年度总结、年度明细；
- 可选同步 Notion，并在同步失败时通过 Bark 提醒。
- 通过独立飞书 WebSocket worker 接收文本灵感，保存为 Markdown 并添加回执。

GTD、Telegram 下载、视频处理和相关 AI 能力已于 2026-07-19 废弃。代码、模型和
历史迁移暂时保留用于兼容，但主应用不得导入、注册或调用这些功能。

飞书灵感采集来自 `daily-claw`，属于新的有效功能，不等同于已废弃的 Telegram
下载功能。原项目没有实现 AI 文档整理；后续实现前不得把现有废弃 `ai_client.py`
当作灵感整理能力重新启用。

## 技术栈

- Python 3.11
- FastAPI 0.104.1
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- Pydantic 2.5.2
- HTTP Bearer + 数据库 API Key
- uv 依赖与虚拟环境管理

## 目录结构

```text
app/
├── api/v1/endpoints/
│   ├── rest_records.py   # 当前唯一业务 API
│   ├── gtd.py            # 已废弃，禁止注册
│   ├── telegram.py       # 已废弃，禁止注册
│   └── video_process.py  # 已废弃，禁止注册
├── core/                 # 配置、安全、废弃路由保护
├── db/                   # 数据库引擎、会话和初始化
├── models/               # 当前模型及兼容保留模型
├── schemas/              # 当前 Schema 及兼容保留 Schema
├── services/
│   ├── bark.py           # 睡眠同步失败提醒；含少量废弃兼容方法
│   ├── inspiration.py    # 飞书灵感解析、去重、落盘和回执
│   ├── notion.py         # 睡眠 Notion 同步；含废弃 GTD 方法
│   ├── telegram.py       # 已废弃
│   └── video_processor.py # 已废弃
└── utils/
    └── ai_client.py      # 已废弃
app/workers/
└── feishu_inspiration.py # 飞书长连接独立进程入口
alembic/                  # 历史迁移，不得因功能废弃而改写
tests/                    # 自动化测试
docs/                     # 中文需求与设计文档
```

## 常用命令

```bash
# 创建或同步根目录 .venv
uv sync --locked

# 运行服务
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行飞书灵感采集 worker
uv run python -m app.workers.feishu_inspiration

# 测试与检查
uv run pytest -q
uv run python -m compileall -q app alembic scripts tests
uv run alembic heads

# Docker
docker compose up --build -d
docker compose --profile inspiration up --build -d
```

数据库命令：

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "描述"
uv run alembic history
```

## 依赖管理

- 直接生产依赖维护在 `pyproject.toml` 的 `[project.dependencies]`。
- 测试依赖位于 `dev` 组，默认随本地 `uv sync` 安装。
- 废弃功能依赖位于 `legacy` 组，默认和 Docker 均不安装。
- `lark-oapi` 和 `requests` 是飞书灵感采集所需的有效生产依赖。
- 只有人工审查历史代码时才可执行 `uv sync --group legacy`；这不会重新启用接口。
- `uv.lock` 必须提交，`.venv/` 必须保持忽略。

## 当前 API

所有业务端点都需要：

```text
Authorization: Bearer <api-key>
```

FastAPI 仅开放：

- `POST /api/v1/rest-records/`
- `GET /api/v1/rest-records/`
- `GET /api/v1/rest-records/annual-summary/{year}`
- `GET /api/v1/rest-records/annual-summary/{year}/table`

根路径和 API 文档不要求认证。

飞书灵感采集通过长连接接收事件，不注册 HTTP 路由。它必须作为独立进程运行，
不得加入 FastAPI lifespan，以免 Uvicorn 重载或多进程造成重复连接。

## 废弃功能规则

- `/api/v1/gtd-tasks`、`/api/v1/telegram`、`/api/v1/video-process` 不得注册，
  正常请求结果应为 404。
- `/downloads` 静态挂载已移除。
- Telegram 客户端不得在应用生命周期中启动。
- 废弃端点统一使用 `app.core.deprecation.create_disabled_router`；即使误注册也必须返回
  `410 Gone`，不得执行原业务函数。
- 保留 `GtdTask`、`VideoProcessTask` 和历史 Alembic 迁移，避免破坏既有数据库。
- 不得在普通功能改造中删除旧表、改写已发布迁移或重新启用废弃入口。

完整决策见 `docs/睡眠单一职责改造/README.md`。

## 配置

当前有效配置：

- 应用：`APP_NAME`、`DEBUG`、`ENVIRONMENT`
- 数据库：`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`POSTGRES_HOST`、`POSTGRES_PORT`
- Notion：`NOTION_TOKEN`、`NOTION_SLEEP_DATABASE_ID`、`NOTION_WAKE_DATABASE_ID`
- Bark：`BARK_BASE_URL`、`BARK_DEFAULT_DEVICE_KEY`
- 飞书灵感：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_URL`、
  `INSPIRATION_DOC_PATH`
- 日志与 Docker 持久化配置

GTD、Telegram 下载、视频和旧 AI 配置字段仅在 `Settings` 中兼容旧 `.env`，
主应用不得读取。

灵感文件默认为 `data/inspirations.md`，`data/` 不纳入 Git，部署时必须持久化和备份。
完整决策见 `docs/飞书灵感采集整合/README.md`。

## 已知问题

1. Alembic 存在两个 head。先检查 `alembic current`，不得直接重置有数据的数据库。
2. PostgreSQL `zrest` 存在 collation 版本提示，处理前必须备份并评估索引重建。
3. 部分 Pydantic Schema 仍使用 v1 兼容写法，会产生弃用警告。

## 协作规则

1. 全程使用中文沟通。
2. 新需求在 `docs/` 下创建对应的中文需求目录，文档统一存放其中。
3. 需求设计流程遵循 `docs/SETP.md`。
4. 完成需求后更新本文件，保证信息准确。
5. 保留用户已有数据和无关改动；数据库与外部服务写入必须谨慎。
