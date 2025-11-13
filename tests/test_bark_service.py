from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.services.bark_service import BarkService


@pytest.fixture
def bark_service():
    """创建 Bark 服务实例"""
    if not settings.BARK_DEFAULT_DEVICE_KEY:
        pytest.skip("BARK_DEFAULT_DEVICE_KEY not set")
    return BarkService(base_url=settings.BARK_BASE_URL,
                       default_device_key=settings.BARK_DEFAULT_DEVICE_KEY)


@pytest.mark.asyncio
async def test_send_notification_success(bark_service):
    """测试发送通知成功"""
    # 模拟 aiohttp.ClientSession 的响应
    mock_response = AsyncMock()
    mock_response.status = 200

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await bark_service.send_notification(title="测试标题",
                                                      content="测试内容",
                                                      device_key="test_key",
                                                      level="active",
                                                      sound="bell",
                                                      group="test_group")

        assert result is True
        # 验证请求 URL 和参数
        mock_session.__aenter__.return_value.get.assert_called_once()
        call_args = mock_session.__aenter__.return_value.get.call_args
        assert "test_key/测试标题/测试内容" in str(call_args[0][0])
        assert call_args[1]["params"]["level"] == "active"
        assert call_args[1]["params"]["sound"] == "bell"
        assert call_args[1]["params"]["group"] == "test_group"


@pytest.mark.asyncio
async def test_send_notification_failure(bark_service):
    """测试发送通知失败"""
    # 模拟请求异常
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value.get.side_effect = Exception("网络错误")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await bark_service.send_notification(title="测试标题",
                                                      content="测试内容")

        assert result is False


@pytest.mark.asyncio
async def test_send_notification_missing_device_key(bark_service):
    """测试缺少设备 key 的情况"""
    # 创建没有默认 device_key 的服务实例
    service = BarkService(base_url="https://api.day.app")

    with pytest.raises(ValueError, match="device_key is required"):
        await service.send_notification(title="测试标题", content="测试内容")


@pytest.mark.asyncio
async def test_send_rest_notification(bark_service):
    """测试发送休息记录通知"""
    with patch.object(bark_service,
                      "send_notification",
                      new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # 测试睡眠记录
        result = await bark_service.send_rest_notification(
            device_key="test_key", rest_type=0, location="北京 家里")

        assert result is True
        mock_send.assert_called_once_with(title="睡眠提醒",
                                          content="记录睡眠时间\n位置：北京 家里",
                                          device_key="test_key",
                                          level="timeSensitive",
                                          sound="bell",
                                          group="rest_records")

        # 测试起床记录
        mock_send.reset_mock()
        result = await bark_service.send_rest_notification(
            device_key="test_key", rest_type=1)

        assert result is True
        mock_send.assert_called_once_with(title="起床提醒",
                                          content="记录起床时间",
                                          device_key="test_key",
                                          level="timeSensitive",
                                          sound="bell",
                                          group="rest_records")


@pytest.mark.asyncio
async def test_send_task_notification(bark_service):
    """测试发送任务通知"""
    with patch.object(bark_service,
                      "send_notification",
                      new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # 测试高优先级任务
        result = await bark_service.send_task_notification(
            device_key="test_key", task_name="重要任务", status=1, priority=8)

        assert result is True
        mock_send.assert_called_once_with(
            title="任务状态更新：进行中",
            content="任务：重要任务\n优先级：8",
            device_key="test_key",
            level="active",  # 高优先级使用 active 级别
            sound="bell",
            group="gtd_tasks")

        # 测试低优先级任务
        mock_send.reset_mock()
        result = await bark_service.send_task_notification(
            device_key="test_key", task_name="普通任务", status=0, priority=5)

        assert result is True
        mock_send.assert_called_once_with(
            title="任务状态更新：待办",
            content="任务：普通任务\n优先级：5",
            device_key="test_key",
            level="timeSensitive",  # 低优先级使用 timeSensitive 级别
            sound="bell",
            group="gtd_tasks")


@pytest.mark.asyncio
async def test_real_bark_notification(bark_service):
    """测试真实发送 Bark 通知"""
    result = await bark_service.send_notification(title="测试通知",
                                                  content="这是一条测试通知\n来自集成测试",
                                                  level="active",
                                                  sound="bell",
                                                  group="test")
    assert result is True


@pytest.mark.asyncio
async def test_real_rest_notification(bark_service):
    """测试真实发送休息记录通知"""
    result = await bark_service.send_rest_notification(
        device_key=settings.BARK_DEFAULT_DEVICE_KEY,
        rest_type=0,  # 睡眠
        location="测试位置")
    assert result is True


@pytest.mark.asyncio
async def test_real_task_notification(bark_service):
    """测试真实发送任务通知"""
    result = await bark_service.send_task_notification(
        device_key=settings.BARK_DEFAULT_DEVICE_KEY,
        task_name="测试任务",
        status=1,  # 进行中
        priority=8  # 高优先级
    )
    assert result is True
