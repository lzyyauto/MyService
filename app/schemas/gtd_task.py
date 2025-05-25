from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, validator


class GtdTaskBase(BaseModel):
    name: str = Field(..., description="任务名称", min_length=1, max_length=100)
    start_time: int = Field(..., description="开始时间戳")
    end_time: int = Field(..., description="结束时间戳")
    priority: int = Field(0, ge=0, le=10, description="优先级：0-10，数字越大优先级越高")
    category: str = Field(..., description="任务分类", min_length=1, max_length=50)
    status: int = Field(0,
                        ge=0,
                        le=3,
                        description="任务状态：0-待办，1-进行中，2-已完成，3-已取消")

    @validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('结束时间必须晚于开始时间')
        return v


class GtdTaskCreate(GtdTaskBase):
    pass


class GtdTaskInDB(GtdTaskBase):
    id: UUID = Field(..., description="任务ID")
    user_id: str = Field(..., description="用户ID")
    created_at: int = Field(..., description="创建时间戳")
    updated_at: int = Field(..., description="更新时间戳")

    class Config:
        from_attributes = True


class GtdTask(GtdTaskInDB):
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @validator('start_time', 'end_time', 'created_at', 'updated_at', pre=True)
    def convert_timestamp_to_datetime(cls, v):
        if isinstance(v, int):
            return datetime.fromtimestamp(v)
        return v

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.strftime('%Y-%m-%d %H:%M:%S')}
