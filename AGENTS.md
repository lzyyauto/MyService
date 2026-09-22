# AGENTS.md

这个文件为 Codex 在处理此代码库时提供指导。

## 项目概述

**Z 收集系统**用于收集和整理个人数据，由 FastAPI API 与独立 worker 组成。

当前有效业务范围：

- 记录睡眠和起床时间；
- 保存 WiFi、经纬度和城市等可选位置数据；
- 查询记录并生成年度总结、年度明细；
- 提供独立 React 前端容器；睡眠页按起床当天展示会话、热力日历和分页明细，运动页使用 `/sport` 深链；
- 可选同步 Notion，并在同步失败时通过 Bark 提醒。
- 接收 Notion 标准页面 JSON；映射保存业务类型、显示名称和说明，已映射运动数据写入
  `sport_record`；运动种类通过全局 `notion_select_option_mappings` 的选项 ID 映射为可读
  名称，未映射数据仍保存并同步。
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
- React 19 + TypeScript + Vite + Nginx

## 目录结构

```text
app/
├── api/v1/endpoints/
│   ├── rest_records.py   # 当前睡眠业务 API
│   ├── notion_ingest.py  # 认证的 Notion 页面采集与映射 API
│   ├── public_request_dump.py # 可选公开调试接收器，默认不注册
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
│   ├── notion_ingest.py  # 严格业务 mapper
│   ├── telegram.py       # 已废弃
│   └── video_processor.py # 已废弃
└── utils/
    └── ai_client.py      # 已废弃
app/workers/
├── feishu_inspiration.py # 飞书长连接独立进程入口
└── notion_delivery.py    # Notion 持久化投递队列独立进程入口
frontend/                 # 睡眠与运动看板，独立构建并由 Nginx 提供
alembic/                  # 历史迁移，不得因功能废弃而改写
tests/                    # 自动化测试
├── unit/                 # 无 Docker、无外部服务的单元测试
└── functional/           # 一次性 PostgreSQL、真实 HTTP 与本地外部服务替身
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

# 运行 Notion 投递 worker
uv run python -m app.workers.notion_delivery

# 测试与检查
./scripts/test.sh unit
./scripts/test.sh functional
./scripts/test.sh all
uv run python -m compileall -q app alembic scripts tests
uv run alembic heads

# 前端
cd frontend
npm ci
npm run test
npm run build

# Docker 部署（只拉取 GitHub Actions 发布的 Docker Hub 镜像；不在部署机编译源码）
docker compose pull
docker compose up -d --wait
docker compose --profile inspiration pull
docker compose --profile inspiration up -d --wait
docker compose -f docker-compose.external-postgres.yml pull
docker compose -f docker-compose.external-postgres.yml up -d --wait
```

数据库命令：

```bash
uv run python -m app.db.migration_baseline
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
- `GET /api/v1/rest-records/sessions`
- `DELETE /api/v1/rest-records/sessions/{anchor_record_id}`
- `GET /api/v1/sport-records/`
- `POST /api/v1/notion-ingest/`
- `PUT /api/v1/notion-ingest/mappings/{database_id}`
- `GET /api/v1/notion-ingest/mappings`

当且仅当 `ENABLE_PUBLIC_REQUEST_DUMP=true` 时，另开放无鉴权的调试端点：

- `POST /api/v1/public-request-dump/`

它会回显并记录完整请求内容（包括可能的敏感数据），只可在受控网络短时使用；默认关闭时
必须保持 `404`。

根路径和 API 文档不要求认证。

## 测试规则

- 单元测试位于 `tests/unit/`，不得访问网络、真实数据库或用户数据。
- 功能测试位于 `tests/functional/`，只能使用 `docker-compose.functional.yml`
  创建的一次性 PostgreSQL 和本地外部服务替身。
- 默认测试不得连接真实飞书、Notion 或 Bark。
- 统一入口是 `scripts/test.sh`；`unit` 是本地第一道验证，`functional` 验证真实
  HTTP/PostgreSQL 链路，`all` 依次执行两者。
- 当前活跃模块单元测试覆盖率门槛为 75%；废弃兼容函数不计入门槛。
- 功能测试结束后必须清理容器和数据；仅调试时允许使用 `KEEP_TEST_STACK=1`。
- 功能测试会在一次性空 PostgreSQL 上先执行 `python -m app.db.migration_baseline`，再执行
  `alembic upgrade head` 和真实 HTTP 链路验证；
  这不等于已验证有历史数据的生产库升级／回退。生产升级前仍须备份并检查 `alembic current`。

长期开发入口：

- `docs/项目开发指南/README.md`：当前能力、边界、技术债和后续路线；
- `docs/项目开发指南/后端技术路线与开发规范.md`：分层职责、代码规范和功能开发路径；
- `docs/项目开发指南/测试规范.md`：测试分层、隔离规则和按改动类型选择验证。

飞书灵感采集通过长连接接收事件，不注册 HTTP 路由。它必须作为独立进程运行，
不得加入 FastAPI lifespan，以免 Uvicorn 重载或多进程造成重复连接。

睡眠会话不是新的数据库表：它由休息事件投影得到。完整会话固定按起床当天归属；单侧
错误事件按现存事件当天展示且不参与统计。删除会话会删除本地配对事件，但不会删除 Notion 副本。

快捷指令可省略 `rest_type` 保持一键打卡：显式类型始终优先；未指定时使用上一条
`rest_time`，间隔严格大于 12 小时则按北京时间 21:00（含）至次日 05:00（不含）重锚定为
睡眠，其他时段重锚定为起床；其余间隔按上一条类型切换。未指定类型且距上一条不足 2 分钟
必须返回 `409`，不得写入数据库或触发 Notion 同步。完整规则见 `docs/睡眠打卡自动纠偏/README.md`。

运动 `duration` 的业务单位为分钟。“其他”且时长为 2 分钟的是红色个人运动标记，时长为
30 分钟的是黄色特殊标记；API 必须以独立布尔字段返回两者，日历和明细均不得只依赖颜色。
早期文档曾误写为小时；既有数据只能在备份并核对原始载荷后另行修正，不得自动批量换算。
`sport_record.detail` 与 `detail2` 仅用于保留 `sport_data` 历史附加文本；不得在当前
API、看板或 Notion 映射业务中使用或展示。

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
- 公开调试接收器：`ENABLE_PUBLIC_REQUEST_DUMP`（默认 `false`）
- 数据库：`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`POSTGRES_HOST`、`POSTGRES_PORT`
- 部署镜像：`MYSERVICE_BACKEND_IMAGE`、`MYSERVICE_FRONTEND_IMAGE`、`MYSERVICE_IMAGE_TAG`
- Notion：`NOTION_TOKEN`、`NOTION_SLEEP_DATABASE_ID`、`NOTION_WAKE_DATABASE_ID`
- Notion 投递：`NOTION_DELIVERY_POLL_INTERVAL_SECONDS`、
  `NOTION_DELIVERY_RETRY_DELAY_SECONDS`、`NOTION_DELIVERY_LEASE_SECONDS`
- Bark：`BARK_BASE_URL`、`BARK_DEFAULT_DEVICE_KEY`
- 飞书灵感：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_URL`、
  `INSPIRATION_DOC_PATH`
- 日志与 Docker 持久化配置

GTD、Telegram 下载、视频和旧 AI 配置字段仅在 `Settings` 中兼容旧 `.env`，
主应用不得读取。

灵感文件默认为 `data/inspirations.md`，`data/` 不纳入 Git，部署时必须持久化和备份。
完整决策见 `docs/飞书灵感采集整合/README.md`。

## 已知问题

1. Notion 统一采集迁移已合并为一个 head。生产升级前先检查 `alembic current`、完成
   数据库备份；不得直接重置有数据的数据库。
   早期 `create_all` 数据库若表结构已在当前 head、但版本标记落后，必须先备份并人工核对后使用
   `alembic stamp` 对齐；不得因 `DuplicateTable` 自动跳过或删除既有表，详见
   `docs/容器化部署与本地运行/README.md`。
2. PostgreSQL `zrest` 存在 collation 版本提示，处理前必须备份并评估索引重建。
3. 部分 Pydantic Schema 仍使用 v1 兼容写法，会产生弃用警告。
4. Docker daemon 未运行时只能执行单元测试和本地飞书管道测试，无法执行完整功能测试。

## 协作规则

1. 全程使用中文沟通。
2. 新需求在 `docs/` 下创建对应的中文需求目录，文档统一存放其中。
3. 需求设计流程遵循 `docs/SETP.md`。
4. 完成需求后更新本文件，保证信息准确。
5. 保留用户已有数据和无关改动；数据库与外部服务写入必须谨慎。
