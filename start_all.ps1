# start_all.ps1 – Lance le serveur ET l'anchor dans deux fenêtres PowerShell séparées
# Exécuter depuis la racine du projet : .\start_all.ps1

$root = $PSScriptRoot

Write-Host "🚀 Lancement Aurora Star..." -ForegroundColor Green

# Fenêtre 1 : Serveur FastAPI
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; & '$root\start_server.ps1'"

# Attente que le serveur démarre
Start-Sleep -Seconds 3

# Fenêtre 2 : Anchor BLE
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; & '$root\start_anchor.ps1'"

Write-Host "✅ Deux fenêtres ouvertes : Serveur + Anchor" -ForegroundColor Green
Write-Host "   Dashboard : http://127.0.0.1:8000/docs" -ForegroundColor Yellow
