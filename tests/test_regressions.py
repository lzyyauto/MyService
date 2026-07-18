from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.rest_records import get_rest_records
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
async def test_notion_gtd_title_uses_task_name() -> None:
    service = NotionService(token="test-token")
    service.create_page = AsyncMock(return_value="page-id")
    task = {
        "name": "跑步",
        "status": 0,
        "priority": 5,
        "category": "运动",
        "start_time": 1_700_000_000,
        "end_time": 1_700_003_600,
    }

    result = await service.add_gtd_task("database-id", task)

    assert result == "page-id"
    service.create_page.assert_awaited_once()
    assert service.create_page.await_args.kwargs["title_property"] == "名称"
    assert service.create_page.await_args.kwargs["title_content"] == "跑步"


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
