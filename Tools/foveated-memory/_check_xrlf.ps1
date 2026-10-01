$ErrorActionPreference = 'SilentlyContinue'
Start-Sleep -Seconds 5
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8400/health' -UseBasicParsing -TimeoutSec 5
    Write-Output ('HEALTH OK: ' + $r.Content)
} catch {
    Write-Output ('HEALTH FAIL: ' + $_.Exception.Message)
}
Write-Output '--- port check ---'
foreach($p in 8300,8301){
    $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1
    if($c){ Write-Output ("Port {0} LISTENING (pid {1})" -f $p, $c.OwningProcess) } else { Write-Output ("Port {0} not listening" -f $p) }
}
