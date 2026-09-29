$ErrorActionPreference = "Stop"
$base = "http://localhost:8080"

Write-Output "===== BACKEND /ready (direct) ====="
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/ready').read().decode())"

Write-Output "`n===== SUBMIT COMPLAINT ====="
$body = '{"text":"Burst water main flooding street 12 since fajr, water entering ground floors","location":"Street 12, F-8"}'
$created = Invoke-RestMethod -Method Post -Uri "$base/api/complaints" -ContentType "application/json" -Body $body
Write-Output ("id={0}" -f $created.id)
Write-Output ("category={0}" -f $created.category)
Write-Output ("priority={0}" -f $created.priority)
Write-Output ("triaged_by={0}" -f $created.triaged_by)
Write-Output ("ai_summary={0}" -f $created.ai_summary)
Write-Output ("status={0}" -f $created.status)
$cid = $created.id

Write-Output "`n===== STATUS open -> in_progress ====="
$upd = Invoke-RestMethod -Method Patch -Uri "$base/api/complaints/$cid/status" -ContentType "application/json" -Body '{"status":"in_progress"}'
Write-Output ("status={0}" -f $upd.status)

Write-Output "`n===== INVALID TRANSITION in_progress -> open (expect 409) ====="
try {
    Invoke-RestMethod -Method Patch -Uri "$base/api/complaints/$cid/status" -ContentType "application/json" -Body '{"status":"open"}'
    Write-Output "ERROR: expected 409"
} catch {
    $resp = $_.Exception.Response
    Write-Output ("HTTP {0}: {1}" -f [int]$resp.StatusCode, (New-Object System.IO.StreamReader($resp.GetResponseStream())).ReadToEnd())
}

Write-Output "`n===== DASHBOARD LIST (filter category=water, page_size=3) ====="
$list = Invoke-RestMethod -Uri "$base/api/complaints?category=water&page=1&page_size=3"
Write-Output ("total={0} returned={1}" -f $list.total, $list.items.Count)

Write-Output "`n===== META PROVIDERS ====="
$meta = Invoke-RestMethod -Uri "$base/api/meta/providers"
Write-Output ("active_provider={0}" -f $meta.active_provider)
Write-Output ("recent_outcomes={0}" -f $meta.recent_outcomes.Count)
Write-Output ("cache_hit_rate={0}" -f ($meta.triage_cache_hit_rate | ConvertTo-Json -Compress))

Write-Output "`n===== METRICS (sample lines) ====="
$m = Invoke-WebRequest -Uri "$base/metrics"
($m.Content -split "`n" | Select-String -Pattern "civicpulse_triage|civicpulse_requests_total" | Select-Object -First 5)