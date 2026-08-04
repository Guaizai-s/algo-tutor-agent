#!/usr/bin/env bash
# 运行后端测试套件（含 slow 测试）。
#
# 自动设置 TEST_DATABASE_URL 指向隔离的测试库 algo_tutor_test，
# 避免污染开发库。测试库需预先创建并应用 migrations（见 scripts/setup_test_db.sh）。
#
# 用法：
#   bash backend/scripts/run_tests.sh           # 常规测试（跳过 slow）
#   bash backend/scripts/run_tests.sh --slow    # 含 slow 测试（需真实 Redis）
#   bash backend/scripts/run_tests.sh -- -k cf  # 传递额外 pytest 参数
set -euo pipefail

SLOW=""
PYTEST_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --slow) SLOW="1"; shift ;;
        --) shift; PYTEST_ARGS+=("$@"); break ;;
        *) PYTEST_ARGS+=("$1"); shift ;;
    esac
done

TEST_DB_URL="postgresql+asyncpg://algo_tutor:algo_tutor_secret@postgres:5432/algo_tutor_test"

# 检查测试库是否可达
if ! docker compose exec -T postgres psql -U algo_tutor -d algo_tutor_test -c "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: 测试库 algo_tutor_test 不存在或不可达。请先运行："
    echo "  bash backend/scripts/setup_test_db.sh"
    exit 1
fi

if [[ -n "$SLOW" ]]; then
    echo "Running tests (with slow)..."
    docker compose exec -e TEST_DATABASE_URL="$TEST_DB_URL" backend python -m pytest -m "slow or not slow" "${PYTEST_ARGS[@]}"
else
    echo "Running tests (excluding slow)..."
    docker compose exec -e TEST_DATABASE_URL="$TEST_DB_URL" backend python -m pytest "${PYTEST_ARGS[@]}"
fi
