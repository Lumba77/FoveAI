$hfHubDir = "C:\Users\danie\.cache\huggingface\hub"
$tempModelfile = "$env:TEMP\OllamaModelfile"

Write-Host "🔍 Scanning Hugging Face Hub for GGUF models..." -ForegroundColor Cyan

# Find all .gguf files in the hub
$ggufFiles = Get-ChildItem -Path $hfHubDir -Filter "*.gguf" -Recurse

if ($ggufFiles.Count -eq 0) {
    Write-Host "❌ No GGUF models found in $hfHubDir" -ForegroundColor Red
    exit
}

Write-Host "Found $($ggufFiles.Count) GGUF models. Linking to Ollama..." -ForegroundColor Green

foreach ($file in $ggufFiles) {
    # Create a clean model name based on the filename (e.g., qwen2.5-0.5b-instruct-q4_k_m)
    $modelName = $file.BaseName.ToLower() -replace '[^a-z0-9-]', '-'
    
    # Generate the Modelfile with the absolute path to the GGUF
    $modelfileContent = "FROM `"$($file.FullName)`""
    Set-Content -Path $tempModelfile -Value $modelfileContent
    
    Write-Host "🔗 Linking model: $modelName -> $($file.Name)" -ForegroundColor Yellow
    
    # Run the ollama create command. Ollama is smart enough to just link the file 
    # instead of copying it if it's already a GGUF, saving disk space!
    $process = Start-Process -FilePath "C:\OllamaCLI\ollama.exe" -ArgumentList "create $modelName -f `"$tempModelfile`"" -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -eq 0) {
        Write-Host "✅ Successfully linked $modelName into Ollama!" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Failed to link $modelName (Ollama might not be running)" -ForegroundColor Red
    }
}

# Cleanup
if (Test-Path $tempModelfile) { Remove-Item $tempModelfile }

Write-Host "`n🎉 All models synced to Ollama!" -ForegroundColor Cyan
