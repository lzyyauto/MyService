# 飞书采集职责简化

更新：2026-10-03。已实现纯采集；状态库默认复用项目 PG，详见[最新状态库说明](../飞书状态库复用PostgreSQL/README.md)。

## 1. 需求与决定

飞书机器人负责长连接、基本反馈和消息落盘。总结、对话、澄清及 agent 编排后续独立讨论。
原先把每日总结嵌入采集的方式，不能自然处理 AI 提问后的用户回复，已从当前有效功能移除。
本轮按现状、设计、实施、验证、交付整理；仓库未找到 docs/SETP.md，参考现有开发指南。

## 2. 当前流程

```text
用户在群聊／私聊发送文本
  → 飞书长连接接收
  → 更新来源清单
  → 按 apps / routes 选择文档目标
  → 持久化内部消息状态
  → 追加完整北京时间、发送者、会话 ID 和原文到 Markdown
  → 落盘成功后添加 OK 表情回执
```

OK 表示已经收录，不是 AI 回复，也不代表程序修改了飞书平台的正式已读状态。
文本按原内容保存，多行保留；图片／语音等非文本暂不落盘。机器人／系统消息忽略。
机器人只收集，不修改原文、分类、不定时运行、不提交 AI、不发送总结，也不保留对话会话。
后续 agent 可以独立读取这份 Markdown，但本轮不实现任何 agent 集成。

## 3. 配置与职责边界

| 配置 | 当前作用 |
|---|---|
| apps | 多个机器人连接、凭证引用、默认文档目标 |
| routes | 将群／私聊会话映射到文档目标；可选 sender_open_id／@ 过滤 |
| pipelines | 为兼容已使用的名称保留；仅表示 id、input_path、enabled 的文档收集目标 |
| runtime | 文件根目录、状态库模式／SQLite 兼容路径、采集轮询与有限重试 |
| observability | 来源发现、日志级别、保留时间和容量 |

多个来源可以共享一个目标；也可按 app_id／chat_id／pipeline_id 模板分开。
一条消息只写入一个目标。原有个人机器人、来源 ID、路由和文档路径均保留。
不再接受 ai_profiles、pipelines.ai／output／delivery 配置段。密钥仍用环境变量引用，实际值放 .env。

文档映射和开关热加载，默认约一秒；无效更新保留旧配置。
新增机器人时，凭证变量已载入进程环境才可直接热启用；.env、runtime、日志目录、代码变化需重启采集。
本次属于代码改造，已有 collect 需停止后重新启动一次；以后仅改路由和文档目标不用重启。

## 4. 实施与数据保留

- 保留采集独立进程、多应用连接、来源 ID 查询、限时发现、去重、文件锁及半条写入恢复。
- 内部状态默认复用项目 PostgreSQL，由 Alembic 创建表；显式 SQLite 供兼容与隔离演示。
- FEISHU_STATE_DATABASE_URL 仅作可选覆盖；留空读取 POSTGRES_*。旧 SQLite 状态可受控导入 PG。
- 删除 AI 客户端、每日整理进程、任务领取／快照／生成／结果投递代码及 CLI worker／process／retry。
- Docker 移除 inspiration-ai 与 inspiration-processing；默认 PG 模式下，采集服务等待 migrate。
- 原文、已生成结果、SQLite 中历史整理任务和 PostgreSQL 相关旧迁移／模型均保留，不执行删表或 downgrade。
- 旧模型 FeishuRun 仅为历史结构兼容，采集不创建、查询或消费其数据。
- 本次移除前的私有配置、提示词和代码保存在 data/backups/feishu-collection-only-*；该目录不纳入 Git。
- 历史提示词保留在本地 config/prompts/ 供后续参考，采集不读取，也不放进发布镜像。

删除 Markdown 不会恢复旧记录；收到新消息后重新创建。内部 HTML 标识用于写入恢复与去重，
在 Markdown 中通常不显示，不应手动修改。其他工具读写／归档该文件时需协调文件锁，
不要在采集正在追加时直接覆盖整份文件。

PostgreSQL 与 Markdown 均需备份；显式 SQLite 模式应放在本机磁盘，不要放到不支持锁的网络文件系统。
失败状态只用于落盘／基本回执重试，不是用户任务或 AI 工作流。

## 5. 验证与交付

单元测试使用 mock 事务和 tmp_path，无网络／真实数据库。纯采集跨组件演示使用临时 SQLite、
本机 HTTP 回执替身，覆盖落盘、回执失败重试不重写、重新打开状态库后去重、删除后新消息重建。
其他 API 功能测试继续使用统一入口的一次性 PostgreSQL；默认不访问真实飞书、Notion 或 Bark。
Docker daemon 不运行时不自动启动它，不把 Compose 静态校验当成容器构建成功。

2026-10-02 本轮验证：

- `./scripts/test.sh unit`：113 项通过，活跃模块覆盖率 85.82%。
- 纯采集专用功能测试：1 项通过（临时 SQLite、本机 HTTP 回执替身）。
- 本地演示及 CLI validate／init-local／simulate／sources／status／discover／logs：通过；不请求真实服务。
- Python 编译、单一 Alembic head、两份部署 Compose 静态校验：通过。
- 实际 TOML 已简化并通过校验，机器人、路由、输入路径保留；旧本地 AI 整理进程已确认退出。
- Docker daemon 未运行：未构建容器、未执行其他 PostgreSQL／HTTP 功能测试、未发布部署。
- 本轮未再次连接真实飞书；本地采集进程需启动／重启，再手动发消息验收。

运行、来源查询与扩展步骤见[操作手册](操作手册.md)。
原 AI 方案和操作文档已标记为历史，仅用于追溯，不作为当前运行说明。


## 6. Docker 配置复核（2026-10-03）

采集保持独立进程，config 只读，data 可写，禁用 HTTP 探针和 Docker stdout 日志。
当前默认项目 PG，两个方案等待 migrate 成功；内置数据库地址 db:5432，外部数据库读取项目 .env。
详情见[最新 PG 与 Docker 操作手册](../飞书状态库复用PostgreSQL/操作手册.md)。
