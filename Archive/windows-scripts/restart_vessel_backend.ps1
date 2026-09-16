$LUMAX_ROOT = 'C:\Users\danie\program\LUMAX'
$venvPath = if ($Env:FoveAI_VENV_PATH) { $Env:FoveAI_VENV_PATH } else { '.venv' }
$VENV_PYTHON = Join-Path $FoveAI_ROOT "$venvPath\Scripts\python.exe"

# Kill any existing Vessel backend on port 8080
$conn = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
if ($conn) {
    $vessel_pids = ($conn | Where-Object { $_.State -eq 'Listen' }).OwningProcess
    foreach ($vessel_pid in $vessel_pids) {
        if ($vessel_pid) {
            Write-Host "Killing existing Vessel backend PID: $vessel_pid"
            Stop-Process -Id $vessel_pid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
}

# Set PYTHONPATH
$env:PYTHONPATH = "$FoveAI_ROOT;$FoveAI_ROOT\Mind;$FoveAI_ROOT\backend\Cognition"

# Start Vessel Backend
Write-Host "Starting Vessel backend..."
$p = Start-Process -FilePath $VENV_PYTHON -ArgumentList 'xr_app.py' -WorkingDirectory (Join-Path $FoveAI_ROOT 'Frontend\XR_Vessel') -NoNewWindow -PassThru
Write-Host "Vessel backend PID: $($p.Id)"

# Wait and verify
Start-Sleep -Seconds 5
try {
    $r2 = Invoke-WebRequest -Uri 'http://localhost:8080/' -TimeoutSec 5 -ErrorAction Stop
    Write-Host "Vessel backend Root: $($r2.StatusCode) OK"
} catch {
    Write-Host "Vessel backend not responding: $($_.Exception.Message)"
}
