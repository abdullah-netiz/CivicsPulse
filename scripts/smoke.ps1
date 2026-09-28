# Smoke test for CivicPulse: exercises the real request path through nginx.
$ErrorActionPreference = "Stop"

Write-Output "=== compose ps ==="
docker compose ps --format "table {{.Service}}`t{{.Status}}"

$base = "http://localhost:8080"
$body = '{"text":"Burst water main flooding street 12 since morning","location":"Street 12, F-8"}'

Write-Output "=== POST /api/complaints (through nginx) ==="
$created = Invoke-RestMethod -Method Post -Uri "$base/api/complaints" -ContentType "application/json" -Body $body
$created | ConvertTo-Json -Compress

Write-Output "=== GET /api/complaints/{id} ==="
$fetched = Invoke-RestMethod -Uri "$base/api/complaints/$($created.id)"
Write-Output ("category={0} status={1} triaged_by={2}" -f $fetched.category, $fetched.status, $fetched.triaged_by)

Write-Output "=== GET /api/stats twice (expect MISS then HIT) ==="
$s1 = Invoke-WebRequest -Uri "$base/api/stats"
Write-Output ("X-Cache #1 = {0}" -f $s1.Headers["X-Cache"])
$s2 = Invoke-WebRequest -Uri "$base/api/stats"
Write-Output ("X-Cache #2 = {0}" -f $s2.Headers["X-Cache"])

Write-Output "=== GET /health (backend) ==="
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"

Write-Output "=== validate compose.prod.yaml ==="
$env:IMAGE_TAG = "abc123"
docker compose -f compose.prod.yaml config --quiet
Write-Output ("PROD config exit = {0}" -f $LASTEXITCODE)