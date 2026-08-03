param(
    [switch]$Slow
)

# Run backend test suite with TEST_DATABASE_URL auto-set to algo_tutor_test.
# Provision test DB first: scripts/setup_test_db.ps1
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File backend/scripts/run_tests.ps1                  # default (skip slow)
#   powershell -ExecutionPolicy Bypass -File backend/scripts/run_tests.ps1 -Slow             # include slow tests (needs real Redis)
#   powershell -ExecutionPolicy Bypass -File backend/scripts/run_tests.ps1 -k cf_sync        # extra pytest args
$ErrorActionPreference = "Stop"

$TestDbUrl = "postgresql+asyncpg://algo_tutor:algo_tutor_secret@postgres:5432/algo_tutor_test"

# Check test DB reachable
docker compose exec -T postgres psql -U algo_tutor -d algo_tutor_test -c "SELECT 1" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: test DB algo_tutor_test not reachable. Run first:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File backend/scripts/setup_test_db.ps1"
    exit 1
}

# Build pytest args list
$pytestArgs = @()

if ($Slow) {
    Write-Host "Running tests (with slow)..."
    $pytestArgs = $pytestArgs + "-m"
    $pytestArgs = $pytestArgs + "slow or not slow"
} else {
    Write-Host "Running tests (excluding slow)..."
}

# Append extra args
foreach ($a in $args) {
    $pytestArgs = $pytestArgs + $a
}

Write-Host ("pytest args: " + ($pytestArgs -join " "))

docker compose exec -e TEST_DATABASE_URL="$TestDbUrl" backend python -m pytest $pytestArgs
