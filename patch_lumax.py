
with open("Start_LUMAX.ps1", "r", encoding="utf-8") as f:
    content = f.read()

search_str = r"""$Global:ActiveProcs = @{}


    "MOUTH"  = @{ Path="$LUMAX_ROOT\Frontend\Mouth"; Cmd="lumax_mouth_kokoro_server.py" }"""

if search_str in content:
    replacement = """$Global:ActiveProcs = @{}

$Global:DebugMode = $LumaxDebug
$Global:DebugLog = $null

if ($LumaxDebug) {
    $debugDate = Get-Date -Format 'yyyyMMdd'
    $Global:DebugLog = Join-Path $LOG_DIR "debug_$debugDate.log"
    $debugHeader = "=== LUMAX DEBUG LOG $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Add-Content -Path $Global:DebugLog -Value $debugHeader

    # Force DEBUG-level logging so Python services emit detailed debug info
    $Env:LOG_LEVEL = "DEBUG"
    Write-Host ">>> DEBUG MODE ACTIVE — detailed DEBUG logs on console + logged to $Global:DebugLog" -ForegroundColor Yellow
}

# Define Services
$Services = @{
    "SOUL"   = @{ Path="$LUMAX_ROOT\backend\\Cognition"; Cmd="compagent.py" }    
    "MEMORY" = @{ Path="$LUMAX_ROOT\backend\\Memory";    Cmd="-m uvicorn memory_service:app --host 0.0.0.0 --port 8005" }
    "MOUTH"  = @{ Path="$LUMAX_ROOT\\Frontend\\Mouth"; Cmd="lumax_mouth_kokoro_server.py" }"""

    new_content = content.replace(search_str, replacement)
    with open("Start_LUMAX.ps1", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("PATCH SUCCESSFUL")
else:
    print("PATCH FAILED: Could not find search string")
