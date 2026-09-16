# =====================================================================
# FoveAI Unity Error Extractor
# Reads Unity Editor.log and writes only error/warning lines to a small file
# Usage: powershell -File Scripts/unity_errors.ps1
# =====================================================================

$editorLog = Join-Path $env:LOCALAPPDATA "Unity\Editor\Editor.log"
$outputFile = Join-Path $PSScriptRoot "..\unity_errors.txt"

if (-not (Test-Path $editorLog)) {
    Write-Host "Unity Editor.log not found at: $editorLog" -ForegroundColor Red
    exit 1
}

$logTime = (Get-Item $editorLog).LastWriteTime
Write-Host "Editor.log last modified: $logTime" -ForegroundColor DarkGray

# Extract only error and warning lines
$errors = Select-String -Path $editorLog -Pattern 'error CS|warning CS|error :|Compile error' | 
    ForEach-Object { $_.Line } |
    Select-Object -Unique

if ($errors.Count -eq 0) {
    Write-Host "No compile errors found!" -ForegroundColor Green
    "" | Out-File $outputFile -Encoding utf8
} else {
    Write-Host "Found $($errors.Count) error/warning lines" -ForegroundColor Yellow
    $errors | Out-File $outputFile -Encoding utf8
    Write-Host "Written to: $outputFile" -ForegroundColor Cyan
    
    # Print summary
    $csErrors = ($errors | Where-Object { $_ -match 'error CS' }).Count
    $csWarnings = ($errors | Where-Object { $_ -match 'warning CS' }).Count
    Write-Host "`n  Errors:   $csErrors" -ForegroundColor Red
    Write-Host "  Warnings: $csWarnings" -ForegroundColor Yellow
}

# Also print the content
if ((Test-Path $outputFile) -and (Get-Content $outputFile).Length -gt 0) {
    Write-Host "`n--- unity_errors.txt ---" -ForegroundColor Cyan
    Get-Content $outputFile | ForEach-Object { Write-Host $_ }
}