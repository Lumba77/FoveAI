$LUMAX_ROOT = 'C:\Users\danie\program\LUMAX'
$venvPath = if ($Env:FoveAI_VENV_PATH) { $Env:FoveAI_VENV_PATH } else { '.venv' }
$VENV_PYTHON = Join-Path $FoveAI_ROOT "$venvPath\Scripts\python.exe"

# Kill any existing Soul on port 8000
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($conn) {
    $soul_pid = ($conn | Where-Object { $_.State -eq 'Listen' }).OwningProcess | Select-Object -First 1
    if ($soul_pid) {
        Write-Host "Killing existing Soul PID: $soul_pid"
        Stop-Process -Id $soul_pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

# Set PYTHONPATH
$env:PYTHONPATH = "$FoveAI_ROOT;$FoveAI_ROOT\Mind;$FoveAI_ROOT\backend\Cognition"

# Load .env
Get-Content (Join-Path $FoveAI_ROOT '.env') | Where-Object { $_ -match '^[^#\s]+=.*' } | ForEach-Object {
    $parts = $_.Split('=', 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    Set-Item -Path "Env:$key" -Value $value
}

# Start Soul
Write-Host "Starting Soul..."
$p = Start-Process -FilePath $VENV_PYTHON -ArgumentList 'compagent.py' -WorkingDirectory (Join-Path $FoveAI_ROOT 'backend\Cognition') -NoNewWindow -PassThru
Write-Host "Soul PID: $($p.Id)"

# Wait and verify
Start-Sleep -Seconds 10
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 5 -ErrorAction Stop
    Write-Host "Soul HEALTH: $($r.StatusCode) OK"
} catch {
    Write-Host "Soul not responding: $($_.Exception.Message)"
}

# Check provider endpoint
try {
    $r2 = Invoke-WebRequest -Uri 'http://localhost:8000/api/chat/provider' -TimeoutSec 5 -ErrorAction Stop
    Write-Host "Provider info: $($r2.Content)"
} catch {
    Write-Host "Provider endpoint not available: $($_.Exception.Message)"
}