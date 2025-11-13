# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **FastAPI-based RESTful API system** for collecting and managing user data, specifically:
- **Rest data tracking**: Sleep/wake time records with location and WiFi information
- **GTD (Getting Things Done) task management**
- **Multi-user support** with API Key authentication
- **External service integrations**: Notion API and Bark notifications

## Tech Stack

- **Framework**: FastAPI 0.104.1
- **Database**: PostgreSQL with SQLAlchemy 2.0.23 ORM
- **Migrations**: Alembic 1.12.1
- **Validation**: Pydantic 2.5.2
- **Authentication**: Python-jose (JWT), passlib (bcrypt)
- **Testing**: pytest 8.2.0, httpx, pytest-asyncio
- **Deployment**: Docker, Docker Compose
- **External APIs**: Notion client, Bark notifications

## Project Structure

```
app/
├── core/                    # Core configuration and shared utilities
│   ├── config.py           # Application settings (pydantic-settings)
│   ├── security.py         # Authentication & authorization
│   └── services/           # External service integrations
│       ├── bark_service.py # Bark notification service
│       └── notion_service.py # Notion API integration
├── api/
│   └── v1/
│       └── endpoints/      # API route handlers
│           ├── gtd.py      # GTD task management endpoints
│           └── rest_records.py # Rest data endpoints
├── models/                 # SQLAlchemy database models
│   ├── user.py
│   ├── rest_record.py      # Sleep/wake records
│   └── gtd_task.py         # GTD tasks
├── schemas/                # Pydantic models for validation
│   ├── rest_record.py
│   └── gtd_task.py
├── db/                     # Database configuration
│   ├── base_class.py       # Base model class
│   ├── session.py          # Database session management
│   └── init_db.py          # Database initialization
└── main.py                 # FastAPI application entry point
```

## Development Workflow

### This Project Uses "Spec-Driven Development"

**Critical**: This repository follows a strict **Spec Mode** workflow documented in `PROJECT_SPEC.md` and `QWEN.md`. When receiving feature requests:

1. **NEVER write code immediately** - First acknowledge the request
2. **Generate a spec proposal** with design doc and spec diff
3. **Wait for explicit approval** ("批准", "同意", "Approved")
4. Only then implement code following the approved design
5. Remind to update main spec after coding

See `PROJECT_SPEC.md:1-72` for complete instructions.

## Common Commands

### Development
```bash
# Start the application with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using Python directly
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Development
```bash
# Start all services (web + postgres)
docker-compose up -d

# View logs
docker-compose logs -f web
docker-compose logs -f db

# Stop services
docker-compose down
```

### Database Migrations
```bash
# Create a new migration
alembic revision --autogenerate -m "migration message"

# Apply migrations to database
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration
alembic current
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_bark_service.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app
```

### API Documentation
When the server is running, access:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json

## API Authentication

The API uses **Bearer Token** authentication:
- Include in request header: `Authorization: Bearer <token>`
- Tokens are validated against the `users` table
- See `app/core/security.py` for implementation

## Key API Endpoints

### Rest Records (作息记录)
- `POST /api/v1/rest-records/` - Create rest record (sleep/wake)
- `GET /api/v1/rest-records/` - Get user's rest records list

**Rest Types**:
- `0`: Sleep (睡眠)
- `1`: Wake Up (起床)

### GTD Tasks
- `POST /api/v1/gtd-tasks/` - Create new task
- `GET /api/v1/gtd-tasks/` - Get user's tasks

**Task Status**:
- `0`: Todo (待办)
- `1`: In Progress (进行中)
- `2`: Completed (已完成)
- `3`: Cancelled (已取消)

## Configuration

Configuration is managed via `.env` file (see `.env.example` for reference). Key settings:

- `POSTGRES_*` - Database connection parameters
- `NOTION_TOKEN` - Notion API integration token
- `NOTION_SLEEP_DATABASE_ID` - Notion database for sleep records
- `NOTION_WAKE_DATABASE_ID` - Notion database for wake records
- `NOTION_GTD_DATABASE_ID` - Notion database for GTD tasks
- `BARK_BASE_URL` - Bark notification service URL
- `BARK_DEFAULT_DEVICE_KEY` - Default Bark device key

Configuration class: `app/core/config.py:9-77`

## Database Architecture

**Models** (`app/models/`):
- `User` - User accounts with API key authentication
- `RestRecord` - Sleep/wake time records with location data
- `GtdTask` - GTD task management

**Base Class**: `app/db/base_class.py` - Provides common fields (id, created_at, updated_at)

**Sessions**: `app/db/session.py` - Database session management

**Initialization**: `app/db/init_db.py` - Auto-runs on startup (see `app/main.py:12-15`)

## External Service Integrations

### Notion Integration (`app/core/services/notion_service.py`)
- Async Notion client for creating pages in databases
- Sleep/wake records auto-sync to Notion databases
- GTD tasks can sync to Notion (optional)
- Retry logic (3 attempts) with failure notification

### Bark Notifications (`app/core/services/bark_service.py`)
- Push notification service for errors/alerts
- Sends notifications when Notion sync fails
- Configurable per user or globally

## CI/CD

**GitHub Actions** (`.github/workflows/build-push.yml`):
- Auto-builds and pushes Docker image to `lzyyauto/myservice:latest` on push to main branch
- Uses Docker Buildx and Docker Hub

## Testing Structure

```
tests/
├── conftest.py                    # Test configuration and fixtures
├── test_bark_service.py           # Unit tests for Bark service
└── integration/
    └── test_notion_service.py     # Integration tests for Notion service
```

## Key Implementation Details

### Async Operations
- Notion sync happens **asynchronously** after creating rest records (see `app/api/v1/endpoints/rest_records.py:74-102`)
- The API responds immediately; Notion sync runs in background
- Failed sync triggers Bark notification after 3 retries

### Database Timestamps
- Records use **Unix timestamps** (integer) for time fields
- `month_str` field stores formatted month (e.g., "11月") for quick queries
- See `app/models/rest_record.py:20-25` for defaults

### CORS Configuration
- CORS is enabled for all origins (`*`) in `app/main.py:44-50`
- Suitable for development; review for production

## Development Tips

1. **Database Changes**: Always create Alembic migrations, never modify database directly
2. **API Changes**: Update both model (`models/`) and schema (`schemas/`) files
3. **Testing**: Add tests for new services in appropriate test files
4. **External APIs**: Handle failures gracefully (see Notion service retry pattern)
5. **Environment**: Copy `.env.example` to `.env` and configure before running

## Important Files Reference

- **App Entry**: `app/main.py`
- **Config**: `app/core/config.py`
- **Auth**: `app/core/security.py`
- **API Routes**: `app/api/v1/endpoints/`
- **Models**: `app/models/`
- **Specs**: `PROJECT_SPEC.md`, `QWEN.md`
- **Docker**: `docker-compose.yml`, `Dockerfile`
- **Tests**: `tests/`
