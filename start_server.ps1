# start_server.ps1 – Lance le serveur FastAPI Aurora Star
# Exécuter depuis la racine du projet : .\start_server.ps1

Set-Location "$PSScriptRoot\backend"

# Activation du venv
& "$PSScriptRoot\.venv\Scripts\Activate.ps1"

# Récupérer l'adresse IP locale (IPv4)
$localIp = (Test-Connection -ComputerName (hostname) -Count 1).IPV4Address.IPAddressToString

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Aurora Star – Serveur FastAPI" -ForegroundColor Cyan
Write-Host "  IP à donner à vos collègues : $localIp" -ForegroundColor Green
Write-Host "  http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "  Docs : http://127.0.0.1:8000/docs" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Cyan

uvicorn server:app --host 0.0.0.0 --port 8000 --reload
