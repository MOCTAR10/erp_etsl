# rebuild_db.ps1 - Recree la base dediee etls_e2e (migrate + seed_all_demo complet).
#
# Utilisation :
#   & .\scripts\regression\rebuild_db.ps1
#
# A appeler AVANT chaque run de regression qui cible les tests fuzz (Schemathesis)
# ou E2E Playwright : Schemathesis mute la base (DELETE /api/users/... peut supprimer
# des comptes) -> on repart toujours d'une base fraiche, jamais d'une base persistee.
#
# ASCII-safe (console cp1252).

$ErrorActionPreference = "Continue"

$root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # etls/
$backend = Join-Path $root "backend"
$py      = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) { throw "venv introuvable : $py" }

Write-Host "## Redemarrage infra docker (Postgres 5433 / MinIO 9000 / Redis 6379)"
docker compose -f (Join-Path $root "docker-compose.yml") up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up -d failed (exit $LASTEXITCODE)" }

Write-Host "## Drop + recreate de la base etls_e2e"
docker exec etls_postgres psql -U etls -c "DROP DATABASE IF EXISTS etls_e2e WITH (FORCE);"
if ($LASTEXITCODE -ne 0) { throw "drop database failed (exit $LASTEXITCODE)" }
docker exec etls_postgres createdb -U etls etls_e2e
if ($LASTEXITCODE -ne 0) { throw "createdb failed (exit $LASTEXITCODE)" }

Write-Host "## Migration + seed complet sur etls_e2e"
$env:PYTHONIOENCODING = "utf-8"
$env:POSTGRES_DB = "etls_e2e"
Push-Location $backend
try {
    & $py manage.py migrate
    if ($LASTEXITCODE -ne 0) { throw "migrate failed (exit $LASTEXITCODE)" }
    & $py manage.py seed_all_demo
    if ($LASTEXITCODE -ne 0) { throw "seed_all_demo failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Host "Base etls_e2e prette (27 sequences realignees)."
