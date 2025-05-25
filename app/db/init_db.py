from sqlalchemy.orm import Session

from app.db.base_class import Base
from app.db.session import engine
from app.models.rest_record import RestRecord
from app.models.user import User


def init_db() -> None:
    # 创建所有表
    Base.metadata.create_all(bind=engine)
