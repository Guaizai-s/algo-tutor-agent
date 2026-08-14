$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
docker compose --project-directory $repoRoot exec -T backend python -m scripts.reset_demo

if ($LASTEXITCODE -ne 0) {
    throw "Demo reset failed with exit code $LASTEXITCODE"
}
