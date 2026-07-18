# UV 依赖管理迁移

## 目标

统一使用 uv 管理 Python 版本、直接依赖、开发依赖、锁文件和项目根目录虚拟环境，删除重复的 requirements 与 pytest 独立配置。

## 文件职责

| 文件 | 职责 | 是否提交 |
|---|---|---|
| `.python-version` | 固定本项目使用 Python 3.11 | 是 |
| `pyproject.toml` | 项目元数据、运行依赖、`dev` 依赖组和 pytest 配置 | 是 |
| `uv.lock` | 锁定完整依赖图，保证开发与构建可复现 | 是 |
| `.venv/` | uv 创建的本机虚拟环境 | 否 |

项目是直接运行源码的 FastAPI 应用，不需要构建 Python 分发包，因此设置了
`tool.uv.package = false`。

## 标准工作流

```bash
# 首次克隆或锁文件更新后
uv sync --locked

# 运行服务和测试
uv run uvicorn app.main:app --reload
uv run pytest -q

# 管理依赖
uv add <运行依赖>
uv add --dev <开发依赖>
uv remove <依赖>
uv lock
```

`uv sync` 默认同步 `dev` 组，并自动在项目根目录创建 `.venv/`。不要求手动激活；
需要激活时仍可执行 `source .venv/bin/activate`。

## Docker

Dockerfile 从固定版本的官方 uv 镜像复制二进制，并在复制源代码前执行：

```bash
uv sync --locked --no-dev --no-install-project
```

这样构建会校验锁文件、只安装生产依赖，并利用依赖层缓存。宿主机 `.venv/`
被 `.dockerignore` 排除；Compose 额外挂载 `/app/.venv`，防止 macOS 虚拟环境覆盖
容器内 Linux 环境。

## 迁移结果

- 原 `requirements.txt` 的 12 个直接依赖迁入 `[project.dependencies]`。
- pytest、pytest-asyncio、pytest-cov 迁入 `[dependency-groups].dev`。
- 已废弃的 Telegram、视频处理依赖迁入非默认 `legacy` 组，生产环境不安装。
- pytest 配置从 `pytest.ini` 迁入 `[tool.pytest.ini_options]`。
- 删除 `requirements.txt`、`requirements-dev.txt` 和 `pytest.ini`。
- Python 版本统一为 3.11，本地环境路径统一为 `.venv/`。

## 验证记录

- 本机 uv 版本：`0.5.24`。
- `uv lock --check` 与 `uv sync --locked`：通过。
- 根目录 `.venv/`：使用 CPython 3.11.11。
- `uv run pytest -q`：睡眠单一职责改造后为 6 项测试；保留既有的 13 条 Pydantic 弃用警告。
- 应用验证：仅注册睡眠相关业务路由；废弃功能不进入主应用。
- `uv pip check`：全部已安装包兼容。
- 独立生产环境执行 `uv sync --locked --no-dev --no-install-project`：睡眠系统当前安装 32 个生产包，确认未安装 pytest 和 Telethon。
- `docker compose config -q`：通过。
- 本机 Docker/OrbStack 守护进程未运行，因此未执行真实镜像构建；Dockerfile 已按官方 uv 锁文件同步模式配置。
