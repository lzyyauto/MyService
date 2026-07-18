from sqlalchemy.orm import Session

from app.db.base_class import Base
from app.db.session import engine
# 导入模型包以注册全部表；不要删除这个导入。
import app.models  # noqa: F401


def init_db() -> None:
    # 创建所有表
    Base.metadata.create_all(bind=engine)
