# 运动历史数据整合

## 目标

将旧 `sport_data` 中的历史运动记录投影到当前 `sport_record`，使运动看板可以统计历史数据；
同时原样保留旧表的 `detail` 与 `detail2`，但不改变现有 HTTP API、看板或 Notion 映射契约。

## 字段映射

| `sport_data` | `sport_record` | 规则 |
| --- | --- | --- |
| `record_finish` | `occurred_at` | 以北京时间解释旧表无时区时间，写为带时区时间。 |
| `record_date` | `occurred_on` | 保留旧记录归属日期；不以完成时间跨日自动改写。 |
| `record_date` | `month_str` | 格式化为 `MM月`。 |
| `sport_type` | `sport_type` | 去除首尾空白后原样保留。 |
| `duration` | `duration` | 单位始终为分钟，不换算。 |
| `city` | `city` | 空白字符串归一为 `NULL`。 |
| `detail` / `detail2` | 同名字段 | 仅存储，不在当前业务接口中体现。 |

`sport_record` 的 `source_event_id` 是必填外键。每条实际导入记录必须创建一条
`notion_ingest_events` 审计事件，标记为本地历史导入；不创建 `notion_deliveries`，因此不会
触发对 Notion 的任何写入或重试。

## 去重与安全边界

导入前先备份 `sport_record`。源表以
`record_date`、`record_finish`、`sport_type`、`duration`、`city`、`detail`、`detail2`
归一化后的组合为业务去重键；只导入每组第一条。目标表再次按相同业务键查重，重复运行不新增
业务记录或审计事件。

现有生产数据库的 Alembic 版本可能落后于实际由 `init_db()` 创建的表结构；生产导入时先备份，
再用受控 DDL 添加两列。仓库中的 Alembic revision 用于全新或已正确追踪版本的环境，不得对已有
数据的数据库盲目执行全量升级。

## Notion CSV 增量补录

Notion 导出的运动 CSV 可以直接补入 `sport_record`，不需要再次投递到 Notion。`月份`、`日期`、
`记录时间 (GMT+8)`、`时长`、`城市`、`运动类型`分别映射到当前投影的时间、时长、地点与种类字段；
`Test` 映射为 `detail`，`Text` 映射为 `detail2`，`创建时间`写入审计和业务记录的创建时间。

CSV 仍需经过同一业务去重键检查，并与目标表再查重。由于 `source_event_id` 是必填外键，实际导入会
建立标记为本地 Notion CSV 历史导入的审计事件来保留原始行；绝不创建 `notion_deliveries`，因此不会
发起 Notion 写入、重试或 Bark 通知。若操作者已持有独立备份，可以明确选择跳过这一次增量导入前的
额外备份。
