# 公开请求调试接收器

## 1. 现状

睡眠记录 API 使用 Bearer API Key 认证。为方便把第三方接口地址临时改到本服务并观察
真实输入，需要一个不依赖数据库、不校验认证和请求体的 POST 接收器；它不得影响现有
业务端点的认证或数据写入行为。

## 2. 设计

- 新增 `POST /api/v1/public-request-dump/`，仅在应用启动时
  `ENABLE_PUBLIC_REQUEST_DUMP=true` 才注册；关闭或未设置时返回 `404`，且不出现在
  OpenAPI 中。
- 端点不使用 Pydantic 输入 Schema、数据库或认证依赖。它读取原始请求字节，保留查询
  参数和 header 的顺序、重复项，并将客户端地址、请求元数据和正文以 JSON 回显。
- 正文同时提供 UTF-8 文本（无法解码的字节替换为 `�`）和 Base64；Base64 是原始字节的
  无损表示。
- 完整 JSON 使用 WARNING 级别写入应用日志。没有新增表、迁移、文件或外部服务调用。

此端点会接收、回显并记录 `Authorization`、Cookie、签名和正文等敏感信息，因此只能
短时开启用于受控调试。部署时应额外通过反向代理或网络策略限制来源，调试结束后将开关
恢复为 `false` 并重启服务。

## 3. 实施

- 在 `app/core/config.py` 增加默认关闭的开关。
- 在 `app/main.py` 应用组装阶段按开关注册路由。
- 在 `app/api/v1/endpoints/public_request_dump.py` 实现无鉴权的原始请求回显和结构化日志。
- Docker Compose 透传该开关；功能测试环境显式保持关闭。

## 4. 验证

- 单元测试验证：无 Authorization 时仍可调用；查询参数、header、非 UTF-8 正文和日志
  均能保留；开启开关时路由与 OpenAPI 出现。
- 运行 `./scripts/test.sh unit`，并运行 `./scripts/test.sh functional` 验证真实 HTTP
  环境默认不会暴露该接口。

## 5. 交付与回退

使用方式：在 `.env` 写入 `ENABLE_PUBLIC_REQUEST_DUMP=true` 并重启服务，然后向
`POST /api/v1/public-request-dump/` 发送任意请求。完成联调后设回 `false` 并重启，路由
会消失，无需数据库回退或数据清理。

实现与设计一致。已知限制是：端点刻意不限制请求大小，公开暴露时可能被滥用或导致敏感
数据进入日志；这也是默认关闭且建议只在受控网络短时使用的原因。
