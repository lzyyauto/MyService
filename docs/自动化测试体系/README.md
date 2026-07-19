# 自动化测试体系

## 1. 现状

项目此前有少量 pytest 用例，但没有明确区分单元测试与功能测试，也没有统一的一键入口。
现有开放功能包括：

- 睡眠记录 HTTP API：认证、创建、自动切换睡眠/起床、列表、分页、年度汇总和明细；
- 飞书灵感采集：文本事件解析、去重、Markdown 落盘、token 获取和消息回执；
- 睡眠记录的可选 Notion 同步与失败 Bark 提醒；
- 已废弃接口必须持续保持不可调用。

测试必须默认隔离用户数据库和外部服务，不能把测试数据写入正式 PostgreSQL、Notion、
Bark 或飞书。

## 2. 设计

统一入口为：

```bash
./scripts/test.sh unit
./scripts/test.sh functional
./scripts/test.sh all
```

### 单元测试

单元测试位于 `tests/unit/`，不要求 Docker 或网络：

- Schema、时区转换和认证逻辑；
- 睡眠记录创建、自动切换、分页和年度统计算法；
- Notion 数据格式转换、Bark 通知参数；
- 灵感事件过滤、去重、落盘顺序；
- 开放路由白名单和废弃路由保护；
- SQLAlchemy 模型注册完整性。

脚本会先执行 `uv sync --locked` 和 Python 编译检查，然后执行 pytest 和覆盖率门槛。
覆盖率只统计当前开放功能涉及的模块；废弃兼容函数不计入门槛。当前门槛为 75%。

### 功能测试

功能测试位于 `tests/functional/`，通过 `docker-compose.functional.yml` 启动：

- 一次性 PostgreSQL 15；
- 按生产镜像构建方式启动的 FastAPI；
- 真实 TCP、HTTP、认证、SQLAlchemy 和 PostgreSQL 链路；
- 睡眠/起床创建、自动切换、查询、分页、年度明细和年度汇总；
- 非法认证、非法参数和废弃接口；
- 本地飞书假服务上的“事件 → Markdown → token → reaction”跨组件链路。

PostgreSQL 使用 tmpfs，Compose 项目名每次唯一，脚本结束后自动删除容器和测试数据。
默认端口为 `18080` 和 `15432`，冲突时可覆盖：

```bash
FUNCTIONAL_TEST_PORT=28080 FUNCTIONAL_TEST_DB_PORT=25432 \
  ./scripts/test.sh functional
```

调试失败现场时可保留容器：

```bash
KEEP_TEST_STACK=1 ./scripts/test.sh functional
```

## 3. 实施中修正的缺口

1. 未配置 Notion 时不再创建后台同步任务，防止测试和普通开发环境误访问外部服务。
2. 缺少认证信息统一返回 `401`，与接口文档一致。
3. `skip >= 0`，`1 <= limit <= 500`，避免非法分页进入数据库。
4. 年份限定为 `1970..2100`，非法年份在请求校验阶段返回 `422`。
5. 活跃测试与废弃功能测试分离，不再用废弃 GTD 行为充当回归测试。

## 4. 验证

本地可执行部分：

- 单元测试：26 个通过；
- 活跃模块覆盖率：83.22%，通过 75% 门槛；
- 飞书本地跨组件功能测试：通过；
- Python 编译、Shell 语法和 Compose 配置解析：通过。

完整 HTTP + PostgreSQL 功能测试需要 Docker daemon。本次开发环境的 Docker daemon
未运行，因此脚本和 Compose 配置已验证，但真实容器链路需在 Docker 启动后执行：

```bash
./scripts/test.sh functional
```

## 5. 已知限制与后续建议

### 当前应明确保留的限制

- 不自动连接真实飞书 WebSocket，也不向真实消息添加 reaction；
- 不向真实 Notion 或 Bark 写入测试数据；
- 不包含负载、并发、长时间稳定性或故障注入测试；
- 不包含依赖漏洞扫描和密钥扫描；
- 不验证现有数据库从历史版本执行 Alembic 升级。

### Alembic 阻塞项

仓库当前存在两个 Alembic head。为避免擅自合并历史迁移并危及已有数据库，功能测试空库
暂时使用 `init_db/create_all` 建表。因此它验证的是当前模型与运行链路，不代表生产迁移
链路已经健康。

单元测试脚本会打印警告；CI 中可先设置以下变量把它升级为强制失败：

```bash
STRICT_MIGRATIONS=1 ./scripts/test.sh unit
```

建议后续在备份并确认生产数据库当前 revision 后，单独设计 merge migration，再把功能
测试切换为 `alembic upgrade head`。

### 建议的第二阶段

1. 在 CI 中执行 `./scripts/test.sh all`；
2. 增加 ruff 或等价静态检查；
3. 增加依赖漏洞扫描、密钥扫描；
4. 对年度统计算法增加更多异常序列和跨年边界属性测试；
5. 为飞书真实长连接建立受控的测试应用和人工冒烟清单；
6. 若数据量增长，增加查询性能和并发写入测试。

## 回退

测试设施只使用独立 Compose 文件和测试目录。删除新增测试文件与
`docker-compose.functional.yml` 即可回退，不涉及业务数据迁移。业务边界修正可通过
对应 Git 提交回退。
