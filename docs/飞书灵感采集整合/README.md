# 飞书灵感采集整合

## 1. 现状

`daily-claw` 是一个独立 Python 项目，通过飞书 WebSocket 长连接接收文本消息，
按 `- [HH:MM:SS] 内容` 的格式追加到本地 Markdown，并在成功后给原消息添加
`OK` 表情。

本次目标是把这项能力纳入 Z 收集系统，同时满足：

- 不改变现有睡眠 API、数据库和历史数据；
- 不重新启用已废弃的 GTD、Telegram 下载或视频处理；
- 保留原有消息格式和飞书回执行为；
- 当前项目继续使用 uv 和根目录 `.venv`；
- 为后续 AI 整理文档留下稳定输入，但不虚构原项目中不存在的 AI 实现。

## 2. 设计

飞书长连接不是 HTTP 请求处理逻辑，因此采用同仓库、同依赖、同 Docker 镜像下的
独立 worker：

```text
飞书消息
  -> app.workers.feishu_inspiration
  -> app.services.inspiration
  -> data/inspirations.md
  -> 后续 AI 整理能力（本次不实现）
```

不把它放入 FastAPI 生命周期，原因是：

1. 飞书 SDK 的 `Client.start()` 是阻塞式长连接；
2. Uvicorn 重载或多 worker 会导致重复建立连接；
3. 采集故障不应影响睡眠 API 的可用性；
4. 独立进程可以分别重启、扩缩和查看日志。

事件回调只做校验、内存去重和入队，文件写入与飞书 HTTP 回执由后台线程执行，
避免超过飞书事件处理时限。HTTP 调用增加超时，最近 2,000 个消息 ID 在进程内去重。

## 3. 实施

- 新增 `app/services/inspiration.py`：事件解析、去重、Markdown 持久化、token 缓存和回执；
- 新增 `app/workers/feishu_inspiration.py`：独立进程入口；
- 新增 `lark-oapi`、`requests` 生产依赖；
- 新增飞书配置和 `data/` 运行时目录；
- Docker Compose 新增可选的 `inspiration` profile；
- 项目名称恢复为通用的“Z 收集系统”，睡眠仍是当前 HTTP API 模块。

本地启动：

```bash
uv sync --locked
uv run python -m app.workers.feishu_inspiration
```

Docker 启动：

```bash
docker compose --profile inspiration pull
docker compose --profile inspiration up -d --wait
```

部署 Compose 仅拉取 GitHub Actions 发布的镜像，NAS 不需要该仓库的源码；镜像标签与完整部署说明见
[`docs/容器化部署与本地运行/README.md`](../容器化部署与本地运行/README.md)。

## 4. 验证

自动化测试覆盖：

- 原有 Markdown 格式与东八区时间；
- 文本消息入队；
- 同一消息在单进程内不重复记录；
- 非文本消息被忽略；
- 现有睡眠 API 路由保持不变。

实施完成时执行结果为 `10 passed`，Python 编译检查、`uv lock`、`uv sync --locked`
和包含 `inspiration` profile 的 Compose 配置解析均通过。

飞书真实连接和消息回执需要有效应用凭证，不能在无密钥的自动化测试中写入外部服务。

## 5. 交付说明

### 配置

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BASE_URL=https://open.feishu.cn
INSPIRATION_DOC_PATH=data/inspirations.md
```

### 已知限制

- 去重状态只保存在内存中，进程重启后飞书若重放旧事件，仍可能产生重复记录；
- 当前存储格式与原项目一致，只有时间没有日期，不适合直接区分跨日内容；
- `daily-claw` 现有代码并未包含 AI 生成文档逻辑。本次仅把 Markdown 定义为后续整理阶段的输入。
- `daily-claw` 的 Git 历史曾经跟踪 `.env`，之后虽已删除，但历史提交仍可能包含旧密钥。
  本次没有复制旧凭证；启用前应在飞书开放平台重置应用密钥，并把新密钥只写入当前项目
  被 Git 忽略的 `.env`。

### 回退

停止 worker 即可，不影响 FastAPI：

```bash
docker compose --profile inspiration stop feishu-inspiration
```

代码回退不会修改数据库；`data/inspirations.md` 是独立运行时数据，应单独保留或备份。
