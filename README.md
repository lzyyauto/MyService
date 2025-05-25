# 休息数据收集系统

基于FastAPI构建的RESTful API系统，用于收集和管理用户的休息数据。

## 系统功能

- 休息数据收集（睡眠/起床时间记录）
- 地理位置和WiFi信息记录
- 多用户支持
- Authorization认证
- Docker容器化部署

## 系统模块

- `app/core`: 核心配置和认证
- `app/api`: API路由和接口
- `app/models`: 数据库模型
- `app/schemas`: 数据验证模型
- `app/db`: 数据库配置和会话管理

## 技术栈

- FastAPI
- SQLAlchemy
- PostgreSQL
- Docker
- Pydantic

## 快速开始

```bash
# 使用Docker Compose启动
docker-compose up -d
```

访问 http://localhost:8000/docs 查看API文档。

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 开发

### 项目结构
```
app/
├── core/          # 核心配置
├── api/           # API路由
├── models/        # 数据库模型
└── schemas/       # Pydantic模型
```

### 数据库迁移
```bash
# 创建迁移
alembic revision --autogenerate -m "migration message"

# 应用迁移
alembic upgrade head
```

## 测试
```bash
pytest
```

## 许可证

MIT 