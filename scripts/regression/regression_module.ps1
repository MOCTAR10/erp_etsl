# regression_module.ps1 - Regression ciblee par module ERP (Incr.33, outilisation).
#
# Pour chaque module cite en argument :
#   1. Tests Django du/des apps backend du module (bases de test separees, sans toucher etls_e2e)
#   2. Schemathesis scoped sur les endpoints /api/<prefixes>/ du module (DB etls_e2e, OK car
#      chaque execution repart d'une base fraiche via rebuild_db.ps1)
#   3. En FIN de run (une seule fois) : typecheck + build frontend + vitest unitaire
#
# Utilisation :
#   & .\scripts\regression\rebuild_db.ps1                                # base etls_e2e fraiche + seed
#   & .\scripts\regression\regression_module.ps1 -Modules M9             # RH & Paie
#   & .\scripts\regression\regression_module.ps1 -Modules M1,M7,M9
#   & .\scripts\regression\regression_module.ps1 -Modules all            # tous (socle + M1..M12)
#
# ASCII-safe (console cp1252), nettoie les artefacts Schemathesis/Playwright en fin de run.
#

param(
    [Parameter(Mandatory = $true)]
    [string]$ModulesArg,

    [switch]$SkipSchemathesis
)

# Table de correspondance module -> (apps_django, prefixes_API, page_frontend)
#
$Modules = @{
    # app backend principale ; les apps Upstream eventuelles restent testees par leur propre module
    M1  = @{ apps = @("commercial");              api = @("commercial");          fe = $true }
    M2  = @{ apps = @("achats");                  api = @("achats");              fe = $true }
    M3  = @{ apps = @("operations");              api = @("operations");          fe = $true }
    M4  = @{ apps = @("logistique");              api = @("logistique");          fe = $true }
    M5  = @{ apps = @("stocks");                  api = @("stocks");              fe = $true }
    M6  = @{ apps = @("qualite");                 api = @("qualite");             fe = $true }
    M7  = @{ apps = @("hse");                     api = @("hse");                 fe = $true }
    M8  = @{ apps = @("maintenance");             api = @("maintenance");         fe = $true }
    M9  = @{ apps = @("rh_paie");                 api = @("rh-paie");             fe = $true }
    M10 = @{ apps = @("comptabilite");            api = @("comptabilite");        fe = $true }
    M11 = @{ apps = @("controle_gestion");        api = @("controle-gestion");    fe = $true }
    M12 = @{ apps = @("juridique");               api = @("juridique");           fe = $true }
    # Couche D (BI) + socle GED + noyau partage (apps transverses)
    D   = @{ apps = @("analytics");               api = @("analytics");           fe = $true }
    S   = @{ apps = @("users","documents","workflow","reports"); api = @("users","documents","dossiers","workflow","reports"); fe = $true }
    K   = @{ apps = @("referentiels","registres","accounting_kernel","integrations","outbox"); api = @("referentiels","registres","accounting","integrations","outbox"); fe = $false }
}

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"

$root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # etls/
$backend = Join-Path $root "backend"
$py      = Join-Path $backend ".venv\Scripts\python.exe"
$sch     = Join-Path $backend ".venv\Scripts\schemathesis.exe"
$front   = Join-Path $root "frontend"

if (-not (Test-Path $sch)) { throw "schemathesis introuvable : $sch" }

$selected = @()
foreach ($tok in $ModulesArg -split ",") {
    $tok = $tok.Trim().ToUpper()
    if ($tok -eq "ALL") { $selected = @($Modules.Keys | Sort-Object); break }
    if (-not $Modules.ContainsKey($tok)) { throw "Module inconnu : $tok (attendu : $(($Modules.Keys | Sort-Object) -join ','), all)" }
    if ($selected -notcontains $tok) { $selected += $tok }
}

Write-Host "## Modules de regression : $($selected -join ', ')"

$Results = @()

foreach ($mod in $selected) {
    $cfg = $Modules[$mod]
    Write-Host ""
    Write-Host "###### Module $mod ######"
    $modStatus = [ordered]@{ Module = $mod }

# 1. Tests Django backend (parallel : plus rapide que le run serial)
    Write-Host "## [1/3] Tests Django (--parallel 4) : $($cfg.apps -join ', ')"
    $env:POSTGRES_DB = "etls_e2e"
    Push-Location $backend
    try {
        & $py manage.py test ($cfg.apps) --parallel 4 --noinput 2>&1 | Select-String -Pattern "OK|FAILED|Ran .* test" | Select-Object -Last 4
        if ($LASTEXITCODE -ne 0) {
            $modStatus["django"] = "FAIL"
        } else {
            $modStatus["django"] = "OK"
        }
    } finally {
        Pop-Location
    }

    # 2. Schemathesis scoped (endpoints du module)
    if (-not $SkipSchemathesis) {
        Write-Host "## [2/3] Schemathesis scoped : /api/$($cfg.api -join '/, /api/')"
        $pattern = "/api/($($cfg.api -join '|'))/"
        # token frais (lifetime 30 min ; un run par module ~5-10 min)
        $body = @{ email = "admin@etls.local"; password = "Etls#Demo2026" } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/users/token/" -Method Post -Body $body -ContentType "application/json" -UseBasicParsing
        $auth = "Authorization: Bearer $($r.access)"
        $tmp = Join-Path $env:TEMP "opencode\schemathesis_module_$mod.out.log"
        $bat = Join-Path $env:TEMP "opencode\run_sch_$mod.bat"
$line = "`"$sch`" run http://127.0.0.1:8000/api/schema/ -H `"$auth`" --include-path-regex `"$pattern`" -c all --max-examples 8 --max-time 480 --workers 3 > `"$tmp`" 2>&1"
        Set-Content -Path $bat -Value $line -Encoding ascii
        $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$bat`"" -PassThru -WindowStyle Hidden
        if (-not $proc.WaitForExit(540000)) {
            Stop-Process -Id $proc.Id -Force
            $modStatus["schemathesis"] = "TIMEOUT"
} else {
            $content = Get-Content $tmp
            # Compter les Server errors dans TOUT le log (le résumé est suivi du traceback
            # éventuel du CLI handler Schemathesis en fin de run, qui masquerait le count).
            $serverErrors = ($content | Select-String "Server error" | Where-Object { $_.Line -notmatch "^$" }).Count
            $summaryLine = (($content | Select-String " failures in " | Select-Object -Last 1).Line)
            if ($serverErrors -eq 0 -and ($content | Select-String "Server error: [1-9]")) { $serverErrors = 1 }
            $modStatus["schemathesis"] = "OK ($summaryLine, server_errors=$serverErrors)"
            if ($serverErrors -gt 0) { $modStatus["schemathesis"] = "SERVER_ERRORS=$serverErrors" }
            Write-Host ($content | Select-Object -Last 25)
        }
    } else {
        Write-Host "## [2/3] Schemathesis skippe (-SkipSchemathesis)"
        $modStatus["schemathesis"] = "skipped"
    }

    # 3. Frontend : fait une seule fois, en fin de run (voir plus bas)
    $modStatus["frontend"] = "n/a"

    $Results += [pscustomobject]$modStatus
}

Write-Host ""
Write-Host "================ SUMMARY ================"
$Results | Format-Table -AutoSize

# Frontend : une seule fois pour tous les modules (typecheck + build + vitest)
Write-Host ""
Write-Host "## Frontend (global) : typecheck + build + vitest"
Push-Location $front
try {
    & npm run typecheck 2>&1 | Select-Object -Last 2
    if ($LASTEXITCODE -ne 0) { Write-Host "FRONTEND: TYPECHECK_FAIL" }
    else {
        & npm run build 2>&1 | Select-Object -Last 2
        if ($LASTEXITCODE -ne 0) { Write-Host "FRONTEND: BUILD_FAIL" }
        else {
            & npm run test:unit 2>&1 | Select-Object -Last 4
            if ($LASTEXITCODE -ne 0) { Write-Host "FRONTEND: VITEST_FAIL" }
            else { Write-Host "FRONTEND: OK" }
        }
    }
} finally {
    Pop-Location
}

# Nettoyage des artefacts de test non suivis (git status)
foreach ($art in @("playwright-report", "test-results", ".schemathesis", ".hypothesis")) {
    $d = Join-Path $root $art
    if (Test-Path $d) { Remove-Item -Recurse -Force $d }
}
Write-Host "Artefacts de test nettoyes (playwright-report, test-results, .schemathesis, .hypothesis)."
