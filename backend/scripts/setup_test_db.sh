#!/usr/bin/env bash
# 初始化隔离的测试数据库 algo_tutor_test。
#
# 幂等：已存在则跳过创建，已应用 migrations 则 alembic upgrade head 是 no-op。
#
# 用法：bash backend/scripts/setup_test_db.sh
set -euo pipefail

TEST_DB="algo_tutor_test"
PG_USER="algo_tutor"

echo "Ensuring test database '$TEST_DB' exists..."

# 检查测试库是否已存在
if docker compose exec -T postgres psql -U "$PG_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$TEST_DB'" | grep -q 1; then
    echo "  Test database already exists, skipping creation."
else
    docker compose exec -T postgres psql -U "$PG_USER" -d postgres -c "CREATE DATABASE $TEST_DB;"
    echo "  Created test database '$TEST_DB'."
fi

# 确保 pgvector 扩展存在（幂等）
echo "Ensuring pgvector extension..."
docker compose exec -T postgres psql -U "$PG_USER" -d "$TEST_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 应用 migrations 到测试库（DATABASE_URL 覆盖指向测试库）
echo "Applying Alembic migrations to test database..."
docker compose exec -e DATABASE_URL="postgresql+asyncpg://$PG_USER:algo_tutor_secret@postgres:5432/$TEST_DB" backend alembic upgrade head

echo "Test database ready. Run tests with:"
echo "  bash backend/scripts/run_tests.sh"
