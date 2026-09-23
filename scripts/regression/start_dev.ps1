# start_dev.ps1 — Démarre le backend Django pour la régression E2E Playwright
# (Incr.33). Utilise la base dédiée `etls_e2e` (POSTGRES_DB override), puis lancé
# le runserver sur 127.0.0.1:8000. Le Vite (5173, proxy -> 8000) est démarré
# automatiquement par playwright.config.ts.
#
# Utilsation :
#   & .\scripts\regression\start_dev.ps1            # provisionne la base + runserver
#   & .\scripts\regression\start_dev.ps1 -NoSeed    # runserver seulement (base deja prete)
# Puis dans un autre terminal (frontend) : npm run test:e2e
#
# ASCII-safe (console cp1252).

param(
    [switch]$NoSeed
)

$ErrorActionPreference = "Stop"

$root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # etls/
$backend = Join-Path $root "backend"
$py      = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) { throw "venv introuvable : $py" }
if (-not (Test-Path $backend)) { throw "backend introuvable : $backend" }

Write-Host "## Infra docker (Postgres 5433 / MinIO 9000 / Redis 6379)"
docker compose -f (Join-Path $root "docker-compose.yml") up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up -d failed (exit $LASTEXITCODE)" }

# Detecte si la base dediee existe deja (le port 5433 host -> Postgres docker).
$dbExists = docker exec etls_postgres psql -U etls -tAc "SELECT 1 FROM pg_database WHERE datname='etls_e2e'" 2>$null
if ("$dbExists".Trim() -ne "1") {
    Write-Host "## Creation de la base dediee etls_e2e"
    docker exec etls_postgres createdb -U etls etls_e2e
    if ($LASTEXITCODE -ne 0) { throw "createdb etls_e2e failed (exit $LASTEXITCODE)" }
}

if (-not $NoSeed) {
    Write-Host "## Migration + seed complet sur etls_e2e"
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
}

Write-Host "## Backend 127.0.0.1:8000 (POSTGRES_DB=etls_e2e) - Ctrl+C pour arreter"
$env:POSTGRES_DB = "etls_e2e"
Push-Location $backend
try {
    & $py manage.py runserver 127.0.0.1:8000
} finally {
    Pop-Location
}