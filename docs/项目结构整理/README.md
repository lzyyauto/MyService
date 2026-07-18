# 项目结构整理

## 目标与边界

本次整理以“结构常见、职责单一、行为兼容”为目标。只移动可明确分类的代码和资料，不移动数据库可能引用的历史媒体，不重写已发布的 Alembic 迁移，也不修改 API 路径和数据模型。

## 最终结构

```text
app/
├── api/v1/endpoints/  HTTP 接口层
├── core/              配置、安全等横切能力
├── db/                数据库基础设施
├── models/            SQLAlchemy 模型
├── schemas/           Pydantic 模型
├── services/          业务服务与外部系统集成
└── utils/             通用工具
alembic/               数据库迁移
scripts/               人工执行的运维与诊断脚本
tests/                 自动化测试
docs/                  设计、说明和历史资料
temp/                  运行时媒体，不进入版本控制或镜像
```

## 变更与理由

| 变更 | 理由 | 兼容处理 |
|---|---|---|
| 两处服务目录统一到 `app/services/` | 服务分散在两处，边界不清 | 全量更新内部导入，类名和单例名不变 |
| 服务文件采用 `bark.py`、`notion.py`、`telegram.py`、`video_processor.py` | 位于 `services` 包后，`_service` 后缀重复表达职责 | API 和业务逻辑不变 |
| 为各 Python 包补齐 `__init__.py` | 明确包边界，改善测试、IDE、打包和静态分析的一致性 | 不改变公开 API |
| 用 `app/models/__init__.py` 集中注册模型 | 独立执行 `init_db()` 时原先只注册了部分表 | `init_db` 与 Alembic 共用同一模型注册入口 |
| 删除根目录旧模拟脚本 | 它复制业务逻辑、没有测试真实实现，且被 pytest 误收集后跳过 | 由真实应用回归测试替代 |
| Telegram 调试脚本改名为 `verify_telegram_bot.py` | 它需要真实账号和网络，不是自动化测试 | 脚本行为不变，避免 pytest 误收集 |
| 删除第三方大响应样例 | 样例没有被代码或测试引用，且其中的临时下载链接已经失效 | 无运行时影响 |
| 生产与开发依赖拆分，并移除源码未引用的包 | 测试工具和无用依赖不应进入生产镜像 | 后续已迁移到 uv：生产依赖与 `dev` 组统一声明在 `pyproject.toml` |
| 完善 `.env.example` | 原文件有重复项、伪密钥和结尾残留字符 | 只保留安全占位符和有效格式 |
| 增加结构测试 | 防止新增模型忘记注册导致初始化缺表 | 不连接数据库 |

## 运行时数据处理

清理时通过只读数据库查询核对 `video_process_tasks.video_path` 和 `audio_path`：删除了 9 个确定未被引用的媒体文件，释放约 106 MB。现存 14 个媒体文件均有数据库引用，共约 916 MB，因此不是冗余文件并予以保留。`temp/` 已被 Git 和 Docker 构建上下文排除，属于运行数据而非源码。

旧本地 `venv/` 与 `.claude/settings.local.json` 均可重新生成，已在最终验证后删除。项目现已迁移到 uv，并由 `uv sync` 在根目录管理标准 `.venv/`。

`CLAUDE.md` 原先与 `AGENTS.md` 重复维护整份项目说明，容易产生偏差；现缩减为入口文件，统一以 `AGENTS.md` 为事实来源。

## 顺带修复的既有问题

- 作息记录列表端点原先没有函数体，现恢复按用户过滤、按时间倒序和分页查询。
- GTD 同步 Notion 时原先使用未定义变量，现明确使用“名称”标题字段与任务名。
- `init_db()` 原先可能漏建 GTD 和视频任务表，现通过统一模型注册修复。

## 已知风险

`alembic heads` 显示 `796f614d8ac3` 与 `a1b2c3d4e5f6` 两个迁移头。第二个迁移虽然逻辑上依赖第一个，却声明 `down_revision = None`。直接改写已在使用的迁移可能导致现有数据库版本表不一致，因此本次不修改。建议以后创建一个新的 merge revision，并先核对线上 `alembic current`。

现有 Pydantic 模式仍使用部分 v1 兼容写法，测试会产生 13 条弃用警告，但当前 Pydantic 2.5.2 下功能正常。一次性改写验证器和序列化配置可能改变 API 响应，因此不与目录整理混做，建议后续作为独立需求迁移。

数据库连接检查提示 `zrest` 的 collation 版本与当前操作系统不一致。此次只做了读取，没有修改数据库；应在确认备份和索引重建方案后执行 PostgreSQL 提示的 collation 刷新操作。

## 验证记录

- `python -m compileall -q app alembic scripts tests`：通过。
- `pytest -q`：4 项结构与既有问题回归测试通过；存在上述 Pydantic 兼容警告。
- 应用导入与路由检查：13 个路由、4 张模型表注册成功。
- `.env.example`：可被 `Settings` 正常解析。
- `pip check`：清理虚拟环境前确认无依赖冲突。
- `docker compose config -q`：配置解析通过。
- `git diff --check`：无空白错误。
- `alembic heads`：命令可运行，但确认存在上述两个 head，未擅自改写。

## 回退

代码和已删除的历史样例可通过 Git 提交记录回退。被删除的未引用媒体与本地虚拟环境不纳入 Git；虚拟环境可按 README 重建。
