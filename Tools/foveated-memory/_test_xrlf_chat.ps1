$ErrorActionPreference = 'SilentlyContinue'
$body = @{
    model = 'qwen4b-concise'
    messages = @(
        @{ role = 'system'; content = 'You are a helpful AI assistant.' },
        @{ role = 'user'; content = 'What is 2 + 2? Answer in one word.' }
    )
    max_tokens = 50
    temperature = 0.1
    stream = $false
} | ConvertTo-Json -Depth 6

try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8400/v1/chat/completions' -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing -TimeoutSec 90
    Write-Output ('STATUS: ' + $r.StatusCode)
    Write-Output ('BODY: ' + $r.Content)
} catch {
    Write-Output ('CHAT FAIL: ' + $_.Exception.Message)
}
