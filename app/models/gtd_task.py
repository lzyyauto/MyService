import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class GtdTask(Base):
    __tablename__ = "gtd_tasks"

    # 任务状态常量
    STATUS_TODO = 0
    STATUS_DOING = 1
    STATUS_DONE = 2
    STATUS_CANCELLED = 3

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String,
                     ForeignKey("users.id"),
                     nullable=False,
                     index=True,
                     comment="用户ID")
    name = Column(String, nullable=False, comment="任务名称")
    start_time = Column(BigInteger, nullable=False, comment="开始时间戳")
    end_time = Column(BigInteger, nullable=False, comment="结束时间戳")
    priority = Column(Integer,
                      nullable=False,
                      default=0,
                      comment="优先级，数字越大优先级越高")
    category = Column(String, nullable=False, comment="任务分类")
    status = Column(Integer,
                    nullable=False,
                    default=STATUS_TODO,
                    comment="任务状态：0-待办，1-进行中，2-已完成，3-已取消")
    created_at = Column(BigInteger,
                        default=lambda: int(datetime.utcnow().timestamp()),
                        nullable=False)
    updated_at = Column(BigInteger,
                        default=lambda: int(datetime.utcnow().timestamp()),
                        onupdate=lambda: int(datetime.utcnow().timestamp()),
                        nullable=False)
