import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class RestRecord(Base):
    __tablename__ = "rest_records"

    # 休息类型常量
    REST_TYPE_SLEEP = 0
    REST_TYPE_WAKE_UP = 1

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    rest_type = Column(Integer, nullable=False)  # 0: SLEEP, 1: WAKE_UP
    rest_time = Column(BigInteger,
                       nullable=False,
                       default=lambda: int(datetime.now().timestamp()))
    month_str = Column(String,
                       nullable=False,
                       default=lambda: datetime.now().strftime('%m月'))
    wifi_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    city = Column(String, nullable=True)
    created_at = Column(BigInteger,
                        default=lambda: int(datetime.utcnow().timestamp()),
                        nullable=False)
    updated_at = Column(BigInteger,
                        default=lambda: int(datetime.utcnow().timestamp()),
                        onupdate=lambda: int(datetime.utcnow().timestamp()),
                        nullable=False)
