import logging

from sqlalchemy import inspect, text

from app.db.base_class import Base
from app.db.session import engine
# 导入模型包以注册全部表；不要删除这个导入。
import app.models  # noqa: F401


logger = logging.getLogger(__name__)


def _repair_legacy_notion_mapping_table() -> None:
    """补齐早期 create_all 创建的映射表列，保留已有映射行。

    ``create_all`` 只会创建缺失的表，不会给已存在表增加列。早期本地环境曾创建过仅含
    database ID 的 ``notion_database_mappings``，因此在读取新映射模型前需要做一次窄范围
    的兼容升级。正式 Alembic 升级仍应在备份后单独执行。
    """
    with engine.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("notion_database_mappings"):
            return

        existing_columns = {
            column["name"] for column in inspector.get_columns("notion_database_mappings")
        }
        additions = {
            "business_type": "VARCHAR",
            "display_name": "VARCHAR",
            "description": "TEXT",
            "mapper_key": "VARCHAR",
            "created_at": "BIGINT",
            "updated_at": "BIGINT",
        }
        missing_columns = [name for name in additions if name not in existing_columns]
        if not missing_columns:
            return

        logger.warning(
            "检测到旧版 notion_database_mappings，正在补齐列：%s",
            ", ".join(missing_columns),
        )
        for column_name in missing_columns:
            connection.execute(
                text(
                    "ALTER TABLE notion_database_mappings "
                    f"ADD COLUMN {column_name} {additions[column_name]}"
                )
            )

        # 旧表没有业务语义。当前唯一支持的稳定业务类型是 exercise，原有映射行按此兼容，
        # 用户仍可通过 PUT 显式更新显示名称与说明。
        if "business_type" in missing_columns:
            connection.execute(
                text(
                    "UPDATE notion_database_mappings "
                    "SET business_type = 'exercise' "
                    "WHERE business_type IS NULL"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE notion_database_mappings "
                    "ALTER COLUMN business_type SET NOT NULL"
                )
            )
        if "display_name" in missing_columns:
            connection.execute(
                text(
                    "UPDATE notion_database_mappings "
                    "SET display_name = notion_database_id "
                    "WHERE display_name IS NULL"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE notion_database_mappings "
                    "ALTER COLUMN display_name SET NOT NULL"
                )
            )
        if "mapper_key" in missing_columns:
            connection.execute(
                text(
                    "UPDATE notion_database_mappings "
                    "SET mapper_key = 'exercise_notion_v1' "
                    "WHERE mapper_key IS NULL"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE notion_database_mappings "
                    "ALTER COLUMN mapper_key SET NOT NULL"
                )
            )
        for column_name in ("created_at", "updated_at"):
            if column_name in missing_columns:
                connection.execute(
                    text(
                        "UPDATE notion_database_mappings "
                        f"SET {column_name} = EXTRACT(EPOCH FROM NOW())::BIGINT "
                        f"WHERE {column_name} IS NULL"
                    )
                )
                connection.execute(
                    text(
                        "ALTER TABLE notion_database_mappings "
                        f"ALTER COLUMN {column_name} SET NOT NULL"
                    )
                )


def _repair_legacy_notion_event_tables() -> None:
    """补齐早期本地采集表遗漏的列，不改写已有事件或投递内容。"""
    table_columns = {
        "notion_ingest_events": {
            "notion_database_id": "VARCHAR",
            "idempotency_key": "VARCHAR",
            "business_type": "VARCHAR",
            "mapping_display_name": "VARCHAR",
            "mapper_key": "VARCHAR",
            "original_payload": "JSONB",
            "created_at": "BIGINT",
        },
        "exercise_records": {
            "source_event_id": "UUID",
            "exercise_type": "VARCHAR",
            "duration": "DOUBLE PRECISION",
            "occurred_at": "TIMESTAMP WITH TIME ZONE",
            "occurred_on": "DATE",
            "month_str": "VARCHAR",
            "city": "VARCHAR",
            "created_at": "BIGINT",
            "updated_at": "BIGINT",
        },
        "notion_deliveries": {
            "event_id": "UUID",
            "notion_payload": "JSONB",
            "status": "VARCHAR",
            "attempt_count": "INTEGER",
            "next_attempt_at": "BIGINT",
            "locked_until": "BIGINT",
            "notion_page_id": "VARCHAR",
            "last_error": "TEXT",
            "created_at": "BIGINT",
            "updated_at": "BIGINT",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, additions in table_columns.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            missing_columns = [name for name in additions if name not in existing_columns]
            if not missing_columns:
                continue
            logger.warning(
                "检测到旧版 %s，正在补齐列：%s",
                table_name,
                ", ".join(missing_columns),
            )
            for column_name in missing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {additions[column_name]}"
                    )
                )


def init_db() -> None:
    # 创建缺失表；再对早期 create_all 留下的旧 Notion 表做窄范围兼容升级。
    Base.metadata.create_all(bind=engine)
    _repair_legacy_notion_mapping_table()
    _repair_legacy_notion_event_tables()
