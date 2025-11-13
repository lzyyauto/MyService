"""
视频处理服务测试
测试完整的视频处理流程
"""

from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from pathlib import Path
import pytest
import asyncio
from sqlalchemy.orm import Session

from app.core.services.video_processor_service import VideoProcessorService
from app.models.video_process_task import VideoProcessTask


class TestVideoProcessorService:
    """视频处理服务测试"""

    @pytest.fixture
    def mock_db(self):
        """创建模拟数据库"""
        return MagicMock(spec=Session)

    @pytest.fixture
    def processor(self, mock_db):
        """创建视频处理服务实例"""
        return VideoProcessorService(mock_db)

    @pytest.fixture
    def sample_task(self, mock_db):
        """创建示例任务"""
        task = MagicMock(spec=VideoProcessTask)
        task.id = "550e8400-e29b-41d4-a716-446655440000"
        task.user_id = "test_user"
        task.status = VideoProcessTask.STATUS_PENDING
        task.video_path = None
        task.audio_path = None
        task.subtitle_text = None
        task.ai_summary = None
        task.error_message = None

        mock_db.query.return_value.filter.return_value.first.return_value = task
        return task

    @pytest.mark.asyncio
    async def test_initialization(self, mock_db):
        """测试服务初始化"""
        processor = VideoProcessorService(mock_db)

        assert processor.db == mock_db
        assert processor.temp_dir == Path("temp/video")
        assert processor.ffmpeg_path  # ffmpeg路径存在即可（可能是绝对路径）

    @pytest.mark.asyncio
    async def test_process_video_success_flow(self, processor, sample_task, mock_db):
        """测试视频处理成功流程"""
        # 模拟各步骤返回值
        video_path = Path("/tmp/test_video.mp4")
        audio_path = Path("/tmp/test_audio.mp3")
        subtitle_text = "这是识别出的字幕文字"
        ai_summary = "这是AI生成的总结"

        # 使用AsyncMock来模拟download_video方法
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=audio_path), \
             patch.object(processor, '_recognize_speech', return_value=subtitle_text), \
             patch.object(processor, '_generate_summary', return_value=ai_summary), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            # 验证结果
            assert result["success"] is True
            assert result["task_id"] == str(sample_task.id)
            assert result["video_path"] == str(video_path)
            assert result["audio_path"] == str(audio_path)
            assert result["subtitle_text"] == subtitle_text
            assert result["ai_summary"] == ai_summary

            # 验证数据库更新
            assert sample_task.status == VideoProcessTask.STATUS_COMPLETED
            assert sample_task.video_path == str(video_path)
            assert sample_task.audio_path == str(audio_path)
            assert sample_task.subtitle_text == subtitle_text
            assert sample_task.ai_summary == ai_summary

            # 验证Bark未发送（因为成功）
            mock_bark.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_video_download_failure(self, processor, sample_task, mock_db):
        """测试视频下载失败"""
        download_mock = AsyncMock(return_value=None)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is False
            assert "视频下载失败" in result["error"]
            assert sample_task.status == VideoProcessTask.STATUS_FAILED
            mock_bark.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_extract_audio_failure(self, processor, sample_task, mock_db):
        """测试音频提取失败"""
        video_path = Path("/tmp/test_video.mp4")
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=None), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is False
            assert "音频提取失败" in result["error"]
            mock_bark.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_recognize_speech_failure(self, processor, sample_task, mock_db):
        """测试语音识别失败"""
        video_path = Path("/tmp/test_video.mp4")
        audio_path = Path("/tmp/test_audio.mp3")
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=audio_path), \
             patch.object(processor, '_recognize_speech', side_effect=Exception("识别失败")), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is False
            assert "语音识别" in result["error"]
            mock_bark.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_empty_subtitle(self, processor, sample_task, mock_db):
        """测试语音识别返回空结果"""
        video_path = Path("/tmp/test_video.mp4")
        audio_path = Path("/tmp/test_audio.mp3")
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=audio_path), \
             patch.object(processor, '_recognize_speech', return_value=""), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is False
            assert "语音识别失败" in result["error"] or "返回空结果" in result["error"]
            mock_bark.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_summary_failure(self, processor, sample_task, mock_db):
        """测试AI总结失败"""
        video_path = Path("/tmp/test_video.mp4")
        audio_path = Path("/tmp/test_audio.mp3")
        subtitle_text = "测试字幕"
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=audio_path), \
             patch.object(processor, '_recognize_speech', return_value=subtitle_text), \
             patch.object(processor, '_generate_summary', side_effect=Exception("总结失败")), \
             patch.object(processor.bark_service, 'send_notification') as mock_bark:

            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is False
            assert "AI总结" in result["error"]
            mock_bark.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_bark_notification_failure(self, processor, sample_task, mock_db):
        """测试Bark通知发送失败"""
        video_path = Path("/tmp/test_video.mp4")
        audio_path = Path("/tmp/test_audio.mp3")
        subtitle_text = "测试字幕"
        ai_summary = "测试总结"
        download_mock = AsyncMock(return_value=video_path)

        with patch.object(processor, 'download_video', download_mock), \
             patch.object(processor, '_extract_audio', return_value=audio_path), \
             patch.object(processor, '_recognize_speech', return_value=subtitle_text), \
             patch.object(processor, '_generate_summary', return_value=ai_summary), \
             patch.object(processor.bark_service, 'send_notification', side_effect=Exception("Bark error")):

            # 即使Bark失败，处理也应该成功
            result = await processor.process_video(
                task_id=str(sample_task.id),
                video_url="https://v.douyin.com/test/"
            )

            assert result["success"] is True
            assert sample_task.status == VideoProcessTask.STATUS_COMPLETED

    @pytest.mark.asyncio
    async def test_extract_audio_success(self, processor):
        """测试音频提取成功"""
        video_path = Path("/tmp/test_video.mp4")
        expected_audio_path = Path("temp/video/test_video.mp3")

        # 模拟ffmpeg存在
        with patch('shutil.which', return_value="/usr/bin/ffmpeg"), \
             patch('asyncio.create_subprocess_exec') as mock_subprocess, \
             patch('pathlib.Path.exists', return_value=True):

            # 模拟subprocess返回成功
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await processor._extract_audio(video_path)

            assert result is not None
            assert result.name == "test_video.mp3"

            # 验证ffmpeg命令
            call_args = mock_subprocess.call_args
            assert "ffmpeg" in str(call_args)
            assert str(video_path) in str(call_args)
            assert "-vn" in str(call_args)  # 不包含视频
            assert "mp3" in str(call_args)  # MP3格式

    @pytest.mark.asyncio
    async def test_extract_audio_ffmpeg_not_found(self, processor):
        """测试ffmpeg未找到"""
        video_path = Path("/tmp/test_video.mp4")

        with patch('shutil.which', return_value=None):
            result = await processor._extract_audio(video_path)

            assert result is None

    @pytest.mark.asyncio
    async def test_extract_audio_subprocess_error(self, processor):
        """测试ffmpeg执行错误"""
        video_path = Path("/tmp/test_video.mp4")

        with patch('shutil.which', return_value="/usr/bin/ffmpeg"), \
             patch('asyncio.create_subprocess_exec') as mock_subprocess, \
             patch('pathlib.Path.exists', return_value=False):

            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"ffmpeg error")
            mock_subprocess.return_value = mock_process

            result = await processor._extract_audio(video_path)

            assert result is None

    @pytest.mark.asyncio
    async def test_extract_audio_no_output_file(self, processor):
        """测试ffmpeg未生成输出文件"""
        video_path = Path("/tmp/test_video.mp4")

        with patch('shutil.which', return_value="/usr/bin/ffmpeg"), \
             patch('asyncio.create_subprocess_exec') as mock_subprocess, \
             patch('pathlib.Path.exists', return_value=False):

            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await processor._extract_audio(video_path)

            assert result is None

    @pytest.mark.asyncio
    async def test_recognize_speech(self, processor):
        """测试语音识别"""
        audio_path = Path("/tmp/test_audio.mp3")
        expected_text = "这是识别出的文字"

        with patch('app.utils.ai_client.get_ai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.recognize_speech.return_value = expected_text
            mock_get_client.return_value = mock_client

            result = await processor._recognize_speech(audio_path)

            assert result == expected_text
            mock_client.recognize_speech.assert_called_once_with(audio_path)

    @pytest.mark.asyncio
    async def test_generate_summary(self, processor):
        """测试AI总结"""
        text = "这是测试文字"
        expected_summary = "这是AI总结"

        with patch('app.utils.ai_client.get_ai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.summarize_text.return_value = expected_summary
            mock_get_client.return_value = mock_client

            result = await processor._generate_summary(text)

            assert result == expected_summary
            mock_client.summarize_text.assert_called_once_with(text)

    @pytest.mark.asyncio
    async def test_check_existing_task_found(self, processor, mock_db):
        """测试检查已存在任务 - 找到"""
        video_url = "https://v.douyin.com/test/"
        existing_task = MagicMock(spec=VideoProcessTask)
        existing_task.id = "existing_task_id"
        existing_task.status = VideoProcessTask.STATUS_COMPLETED

        with patch.object(processor, 'extract_video_url', return_value="https://v.douyin.com/test/"):
            mock_db.query.return_value.filter.return_value.first.return_value = existing_task

            result = processor.check_existing_task(video_url)

            assert result == existing_task

    @pytest.mark.asyncio
    async def test_check_existing_task_not_found(self, processor, mock_db):
        """测试检查已存在任务 - 未找到"""
        video_url = "https://v.douyin.com/test/"

        with patch.object(processor, 'extract_video_url', return_value="https://v.douyin.com/test/"):
            mock_db.query.return_value.filter.return_value.first.return_value = None

            result = processor.check_existing_task(video_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_check_existing_task_no_video_url(self, processor, mock_db):
        """测试检查已存在任务 - 提取不到视频URL"""
        video_url = "invalid_url"

        with patch.object(processor, 'extract_video_url', return_value=None):
            result = processor.check_existing_task(video_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_temp_files(self, processor):
        """测试清理临时文件"""
        # 创建临时文件
        temp_dir = processor.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        test_file1 = temp_dir / "task1_video.mp4"
        test_file2 = temp_dir / "task1_audio.mp3"
        test_file3 = temp_dir / "other_file.mp4"

        test_file1.write_bytes(b"test")
        test_file2.write_bytes(b"test")
        test_file3.write_bytes(b"test")

        await processor.cleanup_temp_files("task1")

        assert not test_file1.exists()
        assert not test_file2.exists()
        assert test_file3.exists()  # 其他文件应该保留

        # 清理
        test_file3.unlink()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_with_subdirs(self, processor):
        """测试清理临时文件（含子目录）"""
        temp_dir = processor.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        subdir = temp_dir / "subdir"
        subdir.mkdir(exist_ok=True)

        test_file = subdir / "task1_video.mp4"
        test_file.write_bytes(b"test")

        await processor.cleanup_temp_files("task1")

        assert not test_file.exists()

        # 清理
        subdir.rmdir()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_not_exists(self, processor):
        """测试清理不存在的临时文件"""
        # 不应该抛出异常
        await processor.cleanup_temp_files("nonexistent_task")

    def test_task_not_found_error(self, processor):
        """测试任务不存在错误"""
        with pytest.raises(ValueError, match="任务不存在"):
            asyncio.run(processor.process_video("nonexistent", "url"))
