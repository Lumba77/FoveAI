# Start Creative Service with environment variables from .env
$envPath = "C:\Users\lumba\Program\FoveAI-lite\.env"

# Read and parse .env file
Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()
    # Skip comments and empty lines
    if ($line -and $line -notmatch '^#' -and $line -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        # Remove quotes if present
        if ($value -match '^["''](.*)["'']$') {
            $value = $matches[1]
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

# Start the creative service
$pythonExe = "C:\Users\lumba\Program\FoveAI-lite\.venv\Scripts\python.exe"
$scriptPath = "C:\Users\lumba\Program\FoveAI-lite\backend\Creativity\creative_service.py"
$workingDir = "C:\Users\lumba\Program\FoveAI-lite\backend\Creativity"

Start-Process -FilePath $pythonExe -ArgumentList $scriptPath -WorkingDirectory $workingDir -WindowStyle Hidden