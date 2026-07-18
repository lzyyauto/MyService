from app.db.base_class import Base

# 导入模型包后，所有业务表都应注册到同一个 MetaData。
import app.models  # noqa: F401, E402


def test_all_models_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "gtd_tasks",
        "rest_records",
        "users",
        "video_process_tasks",
    }
