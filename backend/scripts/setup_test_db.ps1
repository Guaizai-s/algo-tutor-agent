# Initialize isolated test database algo_tutor_test.
# Idempotent: skips creation if exists; alembic upgrade head is no-op if already applied.
# PowerShell version (equivalent to setup_test_db.sh).
#
# Usage: powershell -ExecutionPolicy Bypass -File backend/scripts/setup_test_db.ps1
$ErrorActionPreference = "Stop"

$TestDb = "algo_tutor_test"
$PgUser = "algo_tutor"

Write-Host "Ensuring test database '$TestDb' exists..."

$exists = docker compose exec -T postgres psql -U $PgUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$TestDb'"
if ($exists -match "1") {
    Write-Host "  Test database already exists, skipping creation."
} else {
    docker compose exec -T postgres psql -U $PgUser -d postgres -c "CREATE DATABASE $TestDb;"
    Write-Host "  Created test database '$TestDb'."
}

# Ensure pgvector extension (idempotent)
Write-Host "Ensuring pgvector extension..."
docker compose exec -T postgres psql -U $PgUser -d $TestDb -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Apply migrations to test DB (override DATABASE_URL to point to test DB)
Write-Host "Applying Alembic migrations to test database..."
$testDbUrl = "postgresql+asyncpg://$PgUser" + ":algo_tutor_secret@postgres:5432/$TestDb"
docker compose exec -e DATABASE_URL=$testDbUrl backend alembic upgrade head

Write-Host "Test database ready. Run tests with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File backend/scripts/run_tests.ps1"
