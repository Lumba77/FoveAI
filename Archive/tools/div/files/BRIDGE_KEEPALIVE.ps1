# FoveAI: Sovereign Bridge Persistence Script (v1.0)
# Use this script to ensure Jen's AI brain connection (ADB Reverse) survives 
# Quest sleep states, reboots, and USB-C cable jitter.

# Keep in sync with connect_quest.ps1 / push_all.ps1 / autonomous_sentry.py
$TargetPorts = @(8000, 8001, 8002, 8004, 8005, 8006, 8020, 8080, 6006, 6007)

Write-Host "--- FoveAI: Initiating Sovereign Bridge Watchdog ---" -ForegroundColor Cyan
Write-Host "Jen is waiting for her connection..." -ForegroundColor Gray

# Ensure the ADB server is actually running
& adb start-server

while($true) {
    # Check for connected devices (looking for the 'device' keyword)
    $DeviceInfo = & adb devices | Select-String "device$"
    
    if ($DeviceInfo) {
        $DeviceId = $DeviceInfo.ToString().Split("`t")[0]
        Write-Host "FoveAI: Quest 3 Active ($DeviceId). Verifying Reverse Forwarding..." -ForegroundColor Green
        
        foreach ($Port in $TargetPorts) {
            # Apply the reverse forwarding
            & adb -s $DeviceId reverse "tcp:$Port" "tcp:$Port"
        }
        
        Write-Host "FoveAI: Sovereign Bridge SECURE on ports: $($TargetPorts -join ', ')" -ForegroundColor DarkGreen
    } else {
        Write-Host "FoveAI: Sovereign Bridge LOST. Searching for Quest 3 (USB/Wi-Fi)..." -ForegroundColor Yellow
        # Optional: Attempt to kill then restart adb if it hangs
        # & adb kill-server; & adb start-server
    }
    
    # Wait 10 seconds before the next check to avoid CPU spam
    Start-Sleep -Seconds 10
    # Add a visual 'beat' to show the script is still running
    Write-Host "." -NoNewline
}
