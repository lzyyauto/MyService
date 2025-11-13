"""
AI客户端测试 - 正确的Mock示例
展示如何正确mock异步上下文管理器
"""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import pytest
import httpx

from app.core.config import settings
from app.utils.ai_client import SiliconFlowClient


class TestCorrectMockExample:
    """正确的Mock示例"""

    @pytest.mark.asyncio
    async def test_summarize_text_CORRECT(self):
        """
        正确的Mock方式：需要mock异步上下文管理器
        关键点：
        1. httpx.AsyncClient 是异步上下文管理器 (async with)
        2. 需要mock __aenter__ 和 __aexit__ 方法
        3. response.json() 是同步方法
        """
        client = SiliconFlowClient()

        # 1. 创建mock response对象 (同步的)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "这是AI生成的总结内容"
                    }
                }
            ]
        }

        # 2. 正确mock异步上下文管理器
        with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
            # 创建mock客户端实例
            mock_client_instance = AsyncMock()

            # 设置post方法的返回值
            mock_client_instance.post.return_value = mock_response

            # 关键：mock __aenter__ 方法返回我们的mock客户端实例
            mock_async_context_manager = AsyncMock()
            mock_async_context_manager.__aenter__.return_value = mock_client_instance
            mock_async_context_manager.__aexit__.return_value = None

            # 让AsyncClient()返回我们的异步上下文管理器
            mock_client_class.return_value = mock_async_context_manager

            # 3. 执行测试
            result = await client.summarize_text("这是一段测试文字")

            # 4. 验证结果
            assert result == "这是AI生成的总结内容"
            assert mock_client_instance.post.called

            # 验证调用参数
            call_args = mock_client_instance.post.call_args
            assert "/chat/completions" in call_args[0][0]
            assert settings.AI_SUMMARY_MODEL in call_args[1]["json"]["model"]

    @pytest.mark.asyncio
    async def test_recognize_speech_CORRECT(self):
        """
        正确的文件上传mock示例
        """
        client = SiliconFlowClient()

        # 创建临时音频文件
        temp_audio = Path("/tmp/test_audio.mp3")
        temp_audio.write_bytes(b"fake audio data")

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "识别出的文字"
        }

        try:
            with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
                # 创建mock客户端
                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response

                # Mock异步上下文管理器
                mock_async_context_manager = AsyncMock()
                mock_async_context_manager.__aenter__.return_value = mock_client_instance
                mock_async_context_manager.__aexit__.return_value = None

                mock_client_class.return_value = mock_async_context_manager

                # 执行测试
                result = await client.recognize_speech(temp_audio)

                # 验证
                assert result == "识别出的文字"
                assert mock_client_instance.post.called

                # 验证文件上传参数
                call_args = mock_client_instance.post.call_args
                assert "/audio/transcriptions" in call_args[0][0]
        finally:
            # 清理临时文件
            if temp_audio.exists():
                temp_audio.unlink()

    @pytest.mark.asyncio
    async def test_with_open_file_CORRECT(self):
        """
        正确mock open() 和 文件上传
        """
        client = SiliconFlowClient()
        temp_audio = Path("/tmp/test_upload.mp3")
        temp_audio.write_bytes(b"audio data")

        try:
            with patch("builtins.open", create=True) as mock_open, \
                 patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:

                # Mock file handle
                mock_file_handle = MagicMock()
                mock_open.return_value.__aenter__.return_value = mock_file_handle

                # Mock response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"text": "结果"}

                # Mock客户端
                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response

                mock_async_context_manager = AsyncMock()
                mock_async_context_manager.__aenter__.return_value = mock_client_instance
                mock_async_context_manager.__aexit__.return_value = None

                mock_client_class.return_value = mock_async_context_manager

                # 执行
                result = await client.recognize_speech(temp_audio)

                # 验证
                assert result == "结果"
                assert mock_open.called
                assert mock_client_instance.post.called

        finally:
            if temp_audio.exists():
                temp_audio.unlink()


class TestAlternativeApproach:
    """
    替代方案：使用MagicMock的完整配置
    这种方式更简单，但需要理解Mock的工作原理
    """

    @pytest.mark.asyncio
    async def test_simplified_mock(self):
        """
        简化的Mock方式：直接mock整个httpx模块
        优点：简单直接
        缺点：可能过于宽泛
        """
        client = SiliconFlowClient()

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "总结"}}]
        }

        # 直接mock AsyncClient作为上下文管理器
        mock_async_cm = MagicMock()
        mock_async_cm.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_response)))
        mock_async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("app.utils.ai_client.httpx.AsyncClient", return_value=mock_async_cm):
            result = await client.summarize_text("测试")

            assert result == "总结"


class TestCommonMistakes:
    """
    常见错误示例和修正
    """

    @pytest.mark.asyncio
    async def test_common_mistake_Wrong(self):
        """
        ❌ 错误示例：将json()设置为AsyncMock
        问题：response.json()应该是同步的，但被设为异步协程
        """
        client = SiliconFlowClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"content": "错误"})  # ❌ 错误

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            try:
                await client.summarize_text("测试")
                assert False, "应该失败但没有"
            except TypeError as e:
                assert "'coroutine' object is not subscriptable" in str(e)

    @pytest.mark.asyncio
    async def test_common_mistake_Wrong2(self):
        """
        ❌ 错误示例：只mock post方法，不mock上下文管理器
        问题：代码使用了 async with httpx.AsyncClient()
        """
        client = SiliconFlowClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "错误"}}]}

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            try:
                await client.summarize_text("测试")
                assert False, "应该失败但没有"
            except AttributeError as e:
                assert "AsyncClient" in str(e)
