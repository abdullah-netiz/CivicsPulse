$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Output "===== Rebuild frontend + recreate backend ====="
docker compose up --build -d frontend backend 2>&1 | Select-Object -Last 12

Write-Output "`n===== Wait for healthy ====="
Start-Sleep -Seconds 12
docker compose ps --format "{{.Service}} | {{.Status}}"

Write-Output "`n===== Documented demo curls (through nginx :8080) ====="
Write-Output "--- /health ---"
curl.exe -s http://localhost:8080/health
Write-Output "`n--- /ready ---"
curl.exe -s http://localhost:8080/ready
Write-Output "`n--- /metrics (first 3 triage/request lines) ---"
(curl.exe -s http://localhost:8080/metrics) -split "`n" | Select-String -Pattern "civicpulse_" | Select-Object -First 3