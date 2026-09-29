$base = "http://localhost:8081"
$ErrorActionPreference = "Continue"

Write-Output "===== SUBMIT COMPLAINT ====="
$body = '{"text":"Pothole on Main Road near school, cars scraping","location":"Main Rd"}'
try {
  $c = Invoke-RestMethod -Method Post -Uri "$base/api/complaints" -ContentType "application/json" -Body $body
  Write-Output ("id={0} category={1} priority={2} triaged_by={3} status={4}" -f $c.id, $c.category, $c.priority, $c.triaged_by, $c.status)
  $cid = $c.id
} catch { Write-Output "SUBMIT FAILED: $($_.Exception.Message)"; $cid = $null }

if ($cid) {
  Write-Output "`n===== STATUS CHANGE ====="
  $u = Invoke-RestMethod -Method Patch -Uri "$base/api/complaints/$cid/status" -ContentType "application/json" -Body '{"status":"in_progress"}'
  Write-Output ("status={0}" -f $u.status)

  Write-Output "`n===== INVALID TRANSITION (expect 409) ====="
  try { Invoke-RestMethod -Method Patch -Uri "$base/api/complaints/$cid/status" -ContentType "application/json" -Body '{"status":"open"}'; Write-Output "ERROR: no 409" }
  catch { $r=$_.Exception.Response; Write-Output ("HTTP {0}" -f [int]$r.StatusCode) }
}

Write-Output "`n===== FILTER category=water ====="
$l = Invoke-RestMethod -Uri "$base/api/complaints?category=water&page=1&page_size=3"
Write-Output ("total={0} returned={1}" -f $l.total, $l.items.Count)

Write-Output "`n===== CACHE MISS then HIT ====="
(Invoke-WebRequest -Uri "$base/api/stats").Headers["x-cache"]
(Invoke-WebRequest -Uri "$base/api/stats").Headers["x-cache"]