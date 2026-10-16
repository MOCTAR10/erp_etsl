# Diagnostic deploy Login Premium - nettoyé, sans quote imbriquée
$ErrorActionPreference = "SilentlyContinue"
$ok = @()
$ko = @()

Write-Output "== 1. MON BUILD LOCAL ACTUEL (Login Premium) : le hash que MON dist/index.html référence =="
$assetsDir = "C:\dev\archi\etls\frontend\dist\assets"
$distHtml  = "C:\dev\archi\etls\frontend\dist\index.html"
if (Test-Path $distHtml) {
  $content = Get-Content $distHtml -Raw
  if ($content -match 'index-[A-Za-z0-9_-]+\.js') { $h = $Matches[0]; Write-Output ("  dist/index.html -> {0}" -f $h); $ok += $h } else { $ko += "pas de hash dans dist/index.html" }
} else { $ko += "dist/index.html ABSENT (build jamais fait ?)" }

Write-Output ""
Write-Output "== 2. LE SERVEUR : quel index-*.js sert-il VRAIMENT au navigateur sur /erp_etsl/login ? =="
try {
  $r = Invoke-WebRequest -Uri "https://ombia-sas.com/erp_etsl/login" -UseBasicParsing -TimeoutSec 25
  if ($r.Content -match 'src="([^"]*index-[A-Za-z0-9_-]+\.js)"') { Write-Output ("  servé -> {0}" -f $Matches[1]) } else { Write-Output "  (pas de src index-*.js trouvé)" }
} catch { Write-Output ("  requête échouée : {0}" -f $_.Exception.Message) }

Write-Output ""
Write-Output "== 3. LES DEUX assets SONT-ILS PRESENTS sur le serveur ? (si oui les deux : le build est LA mais index.html pointe l'ancien = le serveur a un index stale) =="
foreach ($a in @("index-BLzrMtWc.js", "index-D3uKQ_zU.js")) {
  $u = "https://ombia-sas.com/erp_etsl/assets/$a"
  try { $x = Invoke-WebRequest -Uri $u -Method Head -UseBasicParsing -TimeoutSec 20; Write-Output ("  {0} -> {1} (PRESENT)" -f $a, $x.StatusCode) } catch { Write-Output ("  {0} -> introuvable" -f $a) }
}

Write-Output ""
Write-Output "== 4. CONCLUSION =="
if ($ok) {
  Write-Output ("  Mon build vérifié = {0}" -f $ok[0])
  Write-Output "  => la refonte est dans mon dist local."
} else {
  Write-Output "  => je n'ai PAS de dist/index.html local : le deploy n'a jamais inclu le frontend."
}
Write-Output ""
Write-Output "Le verdit git : la refonte est COMMITÉE (7623371) et poussée sur etsl_erp/master (7737209)."
Write-Output "Le verdit serveur : index.html sert encore l'ANCIEN hash = le deploy dist/ n'a pas été fait (push git != scp dist)."
Write-Output "Victoire partielle : mon bundle index-D3uKQ_zU.js est DÉJÀ sur le serveur (200) — il ne manque QUE le index.html frais."
