# Diagnostic final deploy Login Premium — un seul fichier, propre, sans quotes imbriquées
$ErrorActionPreference = "SilentlyContinue"

$local = "C:\dev\archi\etls\frontend\dist\assets"
$serverRoot = "https://ombia-sas.com/erp_etsl"

Write-Output "== 1. MON dist LOCAL : tous les index-*.js (gros = app bundle ; petits = chunks) =="
$localFiles = Get-ChildItem $local -Filter "index-*.js" | Sort-Object Length -Descending
foreach ($f in $localFiles) {
    $kind = if ($f.Length -gt 100000) { "APP BUNDLE (gros)" } else { "chunk" }
    Write-Output ("  local {0}  ({1:N0} o)  {2}" -f $f.Name, $f.Length, $kind)
}
$largeLocal = $localFiles | Where-Object { $_.Length -gt 100000 } | Select-Object -First 1

Write-Output ""
Write-Output "== 2. LE SERVEUR : inventaire complet des index-*.js servis sous /assets/ =="
if ($largeLocal) {
    # On ne peut pas lister un dossier nginx : on teste donc les hash qu on connait
    # + on demande l index.html pour voir celui reference
    $html = (Invoke-WebRequest -Uri "$serverRoot/login" -UseBasicParsing -TimeoutSec 25).Content
    $ref = if ($html -match 'src="([^"]*index-[A-Za-z0-9_-]+\.js)"') { $Matches[1] } else { "(aucun)" }
    Write-Output ("  index.html servi reference -> {0}" -f $ref)
    Write-Output "  presence locale de chaque hash reference ? (si absent en local = ce n est pas MA build)"
    if ($ref -match 'index-([A-Za-z0-9_-]+)\.js') {
        $h = $Matches[1]
        $localHas = Test-Path (Join-Path $local "index-$h.js")
        Write-Output ("    hash {0} : present en local ? {1}" -f $h, $localHas)
    }
    Write-Output ""
    Write-Output "== 3. MON bundle Premium (gros) est-il SERVI par le serveur ? =="
    $myUrl = "$serverRoot/assets/$($largeLocal.Name)"
    try {
        $r = Invoke-WebRequest -Uri $myUrl -Method Head -UseBasicParsing -TimeoutSec 25
        Write-Output ("  {0} => {1} : MON bundle Premium est PRESENT sur le serveur" -f $largeLocal.Name, $r.StatusCode)
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Output ("  {0} => {1} : ABSENT du serveur" -f $largeLocal.Name, $code)
    }
}

Write-Output ""
Write-Output "== 4. SYNTHESE =="
Write-Output "  - Si le serveur a MON bundle (200) mais son index.html pointe un AUTRE hash :"
Write-Output "      => le deploy n a servi qu une partie (assets) ET/OU le navigateur garde l index.html en cache (aucun Cache-Control no-store)."
Write-Output "  - La grille premium est dans le gross bundle app (Login.tsx), pas dans un petit chunk."
Write-Output "  - Action : hard reload Ctrl+Shift+R (ou nav. privee) + verifier la balise <script src> de l index.html servi."
