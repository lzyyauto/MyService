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
| 根目录旧模拟脚本移入 `归档/` | 它复制业务逻辑、没有测试真实实现，且被 pytest 误收集后跳过 | 保留源码供追溯 |
| Telegram 调试脚本改名为 `verify_telegram_bot.py` | 它需要真实账号和网络，不是自动化测试 | 脚本行为不变，避免 pytest 误收集 |
| 第三方大响应样例移入 `归档/` | 样例不属于项目主文档，也没有被运行时代码引用 | 原样保留 |
| 生产与开发依赖拆分，并移除源码未引用的包 | 测试工具和无用依赖不应进入生产镜像 | 开发环境改装 `requirements-dev.txt`；保留应用和运维脚本实际使用的依赖 |
| 完善 `.env.example` | 原文件有重复项、伪密钥和结尾残留字符 | 只保留安全占位符和有效格式 |
| 增加结构测试 | 防止新增模型忘记注册导致初始化缺表 | 不连接数据库 |

## 运行时数据处理

`temp/` 当前约 1 GB，并可能被 `video_process_tasks.video_path`、`audio_path` 等字段引用。移动或删除会让历史文件链接失效，所以本次保留原位。该目录已经被 Git、Docker 构建上下文排除，属于运行数据而非源码。

本地 `venv/` 约 126 MB，已被 Git 和 Docker 忽略。为避免破坏用户当前解释器，本次不移动；以后新环境建议使用更常见的 `.venv/` 名称。

## 顺带修复的既有问题

- 作息记录列表端点原先没有函数体，现恢复按用户过滤、按时间倒序和分页查询。
- GTD 同步 Notion 时原先使用未定义变量，现明确使用“名称”标题字段与任务名。
- `init_db()` 原先可能漏建 GTD 和视频任务表，现通过统一模型注册修复。

## 已知风险

`alembic heads` 显示 `796f614d8ac3` 与 `a1b2c3d4e5f6` 两个迁移头。第二个迁移虽然逻辑上依赖第一个，却声明 `down_revision = None`。直接改写已在使用的迁移可能导致现有数据库版本表不一致，因此本次不修改。建议以后创建一个新的 merge revision，并先核对线上 `alembic current`。

现有 Pydantic 模式仍使用部分 v1 兼容写法，测试会产生 13 条弃用警告，但当前 Pydantic 2.5.2 下功能正常。一次性改写验证器和序列化配置可能改变 API 响应，因此不与目录整理混做，建议后续作为独立需求迁移。

## 验证记录

- `python -m compileall -q app alembic scripts tests`：通过。
- `pytest -q`：4 项结构与既有问题回归测试通过；存在上述 Pydantic 兼容警告。
- 应用导入与路由检查：13 个路由、4 张模型表注册成功。
- `.env.example`：可被 `Settings` 正常解析。
- `pip check`：当前虚拟环境无依赖冲突。
- `docker compose config -q`：配置解析通过。
- `git diff --check`：无空白错误。
- `alembic heads`：命令可运行，但确认存在上述两个 head，未擅自改写。

## 回退

代码移动可通过 Git 回退。归档目录保存的历史材料可随时取回；`temp/` 和本地虚拟环境未被改动，不需要恢复。
