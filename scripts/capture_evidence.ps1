$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$ev = "docs/evidence"
$stamp = "Captured: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K")

# ---------- Kubernetes / autoscaling (Part H) ----------
@("$stamp", "",
  "## kubectl get pods -n civicpulse",
  (kubectl get pods -n civicpulse 2>&1 | Out-String),
  "## kubectl get svc -n civicpulse",
  (kubectl get svc -n civicpulse 2>&1 | Out-String),
  "## kubectl get hpa -n civicpulse",
  (kubectl get hpa -n civicpulse 2>&1 | Out-String),
  "## kubectl get vpa -n civicpulse",
  (kubectl get vpa -n civicpulse 2>&1 | Out-String),
  "## kubectl top pods -n civicpulse  (metrics-server)",
  (kubectl top pods -n civicpulse 2>&1 | Out-String),
  "## kubectl top nodes",
  (kubectl top nodes 2>&1 | Out-String)
) | Set-Content "$ev/k8s-autoscaling.txt" -Encoding utf8

@("$stamp", "",
  "## kubectl describe vpa backend-vpa -n civicpulse",
  (kubectl describe vpa backend-vpa -n civicpulse 2>&1 | Out-String)
) | Set-Content "$ev/vpa-recommendations.txt" -Encoding utf8

# ---------- Compose functional demo ----------
$base = "http://localhost:8080"
$lines = @("$stamp", "", "## Docker Compose functional demo (localhost:8080)", "")
foreach ($p in "/health", "/ready", "/metrics") {
  $lines += "--- GET $p ---"
  try {
    $r = Invoke-WebRequest -Uri "$base$p" -UseBasicParsing
    $body = $r.Content
    if ($body.Length -gt 700) { $body = ($body -split "`n" | Select-String -Pattern "civicpulse_" | Select-Object -First 5) -join "`n" }
    $lines += "HTTP $($r.StatusCode)"
    $lines += $body
  } catch { $lines += "FAILED: $($_.Exception.Message)" }
  $lines += ""
}
$lines += "--- GET /api/stats twice (x-cache MISS then HIT) ---"
try {
  $a = Invoke-WebRequest -Uri "$base/api/stats" -UseBasicParsing
  $b = Invoke-WebRequest -Uri "$base/api/stats" -UseBasicParsing
  $lines += "first : x-cache=$($a.Headers['x-cache'])  $($a.Content)"
  $lines += "second: x-cache=$($b.Headers['x-cache'])  $($b.Content)"
} catch { $lines += "FAILED: $($_.Exception.Message)" }
$lines | Set-Content "$ev/compose-functional.txt" -Encoding utf8

Write-Output "Wrote:"
Get-ChildItem $ev -Name