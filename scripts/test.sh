#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-unit}"
FUNCTIONAL_TEST_PORT="${FUNCTIONAL_TEST_PORT:-18080}"
FUNCTIONAL_TEST_DB_PORT="${FUNCTIONAL_TEST_DB_PORT:-15432}"
COMPOSE_PROJECT_NAME="z-collection-functional-$$"

cd "$ROOT_DIR"

run_unit_tests() {
  echo "==> 同步锁定依赖"
  uv sync --locked
  echo "==> 执行 Python 编译检查"
  uv run python -m compileall -q app tests scripts
  local migration_head_count
  migration_head_count="$(uv run alembic heads | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
  if [[ "$migration_head_count" -ne 1 ]]; then
    echo "警告：Alembic 当前有 ${migration_head_count} 个 head，功能测试暂用空库 create_all。" >&2
    if [[ "${STRICT_MIGRATIONS:-0}" == "1" ]]; then
      echo "错误：STRICT_MIGRATIONS=1，不允许多个迁移 head。" >&2
      exit 1
    fi
  fi
  echo "==> 执行单元测试"
  uv run pytest tests/unit -m "not functional" \
    --cov=app.api.v1.endpoints.rest_records \
    --cov=app.core.security \
    --cov=app.services.inspiration \
    --cov=app.services.notion \
    --cov=app.services.bark \
    --cov-report=term-missing \
    --cov-fail-under=75
}

cleanup_functional_stack() {
  if [[ "${KEEP_TEST_STACK:-0}" == "1" ]]; then
    echo "==> KEEP_TEST_STACK=1，保留功能测试容器"
    return
  fi
  docker compose \
    -p "$COMPOSE_PROJECT_NAME" \
    -f docker-compose.functional.yml \
    down --volumes --remove-orphans
}

run_functional_tests() {
  command -v docker >/dev/null || {
    echo "错误：功能测试需要 Docker。" >&2
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo "错误：Docker daemon 未运行。" >&2
    exit 1
  }

  uv sync --locked
  export FUNCTIONAL_TEST_PORT FUNCTIONAL_TEST_DB_PORT
  export FUNCTIONAL_TEST_BASE_URL="http://127.0.0.1:${FUNCTIONAL_TEST_PORT}"
  trap cleanup_functional_stack EXIT

  echo "==> 启动一次性 PostgreSQL 与 FastAPI"
  echo "    Compose 项目：${COMPOSE_PROJECT_NAME}"
  docker compose \
    -p "$COMPOSE_PROJECT_NAME" \
    -f docker-compose.functional.yml \
    up --build --detach

  echo "==> 执行真实 HTTP 与跨组件功能测试"
  uv run pytest tests/functional -m functional -o addopts=
}

case "$MODE" in
  unit)
    run_unit_tests
    ;;
  functional)
    run_functional_tests
    ;;
  all)
    run_unit_tests
    run_functional_tests
    ;;
  *)
    echo "用法：$0 [unit|functional|all]" >&2
    exit 2
    ;;
esac
