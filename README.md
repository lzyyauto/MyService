# Z 收集系统

用于记录个人数据的 Python 服务。睡眠/起床数据以本地 PostgreSQL 为准；Notion 是异步、
尽力而为的副本。现有 iOS 快捷指令可通过统一 Notion 采集接口提交标准页面载荷。

项目当前只有后端。FastAPI 和飞书 worker 是两个独立运行单元：前者负责睡眠数据，
后者负责把飞书文本灵感保存为 Markdown；任一侧故障不应阻塞另一侧。

## 📚 文档导航

- [项目现状与后续开发路线](docs/项目开发指南/README.md)
- [后端技术路线与开发规范](docs/项目开发指南/后端技术路线与开发规范.md)
- [测试规范](docs/项目开发指南/测试规范.md)
- [自动化测试体系实施记录](docs/自动化测试体系/README.md)
- [Notion 统一采集与运动映射](docs/Notion统一采集与运动映射/README.md)

## 🌟 主要功能

### 📊 睡眠记录
- 睡眠/起床时间记录
- 地理位置和WiFi信息追踪
- 数据自动同步到Notion数据库

### 🔔 通知服务
- Notion 同步失败时发送 Bark 提醒

### 🏃 Notion 统一采集
- 接收经系统 API Key 认证的 Notion 标准页面 JSON
- 已映射的运动数据库严格入库；未映射载荷仍持久化并异步投递 Notion
- 独立 worker 持久化重试三次，避免 Web 进程重启丢失同步任务

### 💡 灵感采集
- 通过飞书 WebSocket 长连接接收文本消息
- 追加到本地 Markdown，并给已保存消息添加回执
- 与 FastAPI 分进程运行，采集故障不影响睡眠 API

## 🛠 技术栈

| 领域 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.104.1 |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 |
| 认证授权 | HTTP Bearer + 数据库 API Key |
| 数据验证 | Pydantic 2.5.2 |
| 数据库迁移 | Alembic 1.12.1 |
| 测试框架 | pytest + pytest-asyncio |
| 外部集成 | Notion API、Bark通知 |
| 灵感采集 | 飞书开放平台 WebSocket |
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

# 另开终端启动飞书灵感采集（配置凭证后）
uv run python -m app.workers.feishu_inspiration
```

### 常用检查

```bash
# 默认：离线单元测试、编译检查和覆盖率门槛
./scripts/test.sh unit

# 一次性 PostgreSQL + 真实 HTTP 功能测试（需要 Docker）
./scripts/test.sh functional

# 依次执行全部验证
./scripts/test.sh all

# 底层命令仍可直接使用
uv run pytest -q
uv run python -m compileall -q app alembic
uv run alembic heads
```

功能测试不会读取正式数据库，也不会访问真实飞书、Notion 或 Bark。完整测试边界、
覆盖范围与已知限制见
[`docs/自动化测试体系/README.md`](docs/自动化测试体系/README.md)。

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

### 睡眠记录
- `POST /api/v1/rest-records/` - 创建作息记录
- `GET /api/v1/rest-records/` - 获取作息记录列表
- `GET /api/v1/rest-records/annual-summary/{year}` - 获取年度睡眠总结
- `GET /api/v1/rest-records/annual-summary/{year}/table` - 获取年度睡眠明细

### Notion 统一采集

- `POST /api/v1/notion-ingest/` - 接收 Notion 标准页面载荷，返回本地事件和投递任务 ID
- `PUT /api/v1/notion-ingest/mappings/{database_id}` - 建立或更新某个 database ID 的业务映射
- `GET /api/v1/notion-ingest/mappings` - 查询当前用户映射

运动 database 应先配置业务类型 `exercise`，并填写人类可读的显示名称和说明；服务端会选择
对应的字段规则。它要求 `运动类型`、`时长`、`记录时间`、`日期`、`月份`，可选 `城市`。
映射后的格式错误会返回 `422`，不会提交 Notion。未映射数据保留原始 JSON 并继续投递。详情和快捷指令改造见
[`docs/Notion统一采集与运动映射/README.md`](docs/Notion统一采集与运动映射/README.md)。
首次联调请按[本地手动测试操作手册](docs/Notion统一采集与运动映射/手动测试操作手册.md)执行，
该流程不依赖 Docker。

### 可选公开调试接收器

默认不注册。如需临时观察第三方 POST 请求，可在 `.env` 设置
`ENABLE_PUBLIC_REQUEST_DUMP=true` 并重启服务，然后请求：

- `POST /api/v1/public-request-dump/` - 无鉴权地记录并 JSON 回显请求头、查询参数和原始正文

该端点会记录和回显敏感 header、Cookie、签名及正文；仅应在受控网络短时开启。原始正文
以 Base64 无损返回，调试完成后将开关改回 `false` 并重启服务。

历史 GTD、Telegram 下载和视频处理仅为数据兼容保留，未开放 API。

飞书灵感采集不是 HTTP 接口。配置 `.env` 后单独启动 worker：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
INSPIRATION_DOC_PATH=data/inspirations.md

# 公开调试接收器（默认关闭）
ENABLE_PUBLIC_REQUEST_DUMP=false
```

不要直接复用 `daily-claw` Git 历史里的凭证：该仓库曾跟踪过 `.env`。请先在飞书
开放平台重置应用密钥，再把新密钥写入当前项目被 Git 忽略的 `.env`。

```bash
# 本地
uv run python -m app.workers.feishu_inspiration

# Docker；inspiration 是可选 profile
docker compose --profile inspiration up --build -d
```

采集结果默认保存在 `data/inspirations.md`。`data/` 是运行时数据目录，不纳入 Git。

## 🔐 认证方式

除根路径和 API 文档外，业务请求需要在 Header 中添加：
```
Authorization: Bearer <token>
```

API Key 来自数据库 `users.api_key`。项目当前没有公开的用户注册或 Key 签发接口，
首次使用前需通过受控的初始化或运维流程准备用户，不能直接使用示例或测试 Key。

创建记录示例：

```bash
curl -X POST http://localhost:8000/api/v1/rest-records/ \
  -H 'Authorization: Bearer <api-key>' \
  -H 'Content-Type: application/json' \
  -d '{"city":"上海","wifi_name":"Home"}'
```

省略 `rest_type` 时，第一条记录默认为睡眠，后续按当前用户上一条记录在睡眠和起床
之间自动切换。也可以显式传入 `0`（睡眠）或 `1`（起床）。

## 📁 项目结构

```
app/
├── api/v1/endpoints/    # HTTP 路由
├── core/                # 配置与安全等横切能力
├── db/                  # 引擎、会话与初始化
├── models/              # SQLAlchemy 模型
├── schemas/             # Pydantic 模型
├── services/            # 业务服务与外部集成（含灵感采集）
├── workers/             # 独立后台进程入口
└── utils/               # 通用工具
alembic/                 # 数据库迁移
scripts/                 # 人工运维脚本
tests/                   # 自动化测试
docs/                    # 中文设计与变更文档
temp/                    # 废弃功能遗留媒体（不纳入 Git）
data/                    # 灵感等运行时数据（不纳入 Git）
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
NOTION_DELIVERY_POLL_INTERVAL_SECONDS=5
NOTION_DELIVERY_RETRY_DELAY_SECONDS=30
NOTION_DELIVERY_LEASE_SECONDS=300

# Bark通知
BARK_BASE_URL=https://api.day.app
BARK_DEFAULT_DEVICE_KEY=xxx

# 飞书灵感采集
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
INSPIRATION_DOC_PATH=data/inspirations.md
```

灵感采集设计与限制见
[`docs/飞书灵感采集整合/README.md`](docs/飞书灵感采集整合/README.md)。

## 📄 许可证

MIT License
