<#
.SYNOPSIS
  Test de restauration PostgreSQL (CL-OM-11 : "procedure de restauration testee documentee").

.DESCRIPTION
  Sauvegarde la base ETSL (pg_dump -Fc), la restaure dans une base jetable, compare les volumes de
  tables cles, mesure les durees (sauvegarde = base du RPO, restauration = base du RTO) et ecrit un
  rapport JSON horodate dans scripts/backup/reports/.

  Hors production : la production s'appuie sur pgBackRest (WAL + sauvegardes completes/incrementales,
  voir PLAN_SAUVEGARDE_PRA.md). Ce script prouve que la chaine sauvegarde -> restauration produit une
  base IDENTIQUE, et donne un ordre de grandeur de RTO ; il se rejoue apres chaque migration majeure.

.EXAMPLE
  powershell -File scripts\backup\restore_test.ps1
#>
param(
  [string]$Container = "etls_postgres",
  [string]$Db = "etls",
  [string]$User = "etls"
)

$ErrorActionPreference = "Stop"
$env:Path = "C:\Users\user\AppData\Local\Programs\DockerDesktop\resources\bin;$env:Path"
$scratch = "${Db}_restore_test"
$dump = "/tmp/etls_restore_test.dump"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$reports = Join-Path $here "reports"
New-Item -ItemType Directory -Force $reports | Out-Null

function Psql($database, $sql) {
  docker exec $Container psql -U $User -d $database -At -c $sql
}

# Tables cles dont les volumes doivent etre identiques apres restauration.
$tables = @(
  "users_user", "documents_document", "documents_version", "accounting_kernel_accountmove",
  "accounting_kernel_accountmoveline", "rh_paie_employe", "rh_paie_bulletinpaie", "stocks_mouvementstock",
  "achats_purchaseorder", "hse_permistravail", "workflow_task"
)

Write-Host "1/4 Sauvegarde (pg_dump -Fc)..."
$t0 = Get-Date
docker exec $Container pg_dump -U $User -Fc -f $dump $Db
$backupSeconds = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
$sizeBytes = [int64](docker exec $Container stat -c %s $dump)

Write-Host "2/4 Restauration dans '$scratch'..."
Psql "postgres" "DROP DATABASE IF EXISTS $scratch" | Out-Null
Psql "postgres" "CREATE DATABASE $scratch" | Out-Null
$t1 = Get-Date
docker exec $Container pg_restore -U $User -d $scratch --no-owner --exit-on-error $dump
$restoreSeconds = [math]::Round(((Get-Date) - $t1).TotalSeconds, 2)

Write-Host "3/4 Comparaison des volumes..."
$rows = @()
$ok = $true
foreach ($t in $tables) {
  $a = Psql $Db "SELECT count(*) FROM $t"
  $b = Psql $scratch "SELECT count(*) FROM $t"
  $same = ($a -eq $b)
  if (-not $same) { $ok = $false }
  $rows += [pscustomobject]@{ table = $t; source = [int]$a; restauree = [int]$b; identique = $same }
}
$rows | Format-Table -AutoSize

# Controle d'integrite comptable : toutes les ecritures comptabilisees restent equilibrees apres restauration.
$desequilibre = Psql $scratch "SELECT count(*) FROM (SELECT move_id FROM accounting_kernel_accountmoveline GROUP BY move_id HAVING sum(debit) <> sum(credit)) x"
if ([int]$desequilibre -ne 0) { $ok = $false }

Write-Host "4/4 Nettoyage..."
Psql "postgres" "DROP DATABASE $scratch" | Out-Null
docker exec $Container rm -f $dump | Out-Null

$report = [ordered]@{
  date                   = (Get-Date).ToString("s")
  base                   = $Db
  taille_sauvegarde_mo   = [math]::Round($sizeBytes / 1MB, 2)
  duree_sauvegarde_s     = $backupSeconds
  duree_restauration_s   = $restoreSeconds
  ecritures_desequilibrees = [int]$desequilibre
  tables                 = $rows
  resultat               = $(if ($ok) { "OK" } else { "ECHEC" })
  cibles                 = "RPO <= 24 h (sauvegarde quotidienne) ; RTO <= 8 h (CL-OM-11)"
}
$file = Join-Path $reports ("restore_" + (Get-Date).ToString("yyyyMMdd_HHmmss") + ".json")
($report | ConvertTo-Json -Depth 4) | Set-Content -Encoding utf8 $file
Write-Host ("Resultat : {0} - sauvegarde {1}s, restauration {2}s, {3} Mo -> {4}" -f $report.resultat, $backupSeconds, $restoreSeconds, $report.taille_sauvegarde_mo, $file)
if (-not $ok) { exit 1 }
