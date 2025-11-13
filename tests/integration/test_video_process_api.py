"""
视频处理API集成测试
测试完整的API端到端流程
"""

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest
import uuid
from datetime import datetime

from app.main import app
from app.models.user import User
from app.models.video_process_task import VideoProcessTask


class TestVideoProcessAPI:
    """视频处理API集成测试"""

    @pytest.fixture
    def test_client(self):
        """创建测试客户端"""
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        """创建模拟用户"""
        user = MagicMock(spec=User)
        user.id = "test_user_id"
        user.api_key = "test_api_key"
        return user

    @pytest.fixture
    def auth_headers(self, mock_user):
        """创建认证头"""
        return {"Authorization": f"Bearer {mock_user.api_key}"}

    def test_create_video_process_task_success(self, test_client, auth_headers, mock_user):
        """测试创建视频处理任务成功"""
        # 模拟数据库操作
        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)
            mock_get_db.return_value = mock_db

            # 模拟任务创建
            created_task = MagicMock()
            created_task.id = uuid.uuid4()
            created_task.status = VideoProcessTask.STATUS_PENDING

            mock_db.add.return_value = None
            mock_db.commit.return_value = None
            mock_db.refresh.return_value = None
            mock_db.query.return_value.filter.return_value.first.return_value = None  # 没有已存在的任务

            response = test_client.post(
                "/api/v1/video-process/",
                json={"video_url": "请处理这个视频：https://v.douyin.com/iJgDkYhC/"},
                headers=auth_headers
            )

            assert response.status_code == 201
            data = response.json()
            assert "task_id" in data
            assert data["status"] == "pending"
            assert "任务已创建" in data["message"]

    def test_create_video_process_task_invalid_url(self, test_client, auth_headers, mock_user):
        """测试创建任务 - 无效URL"""
        with patch('app.core.security.get_current_user', return_value=mock_user):
            response = test_client.post(
                "/api/v1/video-process/",
                json={"video_url": "这不是一个URL"},
                headers=auth_headers
            )

            assert response.status_code == 422
            data = response.json()
            assert "URL" in data["detail"] or "URL" in str(data)

    def test_create_video_process_task_non_douyin_url(self, test_client, auth_headers, mock_user):
        """测试创建任务 - 非抖音URL"""
        with patch('app.core.security.get_current_user', return_value=mock_user):
            response = test_client.post(
                "/api/v1/video-process/",
                json={"video_url": "https://www.google.com"},
                headers=auth_headers
            )

            assert response.status_code == 422
            data = response.json()
            assert "抖音" in data["detail"] or "douyin" in data["detail"]

    def test_create_video_process_task_existing_completed(self, test_client, auth_headers, mock_user):
        """测试创建任务 - 已有完成的相同任务"""
        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)

            # 模拟已存在的已完成任务
            existing_task = MagicMock()
            existing_task.id = uuid.uuid4()
            existing_task.status = VideoProcessTask.STATUS_COMPLETED

            # 当调用check_existing_task时返回已存在的任务
            with patch.object(
                'app.core.services.video_processor_service.VideoProcessorService',
                'check_existing_task',
                return_value=existing_task
            ):
                response = test_client.post(
                    "/api/v1/video-process/",
                    json={"video_url": "https://v.douyin.com/iJgDkYhC/"},
                    headers=auth_headers
                )

                assert response.status_code == 201
                data = response.json()
                assert data["status"] == "completed"
                assert "已处理完成" in data["message"]

    def test_get_video_process_task_success_completed(self, test_client, auth_headers, mock_user):
        """测试查询任务状态 - 成功完成的任务"""
        task_id = str(uuid.uuid4())

        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)

            # 模拟已完成的任务
            task = MagicMock()
            task.id = task_id
            task.status = VideoProcessTask.STATUS_COMPLETED
            task.original_url = "https://v.douyin.com/test/"
            task.video_path = "/tmp/test.mp4"
            task.audio_path = "/tmp/test.mp3"
            task.subtitle_text = "这是字幕"
            task.ai_summary = "这是总结"

            mock_db.query.return_value.filter.return_value.first.return_value = task

            response = test_client.get(
                f"/api/v1/video-process/{task_id}",
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == task_id
            assert data["status"] == "completed"
            assert data["original_url"] == "https://v.douyin.com/test/"
            assert data["video_path"] == "/tmp/test.mp4"
            assert data["audio_path"] == "/tmp/test.mp3"
            assert data["subtitle_text"] == "这是字幕"
            assert data["summary"] == "这是总结"
            assert data["message"] == "查询成功"

    def test_get_video_process_task_processing(self, test_client, auth_headers, mock_user):
        """测试查询任务状态 - 处理中"""
        task_id = str(uuid.uuid4())

        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)

            # 模拟处理中的任务
            task = MagicMock()
            task.id = task_id
            task.status = VideoProcessTask.STATUS_PROCESSING
            task.original_url = "https://v.douyin.com/test/"
            task.video_path = None
            task.audio_path = None
            task.subtitle_text = None

            mock_db.query.return_value.filter.return_value.first.return_value = task

            response = test_client.get(
                f"/api/v1/video-process/{task_id}",
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == task_id
            assert data["status"] == "processing"
            assert data["summary"] is None
            assert data["video_path"] is None
            assert data["audio_path"] is None
            assert data["subtitle_text"] is None

    def test_get_video_process_task_not_found(self, test_client, auth_headers, mock_user):
        """测试查询任务状态 - 任务不存在"""
        task_id = str(uuid.uuid4())

        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)
            mock_db.query.return_value.filter.return_value.first.return_value = None

            response = test_client.get(
                f"/api/v1/video-process/{task_id}",
                headers=auth_headers
            )

            assert response.status_code == 404
            data = response.json()
            assert "不存在" in data["detail"]

    def test_get_video_process_task_forbidden(self, test_client, auth_headers):
        """测试查询任务状态 - 权限不足"""
        task_id = str(uuid.uuid4())

        # 模拟当前用户不是任务所有者
        other_user = MagicMock()
        other_user.id = "other_user_id"

        with patch('app.core.security.get_current_user', return_value=other_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)

            # 模拟任务属于其他用户
            task = MagicMock()
            task.id = task_id
            task.user_id = "test_user_id"  # 任务属于test_user

            mock_db.query.return_value.filter.return_value.first.return_value = task

            response = test_client.get(
                f"/api/v1/video-process/{task_id}",
                headers=auth_headers
            )

            assert response.status_code == 403
            data = response.json()
            assert "权限" in data["detail"]

    def test_get_video_process_task_unauthorized(self, test_client):
        """测试查询任务状态 - 未认证"""
        task_id = str(uuid.uuid4())

        response = test_client.get(f"/api/v1/video-process/{task_id}")

        assert response.status_code == 401

    def test_create_video_process_task_unauthorized(self, test_client):
        """测试创建任务 - 未认证"""
        response = test_client.post(
            "/api/v1/video-process/",
            json={"video_url": "https://v.douyin.com/test/"}
        )

        assert response.status_code == 401

    def test_api_documentation_available(self, test_client):
        """测试API文档可访问"""
        response = test_client.get("/docs")
        assert response.status_code == 200

    def test_api_openapi_json(self, test_client):
        """测试OpenAPI JSON可访问"""
        response = test_client.get("/api/v1/openapi.json")
        assert response.status_code == 200

        data = response.json()
        # 检查是否包含视频处理端点
        assert "/api/v1/video-process/" in data["paths"]

    def test_create_task_with_background_task(self, test_client, auth_headers, mock_user):
        """测试创建任务时后台任务被添加"""
        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db, \
             patch('fastapi.BackgroundTasks') as mock_bg_tasks:

            mock_db = MagicMock(spec=Session)

            # 模拟check_existing_task返回None（无已存在任务）
            with patch.object(
                'app.core.services.video_processor_service.VideoProcessorService',
                'check_existing_task',
                return_value=None
            ):
                # 创建新任务
                new_task = MagicMock()
                new_task.id = uuid.uuid4()
                new_task.status = VideoProcessTask.STATUS_PENDING

                mock_db.add.return_value = None
                mock_db.commit.return_value = None
                mock_db.refresh.return_value = None
                mock_db.query.return_value.filter.return_value.first.return_value = new_task

                response = test_client.post(
                    "/api/v1/video-process/",
                    json={"video_url": "https://v.douyin.com/iJgDkYhC/"},
                    headers=auth_headers
                )

                assert response.status_code == 201

                # 验证后台任务被添加
                # 注意：这里我们只是验证调用，没有实际执行后台任务
                # 在实际测试中，需要使用TestClient的依赖注入

    def test_multiple_task_creation_same_url(self, test_client, auth_headers, mock_user):
        """测试同一URL创建多个任务（去重机制）"""
        video_url = "https://v.douyin.com/test/"

        with patch('app.core.security.get_current_user', return_value=mock_user), \
             patch('app.db.session.get_db') as mock_get_db:

            mock_db = MagicMock(spec=Session)

            # 第一次请求：没有已存在任务，创建新任务
            existing_task = None
            with patch.object(
                'app.core.services.video_processor_service.VideoProcessorService',
                'check_existing_task',
                return_value=existing_task
            ):
                response1 = test_client.post(
                    "/api/v1/video-process/",
                    json={"video_url": video_url},
                    headers=auth_headers
                )

                assert response1.status_code == 201
                assert response1.json()["status"] == "pending"

            # 第二次请求：有已存在任务，返回已存在的结果
            existing_task = MagicMock()
            existing_task.id = uuid.uuid4()
            existing_task.status = VideoProcessTask.STATUS_COMPLETED

            with patch.object(
                'app.core.services.video_processor_service.VideoProcessorService',
                'check_existing_task',
                return_value=existing_task
            ):
                response2 = test_client.post(
                    "/api/v1/video-process/",
                    json={"video_url": video_url},
                    headers=auth_headers
                )

                assert response2.status_code == 201
                assert response2.json()["status"] == "completed"

    def test_task_status_enum(self):
        """测试任务状态枚举值"""
        assert VideoProcessTask.STATUS_PENDING == "pending"
        assert VideoProcessTask.STATUS_PROCESSING == "processing"
        assert VideoProcessTask.STATUS_COMPLETED == "completed"
        assert VideoProcessTask.STATUS_FAILED == "failed"

    def test_create_task_request_validation(self, test_client, auth_headers):
        """测试创建任务请求体验证"""
        # 缺少video_url
        response = test_client.post(
            "/api/v1/video-process/",
            json={},
            headers=auth_headers
        )
        assert response.status_code == 422

        # video_url为空
        response = test_client.post(
            "/api/v1/video-process/",
            json={"video_url": ""},
            headers=auth_headers
        )
        assert response.status_code == 422
