#Requires -Version 5.1
# Deploy the canonical chat.html (Tools/jenna-vscode/src/webview/chat.html) to the
# installed VS Code, Antigravity, and Devin extensions so all three IDEs show the same UI.

$ErrorActionPreference = "Continue"

# Canonical source
$repoRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$sourceChat = Join-Path $repoRoot "Tools\jenna-vscode\src\webview\chat.html"
if (-not (Test-Path $sourceChat)) {
    throw "Canonical source not found: $sourceChat"
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$deployed = @()

# 1. VS Code
$vscodeExts = Get-ChildItem -Path "$env:USERPROFILE\.vscode\extensions" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*foveai-vibe-coder*" -or $_.Name -like "*jenna-copilot*" }
if ($vscodeExts) {
    foreach ($ext in $vscodeExts) {
        $destHtml = Join-Path $ext.FullName "src\webview\chat.html"
        $destDist = Join-Path $ext.FullName "dist\extension.js"
        try {
            if (Test-Path $destHtml) {
                Copy-Item -Path $sourceChat -Destination $destHtml -Force
                $deployed += "✅ VS Code HTML: $destHtml"
            }
            if ((Test-Path (Join-Path $repoRoot "Tools\jenna-vscode\dist\extension.js")) -and (Test-Path $destDist)) {
                Copy-Item -Path (Join-Path $repoRoot "Tools\jenna-vscode\dist\extension.js") -Destination $destDist -Force
                $deployed += "✅ VS Code JS: $destDist"
            }
        } catch {
            $deployed += "⚠️ VS Code locked: $($ext.FullName) - $($_.Exception.Message)"
        }
    }
} else {
    $deployed += "⚠️ VS Code extension not found"
}

# 2. Antigravity
$antiExts = Get-ChildItem -Path "$env:USERPROFILE\.antigravity-ide\extensions" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*foveai-vibe-coder*" -or $_.Name -like "*jenna-copilot*" }
if ($antiExts) {
    foreach ($d in $antiExts) {
        $destHtml = Join-Path $d.FullName "src\webview\chat.html"
        $destDist = Join-Path $d.FullName "dist\extension.js"
        try {
            if (Test-Path $destHtml) {
                Copy-Item -Path $sourceChat -Destination $destHtml -Force
                $deployed += "✅ Antigravity HTML: $destHtml"
            }
            if ((Test-Path (Join-Path $repoRoot "Tools\jenna-vscode\dist\extension.js")) -and (Test-Path $destDist)) {
                Copy-Item -Path (Join-Path $repoRoot "Tools\jenna-vscode\dist\extension.js") -Destination $destDist -Force
                $deployed += "✅ Antigravity JS: $destDist"
            }
        } catch {
            $deployed += "⚠️ Antigravity locked: $($d.FullName) - $($_.Exception.Message)"
        }
    }
} else {
    $deployed += "⚠️ Antigravity extension not found"
}

# 3. Devin (gzipped chat.html)
$devinGz = Get-ChildItem -Path "$env:APPDATA\Devin\User\globalStorage\blackboxapp.blackbox" -Recurse -File -Force -Filter "chat.html.gz" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($devinGz) {
    Copy-Item -Path $devinGz.FullName -Destination "$($devinGz.FullName).bak-$ts" -Force

    $bytes = [System.IO.File]::ReadAllBytes($sourceChat)
    $outFile = [System.IO.File]::Create($devinGz.FullName)
    try {
        $mem = New-Object System.IO.MemoryStream(,$bytes)
        $gz = New-Object System.IO.Compression.GzipStream($outFile, [System.IO.Compression.CompressionLevel]::Optimal, $false)
        try {
            $mem.CopyTo($gz)
        } finally {
            $gz.Dispose()
        }
        $mem.Dispose()
    } finally {
        $outFile.Dispose()
    }
    $deployed += "✅ Devin: $($devinGz.FullName)"
} else {
    $deployed += "⚠️ Devin chat.html.gz not found"
}

Write-Host "`n--- Deployment results ---"
$deployed | ForEach-Object { Write-Host $_ }
Write-Host "`nBackups were created with timestamp .bak-$ts"
Write-Host "Restart or reload the IDE panels to see the updated UI."
