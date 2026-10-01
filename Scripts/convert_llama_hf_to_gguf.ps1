<#
.SYNOPSIS
  Convert a local Llama-family Hugging Face folder (safetensors) -> GGUF (llama.cpp), then quantize for Lumax.

.DESCRIPTION
  Produces a single .gguf file you can point FoveAI_MODEL_PATH at (Docker mount under /app/models/...).

  Prereqs (once):
    1) git clone https://github.com/ggml-org/llama.cpp
    2) cd llama.cpp
       pip install -r requirements.txt
       (If convert fails, also: pip install torch transformers sentencepiece protobuf safetensors gguf)
    3) Build llama.cpp (need llama-quantize.exe), e.g.:
       cmake -B build -DLLAMA_CURL=OFF
       cmake --build build --config Release

  Set env LLAMA_CPP_ROOT to your llama.cpp clone, or pass -LlamaCppRoot.

  Intermediate F16/BF16 GGUF is large (~16GB for 8B); delete it after quantize if you need disk.

.PARAMETER Quant
  Q4_K_S ~4.0-4.3GB | Q3_K_M ~3.4-3.7GB | Q4_K_M ~4.5-5GB (8B-class, approximate)

.EXAMPLE
  .\scripts\convert_llama_hf_to_gguf.ps1 -Quant Q4_K_S
  $env:LLAMA_CPP_ROOT = "D:\src\llama.cpp"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $HfModelDir = "D:\VR_AI_Forge_Data\models\Mind\Cognition\Meta-Llama-3.1-8B-Instruct-abliterated",

    [Parameter(Mandatory = $false)]
    [string] $LlamaCppRoot = $env:LLAMA_CPP_ROOT,

    [Parameter(Mandatory = $false)]
    [ValidateSet("Q4_K_S", "Q4_K_M", "Q3_K_M", "Q5_K_M")]
    [string] $Quant = "Q4_K_S",

    [Parameter(Mandatory = $false)]
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $HfModelDir)) {
    throw "HF model folder not found: $HfModelDir"
}

if (-not $LlamaCppRoot) {
    throw "Set LLAMA_CPP_ROOT to your llama.cpp clone, or pass -LlamaCppRoot (see script header)."
}
if (-not (Test-Path -LiteralPath $LlamaCppRoot)) {
    throw "LLAMA_CPP_ROOT path does not exist: $LlamaCppRoot"
}

$convertPy = Join-Path $LlamaCppRoot "convert_hf_to_gguf.py"
if (-not (Test-Path -LiteralPath $convertPy)) {
    throw "Missing convert_hf_to_gguf.py under llama.cpp root. Update/clone ggml-org/llama.cpp: $convertPy"
}

if (-not $OutDir) {
    $OutDir = Join-Path $HfModelDir "gguf_out"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$baseName = "llama-3.1-8b-instruct-abliterated"
$f16Path = Join-Path $OutDir "$baseName.f16.gguf"
$outGguf = Join-Path $OutDir "$baseName.$Quant.gguf"

function Find-LlamaQuantizeExe {
    $candidates = @(
        (Join-Path $LlamaCppRoot "build\bin\Release\llama-quantize.exe"),
        (Join-Path $LlamaCppRoot "build\Release\llama-quantize.exe"),
        (Join-Path $LlamaCppRoot "build\llama-quantize.exe"),
        (Join-Path $LlamaCppRoot "llama-quantize.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $found = Get-ChildItem -Path $LlamaCppRoot -Filter "llama-quantize.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

Write-Host "=== Step 1/2: Hugging Face -> FP16 GGUF (large intermediate) ===" -ForegroundColor Cyan
Write-Host "  Input:  $HfModelDir"
Write-Host "  Output: $f16Path"

& python $convertPy $HfModelDir --outfile $f16Path --outtype f16
if ($LASTEXITCODE -ne 0) {
    throw "convert_hf_to_gguf.py failed (exit $LASTEXITCODE). Install llama.cpp requirements.txt and retry."
}

$qexe = Find-LlamaQuantizeExe
if (-not $qexe) {
    throw "llama-quantize.exe not found. Build llama.cpp (Release) and ensure llama-quantize.exe exists under build\"
}

Write-Host "=== Step 2/2: Quantize -> $Quant ===" -ForegroundColor Cyan
Write-Host "  Tool:   $qexe"
Write-Host "  Output: $outGguf"

& $qexe $f16Path $outGguf $Quant
if ($LASTEXITCODE -ne 0) {
    throw "llama-quantize failed (exit $LASTEXITCODE)."
}

$sz = (Get-Item -LiteralPath $outGguf).Length / 1GB
Write-Host ""
Write-Host "Done. Quantized GGUF (~$([math]::Round($sz, 2)) GB):" -ForegroundColor Green
Write-Host "  $outGguf"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  - Point Docker FoveAI_MODEL_PATH at this file (mount D:\VR_AI_Forge_Data\... into /app/models/...)."
Write-Host "  - Optional: delete intermediate F16 to free disk:"
Write-Host "      Remove-Item -LiteralPath '$f16Path'"
Write-Host ""
