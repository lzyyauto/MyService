# 睡眠接口收敛改造

> 后续说明：本次改造完成后，项目又新增了独立的飞书灵感采集 worker。
> 本文所述“单一职责”仅针对当时的 FastAPI HTTP 接口收敛；睡眠接口仍是当前唯一
> 业务 HTTP API，但项目整体不再是睡眠专用项目。新增设计见
> `docs/飞书灵感采集整合/README.md`。

## 目标

将项目收敛为只记录和分析睡眠数据的服务。GTD、Telegram 下载、视频处理和相关
AI 能力立即停止对外提供，但暂时保留历史代码、模型和迁移，降低数据库兼容风险。

## 生效范围

当前唯一业务前缀为 `/api/v1/rest-records`：

- `POST /`：创建睡眠或起床记录；
- `GET /`：查询当前用户记录；
- `GET /annual-summary/{year}`：年度睡眠总结；
- `GET /annual-summary/{year}/table`：年度睡眠明细。

根路径、Swagger、ReDoc 和 OpenAPI JSON 仍正常提供。

## 废弃策略

| 功能 | 原路径 | 当前行为 | 保留内容 |
|---|---|---|---|
| GTD | `/api/v1/gtd-tasks` | 未注册，返回 404 | 端点、Schema、模型、Notion/Bark 兼容方法 |
| Telegram 下载 | `/api/v1/telegram` | 未注册，返回 404 | 端点、Schema、服务、人工脚本 |
| 视频处理 | `/api/v1/video-process` | 未注册，返回 404 | 端点、Schema、模型、服务、AI 客户端 |
| 静态下载 | `/downloads` | 挂载已移除，返回 404 | 历史媒体文件 |

废弃端点使用 `create_disabled_router()`。即使开发者以后误把 router 注册回主应用，
统一依赖也会先返回 `410 Gone`，不会进入原业务函数。

## 启动行为

`app/main.py` 只导入休息记录端点。应用启动时只配置日志和初始化数据库：

- 不导入 Telegram 单例；
- 不连接 Telegram；
- 不创建下载目录；
- 不挂载静态媒体目录；
- OpenAPI 中不出现废弃接口和标签。

## 数据库兼容

`GtdTask`、`VideoProcessTask` 和两份历史视频迁移继续保留并注册到 SQLAlchemy
MetaData。这是有意的兼容策略：

- 不删除既有表和历史数据；
- 不改写已发布迁移；
- 避免 Alembic 自动生成误判为应删除旧表；
- 新功能不得再读写这些模型。

未来若确认要物理删除旧表，必须作为独立的数据迁移需求，先备份并核对线上数据。

## 配置与依赖

`.env.example` 只展示睡眠系统当前需要的数据库、Notion 和 Bark 配置。旧配置字段仍由
`Settings` 容忍，以兼容用户已有 `.env`，但主应用不读取。

Telegram 和视频处理专用依赖移动到 uv 的非默认 `legacy` 组：

```bash
# 正常开发，不安装废弃能力
uv sync --locked

# 仅在人工审查历史代码时安装；不会启用接口
uv sync --locked --group legacy
```

Docker 只安装生产依赖，并移除了 ffmpeg。

## 验证标准

- 主应用路由集合中不存在 GTD、Telegram、视频和 `/downloads`。
- 当前四个睡眠业务接口仍注册。
- 废弃路由保护机制返回 410。
- 应用生命周期不启动 Telegram。
- SQLAlchemy 仍注册历史模型，数据库结构保持兼容。
- 自动化测试、uv 锁文件和 Compose 配置通过。

## 验证结果

- 默认开发环境：39 个包，不包含 Telethon；6 项测试通过。
- 纯生产环境：32 个包，不包含 pytest、Telethon 和 ffmpeg 依赖。
- legacy 审查环境：43 个包，可导入全部保留模块。
- 主应用：8 个路由对象、4 个 OpenAPI 路径；只包含根路径与睡眠业务。
- GTD、Telegram、视频三个 router 在 legacy 环境中即使被误注册也全部返回 410。
- `uv lock --check`、`uv pip check`、`docker compose config -q` 和差异检查通过。
- Alembic 仍显示两个既有 head，本次未改写历史迁移。
