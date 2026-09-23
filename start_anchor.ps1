# start_anchor.ps1 – Lance le scanner BLE anchor.py
# Exécuter depuis la racine du projet : .\start_anchor.ps1
# ⚠️  Le serveur doit être déjà démarré (start_server.ps1)

Set-Location "$PSScriptRoot\backend"

& "$PSScriptRoot\.venv\Scripts\Activate.ps1"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Aurora Star – Anchor BLE Scanner" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$anchorId = Read-Host "Entrez votre ID d'Anchor (ex: A1, A2, A3, A4) [Défaut: A3]"
if ([string]::IsNullOrWhiteSpace($anchorId)) { $anchorId = "A3" }

$serverIp = Read-Host "Entrez l'adresse IP du serveur (ex: 192.168.1.50) [Défaut: 127.0.0.1]"
if ([string]::IsNullOrWhiteSpace($serverIp)) { $serverIp = "127.0.0.1" }

$serverUrl = "http://${serverIp}:8000"

Write-Host ""
Write-Host "  -> Anchor ID configuré : $anchorId" -ForegroundColor Yellow
Write-Host "  -> Serveur cible       : $serverUrl" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Cyan

$env:ANCHOR_ID = $anchorId
$env:SERVER_URL = $serverUrl

python anchor.py
