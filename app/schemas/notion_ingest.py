"""Notion 标准页面载荷采集的 API Schema。"""

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotionParent(BaseModel):
    type: Literal["database_id"]
    database_id: str = Field(..., min_length=1, max_length=200)


class NotionIngestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    parent: NotionParent
    properties: dict[str, dict[str, Any]] = Field(..., min_length=1)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=200)

    def notion_payload(self) -> dict[str, Any]:
        """去除本系统传输字段后，得到可直接交给 Notion 的页面请求。"""
        return self.model_dump(mode="json", exclude={"idempotency_key"})


class NotionIngestResponse(BaseModel):
    event_id: UUID
    delivery_id: UUID
    business_type: Optional[str] = None
    mapping_name: Optional[str] = None
    delivery_status: str
    duplicate: bool = False


class NotionDatabaseMappingUpsert(BaseModel):
    business_type: Literal["exercise"]
    display_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)


class NotionDatabaseMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notion_database_id: str
    business_type: str
    display_name: str
    description: Optional[str] = None
