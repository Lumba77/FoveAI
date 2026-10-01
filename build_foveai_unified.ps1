# Build foveai_unified (foveai_soul) with BuildKit + on-disk cache so the CUDA llama-cpp-python
# wheel is downloaded once and reused on later rebuilds.
# Dockerfile.unified installs llama-cpp-python in an early layer (after minimal ca-certificates only) so
# edits to apt/docker/pip deps below do not invalidate that ~1.5GB layer — keep build/docker-buildkit-cache.
# Run from repo root:  .\build_foveai_unified.ps1
# Requires: Docker Desktop with BuildKit (default). Optional: $env:DOCKER_BUILDKIT_CACHE = "D:\path\to\cache"
# Optional: $env:SKIP_LLAMA_CPP_REINSTALL = "1" if foveai_core already ships cu124 llama-cpp-python (skips ~1.5GB reinstall).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:DOCKER_BUILDKIT = "1"
$cacheDir = if ($env:DOCKER_BUILDKIT_CACHE) { $env:DOCKER_BUILDKIT_CACHE } else { Join-Path $PSScriptRoot "build\docker-buildkit-cache" }
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
if (-not $env:DOCKER_BUILDKIT_CACHE) {
    $env:DOCKER_BUILDKIT_CACHE = $cacheDir
}

Write-Host "BuildKit cache: $env:DOCKER_BUILDKIT_CACHE"
docker compose build foveai_soul @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Next: docker compose up -d foveai_soul"
