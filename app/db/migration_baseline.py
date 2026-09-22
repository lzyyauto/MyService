"""为历史 Alembic 链路补齐未版本化的 ``users`` 基表。

项目最早的数据库由 ``Base.metadata.create_all`` 初始化，之后才开始记录 Alembic
migration。因此历史 revision 会引用 ``users.id``，但仓库内没有创建 ``users`` 的
初始 migration。这个小型、幂等的兼容步骤只在该表缺失时创建它；绝不执行完整的
``create_all``，也不会修改已有用户数据或替代后续 Alembic migration。
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app.models.user import User


def _database_url() -> str | URL:
    """与 Alembic 环境保持相同的连接配置优先级。"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "rest_data"),
    )


def ensure_legacy_users_table() -> None:
    """仅在空库缺少 ``users`` 时创建历史迁移所依赖的基础表。"""
    engine = create_engine(_database_url())
    try:
        User.__table__.create(bind=engine, checkfirst=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    ensure_legacy_users_table()
