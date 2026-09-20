# Notion 统一采集与运动映射

手动验证请按[本地操作手册](手动测试操作手册.md)执行；该流程不依赖 Docker。

## 1. 目标与边界

本需求新增一个经认证的 Notion 标准页面载荷接收入口，用于替代 iOS 快捷指令直连
Notion。PostgreSQL 是本地数据的唯一可信来源；Notion 是异步、尽力而为的副本。

现有睡眠/起床 API 和其 Notion 同步逻辑不在本需求中改造。

不再使用 `public-request-dump` 作为正式入口。它是无鉴权的短时调试工具，必须保持默认
关闭，且不得记录 Notion Token。

## 2. 统一输入契约

请求需要本系统的 Bearer API Key，而不是 Notion Token：

```json
{
  "parent": {
    "type": "database_id",
    "database_id": "<Notion database ID>"
  },
  "properties": { "<Notion 属性名>": { "type": "..." } },
  "idempotency_key": "<可选的快捷指令 UUID>"
}
```

除 `idempotency_key` 外，顶层字段按原样持久化，并作为 Notion 页面创建请求转发。快捷
指令应逐步生成幂等键；未提供时系统仍接受请求，但重复执行会产生独立事件。

## 3. 数据模型

| 表 | 职责 |
|---|---|
| `notion_database_mappings` | 用户下 database ID 到业务类型、显示名称和说明的关系；同时保存内部 mapper 版本 |
| `notion_ingest_events` | 每个已接受请求的完整原始 JSON |
| `exercise_records` | 严格解析出的单次运动事实，通过 `source_event_id` 关联事件 |
| `notion_deliveries` | Notion 投递载荷、重试、页面 ID 和失败摘要 |

首个业务类型是 `exercise`；其当前内部 mapper 为 `exercise_notion_v1`，固定要求下列
Notion properties：

- `运动类型`: `select.name`；
- `时长`: 非负 `number`；
- `记录时间`: 带时区的 `date.start`；
- `日期`: `YYYY-MM-DD` 的 `date.start`；
- `月份`: 非空 `title`；
- `城市`: 可选 `rich_text`。

这不是运行时按 JSON 动态建 SQL 表。`exercise_records` 是依据现有稳定运动载荷建立的固定
业务结构；载荷中的其他字段仍保存在原始事件并转发 Notion，但不会自动增加为业务表列。

## 4. 处理规则

1. 已有业务映射的 database ID：先严格解析；任一字段不符合要求即返回 `422`，不创建
   事件、不写运动表，也不投递 Notion。
2. 未映射的 database ID：只要符合最基础的 Notion 页面输入契约，就保存原始事件并建立
   投递任务；不创建业务表记录。
3. 事件、业务记录与投递任务在同一数据库事务中创建。
4. 独立 `notion-delivery` worker 投递任务；每个任务最多尝试三次。成功保存 Notion page
   ID；最终失败保留事件和错误摘要并发送 Bark。
5. 普通 database 以后建立业务映射时，映射只对其后的新提交生效；已有原始事件不自动
   回填业务表，也不要求迁移历史数据。

## 5. 使用方式

先为运动 database 建立映射：

```bash
curl -X PUT "http://localhost:8000/api/v1/notion-ingest/mappings/<database-id>" \
  -H 'Authorization: Bearer <system-api-key>' \
  -H 'Content-Type: application/json' \
  -d '{
    "business_type":"exercise",
    "display_name":"日常运动记录",
    "description":"来自 iOS 快捷指令；时长单位为小时。"
  }'
```

然后把快捷指令的 URL 改为 `POST /api/v1/notion-ingest/`，保留 `parent` 和 `properties`，
把 Authorization 改为系统 API Key。Notion Token 只能保留在服务器 `.env` 中。

可通过 `GET /api/v1/notion-ingest/mappings` 核对已配置映射。

## 6. 本地验证与生产迁移边界

当前手动联调先使用本地 FastAPI、本地 PostgreSQL 和独立 worker，分别验证现有运动表的
“业务入库 + 转发”与测试表的“原始留存 + 转发”。无需 Docker，具体步骤见本目录操作手册。

新迁移 `20260902_notion_ingest` 以现有两个 Alembic head 为父 revision。生产升级前必须
先备份并只读确认 `alembic current`；不得在未知的有数据数据库上重置 revision。

单元测试验证标准载荷、严格解析、幂等、路由认证和投递重试；功能测试验证真实 HTTP、
PostgreSQL 落库和未映射事件保留。默认测试不访问真实 Notion 或 Bark。
