# FoveAI Diagnostic Script
Write-Host "=== CLOUDFLARED PROCESS ===" -ForegroundColor Cyan
$cfProcs = Get-Process | Where-Object { $_.ProcessName -like '*cloud*' }
if ($cfProcs) {
    $cfProcs | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
} else {
    Write-Host "NOT RUNNING" -ForegroundColor Red
}

Write-Host "`n=== CLOUDFLARED DIR ===" -ForegroundColor Cyan
$cfDir = "C:\Users\danie\.cloudflared\"
if (Test-Path $cfDir) {
    Get-ChildItem $cfDir -Force | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
} else {
    Write-Host "Directory not found!" -ForegroundColor Red
}

Write-Host "`n=== CERT/KEY FILES IN XR_VESSEL ===" -ForegroundColor Cyan
$files = @('server.key', 'server.crt', 'cert.pem', 'Digicert.cer')
foreach ($f in $files) {
    $p = "Frontend\XR_Vessel\$f"
    if (Test-Path $p) {
        $item = Get-Item $p
        Write-Host ("{0}: {1} bytes, modified {2}" -f $f, $item.Length, $item.LastWriteTime) -ForegroundColor Green
    } else {
        Write-Host ("{0}: MISSING" -f $f) -ForegroundColor Red
    }
}

Write-Host "`n=== TEST LOCAL HTTPS (port 5176) ===" -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri 'https://127.0.0.1:5176/' -SkipCertificateCheck -TimeoutSec 10 -UseBasicParsing
    Write-Host ("Status: {0}" -f $resp.StatusCode) -ForegroundColor Green
    Write-Host ("Content-Length: {0}" -f $resp.Content.Length) -ForegroundColor Green
    Write-Host ("First 200 chars: {0}" -f $resp.Content.Substring(0, [Math]::Min(200, $resp.Content.Length))) -ForegroundColor Gray
} catch {
    Write-Host ("ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

Write-Host "`n=== TEST LOCAL HTTP (port 8080) ===" -ForegroundColor Cyan
try {
    $resp2 = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/' -TimeoutSec 10 -UseBasicParsing
    Write-Host ("Status: {0}" -f $resp2.StatusCode) -ForegroundColor Green
    Write-Host ("Content-Length: {0}" -f $resp2.Content.Length) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

Write-Host "`n=== CHECK cloudflared.exe LOCATION ===" -ForegroundColor Cyan
$cfExe = "cloudflared.exe"
$paths = @("cloudflared.exe", "C:\Program Files (x86)\cloudflared\cloudflared.exe", "$env:LOCALAPPDATA\cloudflared\cloudflared.exe")
foreach ($p in $paths) {
    if (Test-Path $p) {
        Write-Host ("FOUND: {0}" -f $p) -ForegroundColor Green
    } else {
        Write-Host ("NOT FOUND: {0}" -f $p) -ForegroundColor Gray
    }
}

Write-Host "`n=== CLOUDFLARED CONFIG (root config.yml) ===" -ForegroundColor Cyan
Get-Content "config.yml" -ErrorAction SilentlyContinue

Write-Host "`n=== DONE ===" -ForegroundColor Green