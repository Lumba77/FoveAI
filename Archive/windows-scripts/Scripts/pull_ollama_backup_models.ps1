# Pull models that match Backend/Cognition/compagent.py defaults (vision helper, SmolLM, embeds).
# Usage (after foveai_ollama_backup is healthy):
#   .\scripts\pull_ollama_backup_models.ps1
# Optional container name:
#   .\scripts\pull_ollama_backup_models.ps1 -Container foveai_ollama_backup

param(
    [string] $Container = "foveai_ollama_backup"
)

$models = @(
    "qwen2.5:latest",
    "moondream:latest",
    "nomic-embed-text:latest",
    "smollm2:latest"
)

Write-Host "--- Ollama pull into container: $Container ---" -ForegroundColor Cyan
$exists = docker ps -a -q -f "name=$Container"
if (-not $exists) {
    Write-Error "Container '$Container' not found. Start the stack first (e.g. docker compose up -d from repo root)."
    exit 1
}

foreach ($m in $models) {
    Write-Host "Pulling $m ..." -ForegroundColor Yellow
    docker exec $Container ollama pull $m
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Pull failed for $m"
    }
}

Write-Host "Done. Test: curl http://127.0.0.1:11434/api/tags" -ForegroundColor Green
