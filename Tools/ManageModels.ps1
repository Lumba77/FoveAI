param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("Load", "Unload")]
    [string]$Action,

    [Parameter(Mandatory=$true)]
    [string[]]$Models,

    [int]$Port = 7272
)

foreach ($modelId in $Models) {
    if ([string]::IsNullOrWhiteSpace($modelId)) { continue }

    $body = @{ model = $modelId } | ConvertTo-Json -Depth 2
    
    if ($Action -eq "Load") {
        Write-Host "   -> Loading: $modelId..." -ForegroundColor Cyan
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10 -ErrorAction Stop | Out-Null
            Write-Host "      [Success] Model loaded." -ForegroundColor Green
        } catch {
            Write-Host "      [Warning] Could not load $modelId: $_" -ForegroundColor Yellow
        }
    } 
    elseif ($Action -eq "Unload") {
        Write-Host "   -> Unloading: $modelId..." -ForegroundColor DarkYellow
        try {
            # Try the standard v1 endpoint first, fallback to v0 if LM Studio version requires it
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models/unload" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 5 -ErrorAction Stop | Out-Null
            Write-Host "      [Success] Model unloaded." -ForegroundColor Green
        } catch {
            Write-Host "      [Warning] Could not unload $modelId: $_" -ForegroundColor Yellow
        }
    }
}
