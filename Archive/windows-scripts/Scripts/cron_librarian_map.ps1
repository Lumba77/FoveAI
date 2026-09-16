# cron_librarian_map.ps1
# Triggers the Librarian codebase mapping sweep via the local Forge API on Port 8100.
# Recommended for daily automation (e.g., via Windows Task Scheduler at midnight).

$ErrorActionPreference = 'Stop'

# Fetch port from environment if set, default to 8100
$port = if ($env:FoveAI_FORGE_PORT) { $env:FoveAI_FORGE_PORT } else { "8100" }
$url = "http://localhost:$port/api/librarian/map"

Write-Host ">>> Triggering Librarian Codebase Mapping Sweep..." -ForegroundColor Cyan
try {
    # Send POST request to trigger the mapping sweep
    $response = Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body "{}" -TimeoutSec 10
    
    if ($response.ok) {
        Write-Host "Success: $($response.message)" -ForegroundColor Green
        Write-Host "  Use Director: $($response.use_director)" -ForegroundColor Gray
        Write-Host "  Auto Apply:   $($response.auto_apply)" -ForegroundColor Gray
    } else {
        Write-Host "Warning: API returned non-success response: $response" -ForegroundColor Yellow
    }
} catch {
    Write-Error "Failed to contact local Forge API at $url. Ensure the FoveAI stack is running! ($($_.Exception.Message))"
}
