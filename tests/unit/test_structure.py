from app.db.base_class import Base

# 兼容保留的 GTD、视频表也必须注册，避免 Alembic 误判为应删除旧表。
import app.models  # noqa: F401, E402


def test_all_models_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "exercise_records",
        "gtd_tasks",
        "notion_database_mappings",
        "notion_deliveries",
        "notion_ingest_events",
        "rest_records",
        "users",
        "video_process_tasks",
    }
