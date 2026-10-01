# Temporary script: append CPU-only router model config to .env
$ErrorActionPreference = 'Stop'
$envPath = 'C:\Users\danie\program\LUMAX\.env'
$raw = [System.IO.File]::ReadAllText($envPath)

$block = @'

# ── CPU-Only Router Models ────────────────────────────────────────────────
# Small router/helper GGUF models run on CPU (GPU offload = 0) to free VRAM for
# the main 9B model, eliminating full-system freezes from VRAM overflow. These
# small models are fast enough on CPU and the win is huge: the 9B stays on GPU
# at full speed (LOCAL_LLM_GPU_OFFLOAD=1.0) while smart-router / no.2-smart-router
# / the summarizer no longer consume VRAM. Comma-separated list of LM Studio
# model identifiers to load with --gpu 0.
LUMAX_CPU_ONLY_MODELS=smart-router_gguf,no.2-smart-router_gguf,reasoning-summarizer-800m-pre
'@

if ($raw -match 'LUMAX_CPU_ONLY_MODELS') {
    Write-Output 'ALREADY_PRESENT'
} else {
    [System.IO.File]::AppendAllText($envPath, $block)
    Write-Output 'APPENDED'
}

