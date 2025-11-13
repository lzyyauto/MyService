# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🎯 Project Overview

**Z收集系统 (Z Collection System)** - A FastAPI-based RESTful API system for collecting and managing user data.

**Primary Features:**
- **Rest Health Management**: Sleep/wake time tracking with Notion sync
- **GTD Task Management**: Task creation with Todo/In Progress/Completed/Cancelled states
- **Video Processing**: Douyin video parsing, download, audio extraction, speech-to-text, and AI summarization
- **Notifications**: Bark push notifications for alerts

## 🏗 Architecture

### Core Stack
- **Backend**: FastAPI 0.104.1 with async support
- **Database**: PostgreSQL + SQLAlchemy 2.0 + Alembic migrations
- **Auth**: JWT (python-jose) + bcrypt
- **Validation**: Pydantic 2.5.2

### Directory Structure
```
app/
├── api/v1/endpoints/      # API routing
│   ├── rest_records.py    # Sleep/wake records
│   ├── gtd.py            # GTD tasks
│   └── video_process.py  # Video processing (3 endpoints)
├── core/                 # Core modules
│   ├── config.py         # Settings (loads from .env)
│   ├── security.py       # JWT authentication
│   └── services/         # External integrations
│       ├── bark_service.py     # Bark notifications
│       ├── notion_service.py   # Notion API sync
│       └── video_processor_service.py  # Video processing with parse logging
├── db/                   # Database
│   ├── session.py        # DB session manager
│   └── init_db.py        # DB initialization
├── models/               # SQLAlchemy models
│   ├── user.py          # User model
│   ├── rest_record.py   # Sleep/wake records
│   ├── gtd_task.py      # GTD tasks
│   └── video_process_task.py  # Video tasks (has task_type field)
├── schemas/              # Pydantic schemas for validation
└── utils/                # Utilities
    └── ai_client.py     # AI service clients (SiliconFlow/OpenAI)

alembic/
└── versions/             # Database migrations
```

## 🚀 Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run with Docker
docker-compose up -d

# View API docs
open http://localhost:8000/docs
```

### Database
```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# View migration history
alembic history
```

### Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
# - Database: POSTGRES_HOST, USER, PASSWORD, DB
# - Notion: NOTION_TOKEN, *_DATABASE_ID
# - Bark: BARK_DEFAULT_DEVICE_KEY
# - AI: AI_PROVIDER (siliconflow/openai), SILICONFLOW_API_KEY
# - Video: THIRD_PARTY_DOUYIN_API_URL, FFMPEG_PATH
```

## 🔌 API Endpoints

### Authentication
All endpoints require JWT token in header:
```
Authorization: Bearer <token>
```

### Core Modules
**1. Rest Records** (`/api/v1/rest-records`)
- `POST /` - Create sleep/wake record
- `GET /` - List records

**2. GTD Tasks** (`/api/v1/gtd-tasks`)
- `POST /` - Create task
- `GET /` - List tasks

**3. Video Processing** (`/api/v1/video-process`)
- `POST /` - Submit full video processing task (download → audio → ASR → AI summary)
- `GET /{task_id}` - Query task status/result
- `POST /parse-url` - Parse URL only (returns download links, supports video/image/Live Photo)

### Video Processing Details
- **Full Process**: Async task with 4 steps (video download, audio extraction, speech-to-text, AI summary)
- **Parse URL Only**: Quick parsing for download links (no processing)
- **Task Type**: Distinguishes between "process" and "parse" tasks via `task_type` field
- **Storage**: Results saved in database, files in `temp/video/` directory
- **Dependencies**: Requires ffmpeg and third-party Douyin API service

## ⚙️ Configuration

### Environment Variables (.env)
```env
# Core
APP_NAME=rest-data-collector
DEBUG=True/False
ENVIRONMENT=development/production

# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=myservice
POSTGRES_HOST=localhost  # or 'db' for Docker
POSTGRES_PORT=5432

# External Services
NOTION_TOKEN=secret_xxx
NOTION_SLEEP_DATABASE_ID=xxx
NOTION_WAKE_DATABASE_ID=xxx
NOTION_GTD_DATABASE_ID=xxx

BARK_BASE_URL=https://api.day.app
BARK_DEFAULT_DEVICE_KEY=xxx

# AI Services
AI_PROVIDER=siliconflow  # or openai
SILICONFLOW_API_KEY=sk-xxx
AI_VOICE_MODEL=FunAudioLLM/SenseVoiceSmall
AI_SUMMARY_MODEL=Qwen/QwQ-32B

# Video Processing
THIRD_PARTY_DOUYIN_API_URL=http://localhost:8088/api/hybrid/video_data
FFMPEG_PATH=/opt/homebrew/bin/ffmpeg
VIDEO_PROCESSING_TEMP_DIR=temp/video/
```

### Third-Party Dependencies
- **Douyin API**: External service at `THIRD_PARTY_DOUYIN_API_URL` for video parsing
- **ffmpeg**: Required for audio extraction (must be installed on system)
- **Notion API**: For optional data synchronization
- **Bark**: For push notifications
- **AI Services**: SiliconFlow (recommended) or OpenAI for speech-to-text and summarization

## 🗄 Database Schema

### Key Models
- **User**: JWT-authenticated users
- **RestRecord**: Sleep/wake time entries (Notion sync)
- **GtdTask**: GTD task management
- **VideoProcessTask**: Video processing tasks with fields:
  - `task_type`: "process" (full processing) or "parse" (URL only)
  - `media_type`: "video", "image", or "live_photo"
  - `aweme_id`, `desc`, `author`: Parse metadata
  - `download_urls`: List of download links
  - `video_path`, `audio_path`: File paths
  - `subtitle_text`, `ai_summary`: Processing results

### Migrations
Located in `alembic/versions/`. Recent migrations added task_type and parse fields for logging parse-url access.

## 🔐 Security

- JWT token authentication for all endpoints
- User-scoped data access (users can only access their own records/tasks)
- Password hashing with bcrypt
- Environment-based configuration for secrets
- CORS enabled for all origins (development setting)

## 📝 Development Notes

- **Project recently cleaned**: Documentation, test files, and temp directories removed
- **Video processing service**: Implements both full processing and parse-only URL functionality
- **Background tasks**: Uses FastAPI BackgroundTasks for async video processing
- **Logging**: Configured in `app/main.py` (app/main.py:12-21)
- **Parse URL logging**: Records parse accesses in database (app/core/services/video_processor_service.py)

## 🐛 Common Issues

1. **Database connection**: Ensure PostgreSQL is running and .env configured correctly
2. **ffmpeg not found**: Install ffmpeg and set FFMPEG_PATH in .env
3. **Third-party API down**: Video processing requires external Douyin API service
4. **AI API errors**: Check SILICONFLOW_API_KEY or OPENAI_API_KEY configuration
5. **Migration conflicts**: Reset with `alembic downgrade base && alembic upgrade head`

## 📦 Dependencies

Key packages from `requirements.txt`:
- fastapi, uvicorn - Web framework
- sqlalchemy, psycopg2-binary - ORM and PostgreSQL driver
- alembic - Database migrations
- pydantic, pydantic-settings - Validation and config
- python-jose, passlib - JWT and password hashing
- notion-client - Notion API integration
- aiohttp, requests - HTTP clients
- tenacity - Retry mechanism
- pytest* - Testing (optional, tests removed)
