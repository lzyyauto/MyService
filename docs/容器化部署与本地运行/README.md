# 本地运行与 Docker 部署

本项目有两种日常运行方式，以及两份互斥的 Docker 部署文件：

| 场景 | 数据库来源 | 使用的 Compose 文件 |
| --- | --- | --- |
| 本机直接运行 | 已有本机或远程 PostgreSQL | 不使用 Compose |
| Docker 自带数据库 | 本 Compose 创建并持久化 PostgreSQL | `docker-compose.yml`，只拉取镜像 |
| Docker 使用外部数据库 | 已有 PostgreSQL，Compose 不创建数据库 | `docker-compose.external-postgres.yml`，只拉取镜像 |

不要同时启动两份部署 Compose。它们的服务名和默认前端端口相同，且是两种数据库拓扑的替代方案。

## 镜像发布与版本选择

部署 Compose **没有** `build:` 字段，NAS 或服务器无需克隆源码，也不会在部署时运行 Python、npm
或 Vite 构建。`.github/workflows/build-push.yml` 会在推送 `main`、推送 `v*` 版本标签，或手动运行时，
构建并发布公开 Docker Hub 多架构镜像：

- `lzyyauto/myservice`：迁移、API 和两个 worker 共用；
- `lzyyauto/myservice-frontend`：静态前端与 Nginx；
- 同一提交会获得 `sha-<短 SHA>` 标签；`main` 额外获得 `latest`，版本标签保留 `v*` 标签。

Docker Hub 仓库是公开的，部署机不需要登录。生产环境应在 `.env` 固定同一提交的 SHA 标签，避免
`latest` 在下一次发布后悄然变化：

```dotenv
MYSERVICE_BACKEND_IMAGE=lzyyauto/myservice
MYSERVICE_FRONTEND_IMAGE=lzyyauto/myservice-frontend
MYSERVICE_IMAGE_TAG=sha-abcdef0
```

这里的 `sha-abcdef0` 以对应 GitHub Actions 发布日志显示的实际标签为准。开发者可以在任意有源码的
机器提交代码；构建由 GitHub Actions 完成，部署机只需要 Compose 文件、`.env` 和需要持久化的 `data/`。

## 1. 本机直接运行

适用于开发、调试和已有 PostgreSQL 的场景；不需要 Docker。

1. 从 `.env.example` 创建 `.env`，填写真实 PostgreSQL 地址和凭证。这里的
   `POSTGRES_HOST` 必须是本机地址或已有数据库地址，不能写 `db`。
2. 安装后端与前端依赖、应用迁移，再分别启动两个进程：

```bash
uv sync --locked
uv run python -m app.db.migration_baseline
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 另开终端
cd frontend
npm ci
npm run dev
```

访问睡眠页 <http://localhost:3000/>、运动页 <http://localhost:3000/sport>；前端开发服务器会把
`/api/` 代理到 `http://127.0.0.1:8000`。

需要 Notion 投递时，在第三个终端执行：

```bash
uv run python -m app.workers.notion_delivery
```

飞书灵感采集是可选独立进程：

```bash
uv run python -m app.workers.feishu_inspiration
```

## 2. Docker：自带 PostgreSQL

`docker-compose.yml` 会创建内部 PostgreSQL 卷 `postgres_data`，但不会向宿主机暴露数据库端口。
`migrate` 会先幂等地补齐历史迁移依赖的 `users` 基表，再运行 `alembic upgrade head`；迁移成功后
才会启动 API、前端和 Notion 投递 worker。该兼容步骤不会执行完整 `create_all`，也不会覆盖已有数据。

1. 创建 `.env`。其中 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 必填；
   `POSTGRES_HOST` 与 `POSTGRES_PORT` 会被 Compose 覆盖为内部的 `db:5432`。
2. 首次部署或升级后拉取镜像并执行：

```bash
docker compose pull
docker compose up -d --wait
docker compose ps
```

`migrate` 显示为退出码 `0` 是预期状态，不是故障。正常服务为 `db`、`web`、`frontend`、
`notion-delivery`；默认访问地址是 <http://localhost:3000/>。

`web` 和 `frontend` 具有 HTTP 健康检查；Notion 投递与飞书灵感是长连接／轮询 worker，并不监听
HTTP 端口，因此以进程退出后的自动重启监测其可用性，不套用 Web 健康检查。

需要飞书灵感采集时显式启用 profile：

```bash
docker compose --profile inspiration pull
docker compose --profile inspiration up -d --wait
```

灵感 Markdown 默认挂载在 `./data`；可在 `.env` 设置 `MYSERVICE_DATA_DIR` 改为持久化宿主机目录。

## 3. Docker：外部 PostgreSQL

`docker-compose.external-postgres.yml` **没有 `db` 服务**，也不会创建或暴露 PostgreSQL。它会从
`.env` 读取 `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。

部署前必须先备份外部数据库，并从部署主机确认该地址可访问。然后执行：

```bash
docker compose -f docker-compose.external-postgres.yml pull
docker compose -f docker-compose.external-postgres.yml up -d --wait
docker compose -f docker-compose.external-postgres.yml ps
```

API 默认发布在 `MYSERVICE_PORT`（默认 `20035`），前端发布在 `FRONTEND_PORT`（默认 `3000`）。
要启用飞书灵感采集：

```bash
docker compose -f docker-compose.external-postgres.yml \
  --profile inspiration pull
docker compose -f docker-compose.external-postgres.yml \
  --profile inspiration up -d --wait
```

外部数据库不可达或迁移失败时，`migrate` 会失败，依赖它的 API 与 Notion worker 不会启动；先检查
`docker compose -f docker-compose.external-postgres.yml logs migrate`，不要通过重置数据库绕过该失败。

### 旧 `create_all` 数据库的版本标记对齐

早期部署曾在应用启动时使用 `create_all` 建表，之后才开始记录 Alembic revision。这类数据库可能已经
拥有 `notion_database_mappings`、`sport_record` 等新表和字段，但 `alembic_version` 仍停留在更早版本。
此时直接升级会报 `DuplicateTable`，例如 `relation "notion_database_mappings" already exists`。

**不得删除表或清空数据库。** 先完成可恢复备份，并核对表、字段、索引与当前 head 的语义一致；确认后，
仅更新 Alembic 的版本标记，再正常启动：

```bash
# 当前 head 应显示为 20260922_sport_details
docker compose -f docker-compose.external-postgres.yml run --rm --no-deps \
  migrate alembic heads

# 仅记录已具备的结构；不执行建表、删表或数据转换
docker compose -f docker-compose.external-postgres.yml run --rm --no-deps \
  migrate alembic stamp 20260922_sport_details

docker compose -f docker-compose.external-postgres.yml up -d --wait
```

若缺任一表、字段或唯一索引，或无法确认该库由旧 `create_all` 创建，停止在这里并先恢复/核对备份，
不得使用 `stamp` 跳过真实迁移。

## 4. 验证、升级与停止

Docker 功能测试使用独立 PostgreSQL 和独立 Compose 项目，不读取 `.env` 中的真实数据库。它保留
`build:` 以测试当前工作区源码；这与只拉取镜像的 NAS 部署入口不同：

```bash
./scripts/test.sh unit
./scripts/test.sh functional
```

升级有数据的数据库前，先备份并确认当前版本：

```bash
uv run alembic heads
uv run python -m app.db.migration_baseline
uv run alembic current
```

空库的 Docker 功能测试已经验证“补齐历史基础表 + `alembic upgrade head`”链路。它不能替代在真实生产数据备份副本上
验证历史版本的升级／回退路径。

停止服务但保留自带 PostgreSQL 数据：

```bash
docker compose down
```

不要执行 `docker compose down --volumes`，除非你已确认要删除内置 PostgreSQL 的全部数据。
