import os
from datetime import datetime

import pytest

from app.core.config import settings
from app.core.services.notion_service import NotionService
from app.models.rest_record import RestRecord
from app.schemas.rest_record import RestRecordCreate

# 使用配置文件中的值
NOTION_TOKEN = settings.NOTION_TOKEN
NOTION_DATABASE_ID = settings.NOTION_REST_DATABASE_ID

# 打印配置信息（不打印完整 token）
print(f"NOTION_TOKEN 是否存在: {bool(NOTION_TOKEN)}")
print(f"NOTION_DATABASE_ID: {NOTION_DATABASE_ID}")

pytestmark = pytest.mark.skipif(
    not all([NOTION_TOKEN, NOTION_DATABASE_ID]),
    reason="需要设置 NOTION_TOKEN 和 NOTION_REST_DATABASE_ID 环境变量")


@pytest.fixture
def notion_service():
    return NotionService(token=NOTION_TOKEN)


@pytest.fixture
def rest_record_data():
    now = int(datetime.now().timestamp())
    return {
        "rest_time": now,
        "rest_type": 0,  # 睡眠
        "city": "深圳",
        "longitude": 114.0579,
        "latitude": 22.5431,
        "wifi_name": "Home WiFi"
    }


@pytest.mark.asyncio
async def test_add_rest_record_with_dict(notion_service, rest_record_data):
    """测试使用字典添加休息记录"""
    page_id = await notion_service.add_rest_record(
        database_id=NOTION_DATABASE_ID, record=rest_record_data)
    assert page_id is not None
    print(f"创建的 Notion 页面 ID: {page_id}")


@pytest.mark.asyncio
async def test_add_rest_record_with_model(notion_service, rest_record_data):
    """测试使用 RestRecord 模型添加休息记录"""
    # 创建 RestRecord 模型实例
    record = RestRecord(user_id="test_user", **rest_record_data)

    page_id = await notion_service.add_rest_record(
        database_id=NOTION_DATABASE_ID, record=record)
    assert page_id is not None
    print(f"使用模型创建的 Notion 页面 ID: {page_id}")


@pytest.mark.asyncio
async def test_add_rest_record_with_schema(notion_service, rest_record_data):
    """测试使用 RestRecordSchema 添加休息记录"""
    # 创建 RestRecordCreate schema 实例
    record = RestRecordCreate(**rest_record_data)

    page_id = await notion_service.add_rest_record(
        database_id=NOTION_DATABASE_ID, record=record)
    assert page_id is not None
    print(f"使用 schema 创建的 Notion 页面 ID: {page_id}")
