# 飞书状态库复用 PostgreSQL

更新：2026-10-03。机器人仍只采集、落盘、添加 OK，不恢复 AI 或每日整理。

## 需求与决定

用户要求直接复用项目 PostgreSQL，而不是强制维护独立 SQLite。此前 SQLite 固定限制已撤回。
按现状、设计、实施、验证、交付记录；docs/SETP.md 当前缺失，遵循项目开发与测试规范。

## 连接规则

1. runtime.database_url_env 指定环境变量名；该变量非空时使用显式 PostgreSQL／SQLite 连接串。
2. 未覆盖时，state_backend="postgresql"（默认）直接读取 POSTGRES_USER／PASSWORD／DB／HOST／PORT。
3. 只有显式 state_backend="sqlite" 才回退 state_path，用于隔离演示。

连接不依赖 Settings 的完整应用字段。URL.create 正确处理密码中的特殊字符，不输出连接串。
PG 使用小型连接池与 pre_ping，事务使用 PostgreSQL 正常提交／回滚；BEGIN IMMEDIATE 仅用于 SQLite。
飞书 HTTP 回执在数据库事务外发送，避免等待网络时持有数据库锁。

## 表管理与 Docker

PG 启动只检查采集表和列，不执行 create_all、不自动迁移生产库；缺表返回 state_schema_missing。
使用既有 20261002_feishu 迁移，不新增／改写历史 revision。四张采集表用于来源、目标、消息和控制；
该历史兼容迁移还创建 feishu_runs，当前采集不使用它。
Docker 两种部署均等待 migrate 成功；内置数据库方案给采集设置 POSTGRES_HOST=db、PORT=5432。
外部数据库方案沿用项目 .env。挂载仍只需 config（只读）和 data（可写），没有 SQLite 的额外挂载要求。
本地 baseline／Alembic 与 CLI 均读取项目 .env，进程环境优先。

## 旧状态迁移

import-sqlite 明确读取只读 SQLite，仅向已迁移 PG 导入四张采集表。
导入前要求原采集停止、没有待写入／失败消息或待发／失败回执；同目录角色锁防止在线导入。
所有写入在同一 PG 事务中，按主键跳过已有记录、不覆盖状态、可重复执行。源库及历史 AI 数据不删除。
路径仍按原绝对路径保留，跨机器部署前清空积压，新消息使用新运行环境的目标路径。

## 本轮实际切换

- 项目 PG 可连接，原版本 20260922_sport_details；备份后升级到 20261002_feishu。
- 现有业务表行数核对未变；新表已经创建，无需用户手工建表。
- SQLite 5 条消息、3 个来源、1 个目标、1 个控制记录已导入 PG，积压和失败计数均为 0。
- 私有 .env 已清空 SQLite 覆盖，私有 TOML 显式 state_backend="postgresql"，应用、路由和路径保留。
- 旧 SQLite、原文及配置保留；完整 PG 备份与旧配置位于被忽略的 data/backups/feishu-project-pg-*。
- 准备备份时安装了独立的 libpq 命令行工具；它是本机操作工具，不增加项目或容器依赖。
- 初次切换时 Docker 尚未运行；用户启动 Docker 后，测试子代理已完成 8 项一次性 PG／HTTP 功能测试，测试资源已清理。

运行和 Docker 更新步骤见[操作手册](操作手册.md)。


## 验证结果

- 单元测试 122 项通过，活跃模块覆盖率 87.76%。
- SQLite 隔离闭环 1 项通过，独立本地演示通过。
- 两份 Compose 静态校验、编译、单一迁移 head 检查通过。
- 本轮项目 PG 升级及实际旧状态导入成功，四张采集表逐字段与原 SQLite 完全一致，Markdown 字节未变。
- 新增 PG 隔离功能测试与其余 HTTP／PG 回归合计 8 项通过；真实飞书及正式部署挂载／网络仍需人工验收。

子代理完整验证、测试边界及人工操作见[测试报告](测试报告.md)。
