# ==============================================================================
# INSTALL / HEAL TERMINAL LIBRARIAN
# Automatically patches .venv/Scripts/Activate.ps1 to hook Foveated Memory AI
# ==============================================================================

$lumaxRoot = $PSScriptRoot | Split-Path -Parent
$activateScript = Join-Path $lumaxRoot ".venv\Scripts\Activate.ps1"
$librarianScript = Join-Path $lumaxRoot "Tools\TerminalLibrarian.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Host "⚠️ LUMAX .venv not found. The Terminal Librarian needs a virtual environment to attach to." -ForegroundColor Yellow
    return
}

$content = Get-Content $activateScript -Raw

if ($content -match "# FOVEA TERMINAL LIBRARIAN HOOK") {
    Write-Host "✅ The Terminal Librarian Fovea Hook is already installed and healthy." -ForegroundColor Green
    return
}

# The injection code
$hookCode = @"

# FOVEA TERMINAL LIBRARIAN HOOK
# Ambient AI companion that occasionally gives tips when you run commands.
if (Test-Path "$librarianScript") {
    . "$librarianScript"
}
"@

# Insert BEFORE the signature block if it exists
if ($content -match "# SIG # Begin signature block") {
    $content = $content -replace "(?s)(# SIG # Begin signature block)", "`n$hookCode`n`n`$1"
    Set-Content -Path $activateScript -Value $content -NoNewline
} else {
    Add-Content -Path $activateScript -Value $hookCode
}

Write-Host "🦋 Fovea Terminal Librarian aggressively installed into .venv\Scripts\Activate.ps1!" -ForegroundColor Cyan
Write-Host "Restart your terminal or run '.venv\Scripts\Activate.ps1' to see her in action." -ForegroundColor Cyan
