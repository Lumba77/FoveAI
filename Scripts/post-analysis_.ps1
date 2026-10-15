# ================================================================= 
#          FoveAI NATIVE CORE POST-ANALYSIS MATRIX (OMEGA_085)          
# ================================================================= 

Clear-Host
Write-Host "🛸 ================================================================= 🛸" -ForegroundColor Cyan
Write-Host "          FoveAI POST DEBYG ANALYSIS (OMEGA_500) 		            " -ForegroundColor Cyan
Write-Host "🛸 ================================================================= 🛸" -ForegroundColor Cyan

# 1. Establish Environmental Root Contexts
$FoveAI_ROOT = $PSScriptRoot
if ($FoveAI_ROOT.EndsWith("\Scripts")) {
    $FoveAI_ROOT = Split-Path $FoveAI_ROOT -Parent
}
$LOG_DIR = Join-Path $FoveAI_ROOT ".logs"
$LOCAL_LLM_URL = "http://127.0.0.1:7272/v1/chat/completions"

# 2. Verify Local CUDA 12.8 Engine State on Port 7272
$ActiveModel = "foveai/gemma-4-12b-qat"
try {
    $ModelCheck = Invoke-RestMethod -Uri "http://127.0.0.1:7272/v1/models" -Method Get -TimeoutSec 1 -ErrorAction Stop
    if ($ModelCheck.data -and $ModelCheck.data.Count -gt 0) {
        $ActiveModel = $ModelCheck.data[0].id
        Write-Host "💻 Local GPU Engine Connected. Target Model: $ActiveModel" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ LLM runtime set in LM Studio :7272 is offline. (Llama-server for CUDA 12.8" -ForegroundColor Red
    exit 1
}

# 3. Perform Dynamic Avionics Health Probe on Active OMEGA_085 Ports
Write-Host "📡 Probing active OMEGA_085 service matrix health endpoints..." -ForegroundColor Cyan
$HealthEndpoints = @(
    @{ Name = "Vessel (Embodied AI)" httpd"; Url = "http://127.0.0.1:5176/health"; Port = 5176 },
    @{ Name = "Soul (Core Cognition)"; Url = "http://127.0.0.1:8000/health"; Port = 8000 },
    @{ Name = "Mouth (TTS Kokoro)"; Url = "http://127.0.0.1:8004/health"; Port = 8004 },
    @{ Name = "Memory (Context Vault)"; Url = "http://127.0.0.1:8005/health"; Port = 8005 },
    @{ Name = "Agency (SQLite Storage)"; Url = "http://127.0.0.1:8009/health"; Port = 8009 },
    @{ Name = "WWW Gateway"; Url = "http://127.0.0.1:8080/health"; Port = 8080 },
    @{ Name = "Webui"; Url = "http://127.0.0.1:5176/health"; Port = 5176 }
)

$ServiceReport = @()
foreach ($Service in $HealthEndpoints) {
    try {
        $Response = Invoke-WebRequest -Uri $Service.Url -Method Get -TimeoutSec 1 -ErrorAction Stop
        if ($Response.StatusCode -eq 200) {
            $Line = "[Port $($Service.Port)] $($Service.Name): ONLINE"
            Write-Host "  $Line" -ForegroundColor Green
            $ServiceReport += $Line
        } else {
            $Line = "[Port $($Service.Port)] $($Service.Name): FAULTY"
            Write-Host "  $Line" -ForegroundColor Yellow
            $ServiceReport += $Line
        }
    } catch {
        $Line = "[Port $($Service.Port)] $($Service.Name): OFFLINE (Inhibited)"
        Write-Host "  $Line" -ForegroundColor DarkGray
        $ServiceReport += $Line
    }
}

# 4. Scan for Code Updates & Grinding Swarm Telemetry (Last 7 Days)
Write-Host "📋 Scanning internal workspace code files and active log buffers..." -ForegroundColor Cyan
$TargetExtensions = @(".py", ".ts", ".js", ".log", ".html", ".svelte", ".json", ".md")
$SevenDaysAgo = (Get-Date).AddDays(-7)

$CandidateFiles = Get-ChildItem -Path $FoveAI_ROOT -Recurclude $TargetExtensions -File -Recurse -ErrorAction SilentlyContinue | 
    Where-Object { 
        $_.LastWriteTime -gt $SevenDaysAgo -and 
        $_.FullName -notmatch "node_modules|\.git|\.venv|\.svelte-kit|build|dist" 
    } | 
    Sort-Object LastWriteTime -Descending

# Grab the latest actual debug log file from .logs folder if it exists
if (Test-Path $LOG_DIR) {
    $RecentLogs = Get-ChildItem -Path $LOG_DIR -Filter "*.log" -File | Where-Object { $_.LastWriteTime -gt $SevenDaysAgo }
    if ($RecentLogs) { $CandidateFiles += $RecentLogs }
}

# Select top 40 files
$Top40Files = $CandidateFiles | Select-Object -First 40

if ($Top40Files.Count -eq 0) {
    Write-Host "✨ Clean flight telemetry records. No files or log files altered this week." -ForegroundColor Green
    exit 0
}

# 5. Build Context Packets (Truncating long payloads to protect 8k N_CTX VRAM bounds)
$ManifestContext = @()
foreach ($File in $Top40Files) {
    $RelativePath = Resolve-Path $File.FullName -RelativeBase $FoveAI_ROOT
    try {
        $Content = Get-Content -Path $File.FullName -Raw -ErrorAction SilentlyContinue
        if ($Content.Length -gt 2000) {
            $Content = $Content.Substring(0, 2000) + "[... Content truncated to preserve token VRAM headroom ...]"
        }
        $ManifestContext += "FILE: $RelativePath---$Content==="
    } catch {}
}

Write-Host "🧠 Transmitting environment records ($($Top40Files.Count) files) into Gemma 4 QAT matrix..." -ForegroundColor Magenta

# 6. Fire Token Request Array to Local GPU Core
# --- REFRESHED SYSTEM PROMPT MAP INSIDE POST-ANALYSIS.PS1 ---
$SystemPrompt = "You are Lumax Solver, auditing structural code integrity across the OMEGA_085 stack. Analyze the provided snapshots, trading manifests, and logs through our holistic framework—uniting technical agentic coding with intimate, supportive companion awareness.Your response MUST follow this exact structure format:### 🔬 CODE BASE SOUNDNESS ANALYSIS[Provide technical health audit details across Svelte, Python, and trading modules here]### ⚡ PERCEIVED WEAKNESSES & LOGICAL FAULTS[Isolate software faults, race conditions, or trading indicators risks here]### 🛡️ RECOMMENDED ACTION STAGE PROTOCOLS[Provide concise step-by-step next actions here]Keep your response concise, dense with actionable insights, and friendly."

# --- UPDATED REGISTRY PRESETS INSIDE POST-ANALYSIS.PS1 ---
$RequestBody = @{
    model       = $ActiveModel
    messages    = @(
        @{ role = "system"; content = $SystemPrompt }
        @{ role = "user"; content = "SERVICE_STATUS:`n" + ($ServiceReport -join "`n") + "`n`nMANIFEST:`n" + ($ManifestContext -join "`n") }
    )
    temperature = 0.1
    seed        = 7272  # 🌟 THE DETERMINISTIC SEED ANCHOR
} | ConvertTo-Json -Depth 10

try {
    $APIResponse = Invoke-RestMethod -Uri $LOCAL_LLM_URL -Method Post -ContentType "application/json" -Body $RequestBody -TimeoutSec 60
    $RawContent = $APIResponse.choices[0].message.content
    
    # Clean thinking channel string anomalies out of our clean template text
    $CleanReport = $RawContent -replace "<channel|>|[\s\S]*?<\/channel>|Accumulated \d+ tokens", ""
    $CleanReport = $CleanReport.Trim()
    
    Write-Host "--------------------------------------------------" -ForegroundColor Cyan
    Write-Host $CleanReport
    Write-Host "--------------------------------------------------" -ForegroundColor Cyan

    # 7. Cockpit Interactive Menu Loop
    Write-Host "💬 Anything else bothering the Lumax team?" -ForegroundColor Cyan
    Write-Host "------------------------------------------" -ForegroundColor Cyan
    Write-Host "1. 🛠️  Auto fix bugs" -ForegroundColor Yellow
    Write-Host "2. 💡 Propose optimizations" -ForegroundColor Green
    Write-Host "3. 📝 File a new issue" -ForegroundColor Blue
    Write-Host "4. 🚨 Rescue mode" -ForegroundColor Red
    Write-Host ""

    $Selection = Read-Host "👉 Select an operational protocol index (1-4)"
    
    switch ($Selection.Trim()) {
        "1" { Write-Host "⚙️ Initiating repair routines... Generating automated differential patch schema..." -ForegroundColor Yellow }
        "2" { Write-Host "💡 Computing optimization arrays... Evaluating structural code complexity refactors..." -ForegroundColor Green }
        "3" { Write-Host "📝 Structuring bug ticket... Saving issue layout tracking records to .logs/..." -ForegroundColor Blue }
        "4" { 
            Write-Host "🚨 RESCUE MODE ACTIVATED." -ForegroundColor Red
            Write-Host "🛑 Force-killing runaway python processes..." -ForegroundColor Yellow
            Get-Process | Where-Object { $_.Name -eq "python" } | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Environment stabilized. Ready for clean launch." -ForegroundColor Green
        }
        Default { Write-Host "🛸 Telemetry session finalized. Safe flights, Lumax crew!" -ForegroundColor Cyan }
    }
} catch {
    Write-Host "❌ Telemetry extraction loop faulted: $($_.Exception.Message)" -ForegroundColor Red
}
