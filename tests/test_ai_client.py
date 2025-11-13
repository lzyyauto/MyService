"""
AI客户端测试
测试硅基AI和OpenAI客户端的各种功能
"""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import pytest
import httpx

from app.core.config import settings
from app.utils.ai_client import (
    SiliconFlowClient,
    OpenAIClient,
    get_ai_client
)


class TestSiliconFlowClient:
    """硅基AI客户端测试"""

    @pytest.fixture
    def siliconflow_client(self):
        """创建硅基AI客户端实例"""
        # 如果没有API密钥，跳过测试
        if not settings.SILICONFLOW_API_KEY:
            pytest.skip("SILICONFLOW_API_KEY not set")
        return SiliconFlowClient()

    @pytest.mark.asyncio
    async def test_initialization(self):
        """测试客户端初始化"""
        client = SiliconFlowClient()
        assert client.api_key == settings.SILICONFLOW_API_KEY
        assert client.base_url == "https://api.siliconflow.cn/v1"
        assert client.voice_model == "FunAudioLLM/SenseVoiceSmall"
        assert client.summary_model == settings.AI_SUMMARY_MODEL

    @pytest.mark.asyncio
    async def test_summarize_text_success(self):
        """测试文本总结成功"""
        client = SiliconFlowClient()

        # 模拟httpx响应
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

        with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response

            # 正确mock异步上下文管理器
            mock_async_cm = AsyncMock()
            mock_async_cm.__aenter__.return_value = mock_client
            mock_async_cm.__aexit__.return_value = None

            mock_client_class.return_value = mock_async_cm

            result = await client.summarize_text("这是一段测试文字")

            # 验证调用
            assert mock_client.post.called
            call_args = mock_client.post.call_args
            assert "/chat/completions" in call_args[0][0]
            assert settings.AI_SUMMARY_MODEL in call_args[1]["json"]["model"]
            assert "这是一段测试文字" in call_args[1]["json"]["messages"][0]["content"]
            assert result == "这是AI生成的总结内容"

    @pytest.mark.asyncio
    async def test_summarize_text_failure(self):
        """测试文本总结失败"""
        client = SiliconFlowClient()

        # 模拟API错误响应
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(Exception, match="硅基AI文本总结失败"):
                await client.summarize_text("测试文字")

    @pytest.mark.asyncio
    async def test_summarize_text_with_max_length(self):
        """测试带最大长度限制的文本总结"""
        client = SiliconFlowClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "简短总结"
                    }
                }
            ]
        }

        with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response

            mock_async_cm = AsyncMock()
            mock_async_cm.__aenter__.return_value = mock_client
            mock_async_cm.__aexit__.return_value = None

            mock_client_class.return_value = mock_async_cm

            result = await client.summarize_text("测试文字", max_length=100)

            call_args = mock_client.post.call_args
            assert "（请控制在100字以内）" in call_args[1]["json"]["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_recognize_speech_with_file(self):
        """测试语音识别 - 模拟文件上传"""
        client = SiliconFlowClient()

        # 创建临时音频文件
        temp_audio = Path("/tmp/test_audio.mp3")
        temp_audio.write_bytes(b"fake audio data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "这是识别出的文字内容"
        }

        try:
            with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response

                mock_async_cm = AsyncMock()
                mock_async_cm.__aenter__.return_value = mock_client
                mock_async_cm.__aexit__.return_value = None

                mock_client_class.return_value = mock_async_cm

                result = await client.recognize_speech(temp_audio)

                # 验证调用
                assert mock_client.post.called
                call_args = mock_client.post.call_args
                assert "/audio/transcriptions" in call_args[0][0]
                assert "FunAudioLLM/SenseVoiceSmall" in call_args[1]["data"]["model"]
                assert result == "这是识别出的文字内容"
        finally:
            # 清理
            temp_audio.unlink()

    @pytest.mark.asyncio
    async def test_recognize_speech_api_error(self):
        """测试语音识别API错误"""
        client = SiliconFlowClient()

        temp_audio = Path("/tmp/test_audio.mp3")
        temp_audio.write_bytes(b"fake audio data")

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(Exception, match="硅基AI语音识别失败"):
                await client.recognize_speech(temp_audio)

            # 清理
            temp_audio.unlink()

    @pytest.mark.asyncio
    async def test_recognize_speech_empty_response(self):
        """测试语音识别空响应"""
        client = SiliconFlowClient()

        temp_audio = Path("/tmp/test_audio.mp3")
        temp_audio.write_bytes(b"fake audio data")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # 空响应

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(Exception, match="硅基AI语音识别失败"):
                await client.recognize_speech(temp_audio)

            # 清理
            temp_audio.unlink()


class TestOpenAIClient:
    """OpenAI客户端测试"""

    @pytest.mark.asyncio
    async def test_initialization_without_api_key(self):
        """测试没有API密钥的初始化"""
        # 临时覆盖配置
        with patch.object(settings, 'OPENAI_API_KEY', None):
            client = OpenAIClient()
            assert client.api_key is None
            assert client.base_url == "https://api.openai.com/v1"
            assert client.voice_model == "whisper-1"
            assert client.summary_model == "gpt-4"

    @pytest.mark.asyncio
    async def test_summarize_text_success(self):
        """测试OpenAI文本总结"""
        client = OpenAIClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OpenAI生成的总结"
                    }
                }
            ]
        }

        with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response

            mock_async_cm = AsyncMock()
            mock_async_cm.__aenter__.return_value = mock_client
            mock_async_cm.__aexit__.return_value = None

            mock_client_class.return_value = mock_async_cm

            result = await client.summarize_text("测试文字")

            assert result == "OpenAI生成的总结"

    @pytest.mark.asyncio
    async def test_recognize_speech_with_file(self):
        """测试OpenAI语音识别"""
        client = OpenAIClient()

        temp_audio = Path("/tmp/test_audio_openai.mp3")
        temp_audio.write_bytes(b"fake audio data")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "识别出的文字"

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            result = await client.recognize_speech(temp_audio)

            assert result == "识别出的文字"

            # 清理
            temp_audio.unlink()


class TestAIClientFactory:
    """AI客户端工厂测试"""

    @pytest.mark.asyncio
    async def test_get_siliconflow_client(self):
        """测试获取硅基AI客户端"""
        # 确保配置为siliconflow
        with patch.object(settings, 'AI_PROVIDER', 'siliconflow'):
            with patch.object(settings, 'SILICONFLOW_API_KEY', 'test_key'):
                client = get_ai_client()
                assert isinstance(client, SiliconFlowClient)
                assert client.api_key == 'test_key'

    @pytest.mark.asyncio
    async def test_get_openai_client(self):
        """测试获取OpenAI客户端"""
        with patch.object(settings, 'AI_PROVIDER', 'openai'):
            with patch.object(settings, 'OPENAI_API_KEY', 'test_key'):
                client = get_ai_client()
                assert isinstance(client, OpenAIClient)
                assert client.api_key == 'test_key'

    @pytest.mark.asyncio
    async def test_get_client_without_key(self):
        """测试未配置API密钥的情况"""
        with patch.object(settings, 'AI_PROVIDER', 'siliconflow'):
            with patch.object(settings, 'SILICONFLOW_API_KEY', None):
                with pytest.raises(ValueError, match="SILICONFLOW_API_KEY 未配置"):
                    get_ai_client()

    @pytest.mark.asyncio
    async def test_get_client_unsupported_provider(self):
        """测试不支持的AI提供商"""
        with patch.object(settings, 'AI_PROVIDER', 'unsupported'):
            with pytest.raises(ValueError, match="不支持的AI提供商"):
                get_ai_client()

    @pytest.mark.asyncio
    async def test_client_switching(self):
        """测试客户端切换"""
        # 第一次获取硅基AI
        with patch.object(settings, 'AI_PROVIDER', 'siliconflow'):
            with patch.object(settings, 'SILICONFLOW_API_KEY', 'key1'):
                client1 = get_ai_client()
                assert isinstance(client1, SiliconFlowClient)

        # 切换到OpenAI
        with patch.object(settings, 'AI_PROVIDER', 'openai'):
            with patch.object(settings, 'OPENAI_API_KEY', 'key2'):
                client2 = get_ai_client()
                assert isinstance(client2, OpenAIClient)
                assert client2.api_key == 'key2'


class TestAIClientIntegration:
    """AI客户端集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_text_processing(self):
        """端到端文本处理测试"""
        client = SiliconFlowClient()

        # 模拟完整的处理流程
        input_text = """
        今天我学习了一个新的技术概念，叫做人工智能。
        人工智能可以帮助我们自动化许多重复性的工作。
        通过机器学习，计算机可以从数据中学习并做出预测。
        这项技术正在改变我们的生活方式。
        """

        # 模拟AI总结响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "总结：\n1. 学习人工智能技术\n2. AI能自动化重复工作\n3. 机器学习可预测\n4. 改变生活方式"
                    }
                }
            ]
        }

        with patch("app.utils.ai_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response

            mock_async_cm = AsyncMock()
            mock_async_cm.__aenter__.return_value = mock_client
            mock_async_cm.__aexit__.return_value = None

            mock_client_class.return_value = mock_async_cm

            result = await client.summarize_text(input_text, max_length=200)

            assert result is not None
            assert len(result) > 0
            assert "总结" in result or "1." in result or "AI" in result
