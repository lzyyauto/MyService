from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.rest_records import get_rest_records
from app.services.bark import BarkService
from app.services.notion import NotionService


@pytest.mark.asyncio
async def test_rest_record_list_applies_pagination() -> None:
    records = [SimpleNamespace(id="record-1")]
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = records

    result = await get_rest_records(
        db=db,
        current_user=SimpleNamespace(id="user-1"),
        skip=5,
        limit=10,
    )

    assert result == records
    query.filter.return_value.order_by.return_value.offset.assert_called_once_with(5)
    query.filter.return_value.order_by.return_value.offset.return_value.limit.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_notion_rest_title_uses_month() -> None:
    service = NotionService(token="test-token")
    service.create_page = AsyncMock(return_value="page-id")
    record = {
        "month_str": "07月",
        "rest_time": 1_700_000_000,
        "city": "上海",
    }

    result = await service.add_rest_record("database-id", record)

    assert result == "page-id"
    service.create_page.assert_awaited_once()
    assert service.create_page.await_args.kwargs["title_property"] == "月份"
    assert service.create_page.await_args.kwargs["title_content"] == "07月"


@pytest.mark.asyncio
async def test_bark_requires_device_key() -> None:
    service = BarkService(base_url="https://example.test")

    with pytest.raises(ValueError, match="device_key"):
        await service.send_notification("标题", "内容")


@pytest.mark.asyncio
async def test_notion_create_page_formats_active_properties() -> None:
    service = NotionService(token="test-token")
    service.client.pages.create = MagicMock(return_value={"id": "page-id"})

    result = await service.create_page(
        database_id="database-id",
        properties={
            "月份": {"type": "title", "value": "07月"},
            "城市": {"type": "text", "value": "上海"},
            "时长": {"type": "number", "value": 8},
        },
        title_property="月份",
        title_content="07月",
    )

    assert result == "page-id"
    properties = service.client.pages.create.call_args.kwargs["properties"]
    assert properties["月份"]["title"][0]["text"]["content"] == "07月"
    assert properties["城市"]["rich_text"][0]["text"]["content"] == "上海"
    assert properties["时长"]["number"] == 8.0


@pytest.mark.asyncio
async def test_notion_create_page_returns_none_on_client_error() -> None:
    service = NotionService(token="test-token")
    service.client.pages.create = MagicMock(side_effect=RuntimeError("offline"))

    result = await service.create_page(
        database_id="database-id",
        properties={"月份": {"type": "title", "value": "07月"}},
    )

    assert result is None


@pytest.mark.asyncio
async def test_notion_create_page_from_payload_forwards_standard_request() -> None:
    service = NotionService(token="test-token")
    service.client.pages.create = MagicMock(return_value={"id": "page-id"})
    payload = {
        "parent": {"type": "database_id", "database_id": "database-id"},
        "properties": {"名称": {"title": []}},
    }

    assert await service.create_page_from_payload(payload) == "page-id"
    service.client.pages.create.assert_called_once_with(**payload)


@pytest.mark.asyncio
async def test_bark_rest_notification_builds_expected_message() -> None:
    service = BarkService(base_url="https://example.test")
    service.send_notification = AsyncMock(return_value=True)

    result = await service.send_rest_notification(
        device_key="device",
        rest_type=0,
        location="上海",
    )

    assert result is True
    service.send_notification.assert_awaited_once_with(
        title="睡眠提醒",
        content="记录睡眠时间\n位置：上海",
        device_key="device",
        level="timeSensitive",
        sound="bell",
        group="rest_records",
    )
