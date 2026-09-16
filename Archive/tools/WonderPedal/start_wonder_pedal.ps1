# Start Wonder Pedal Stack
Write-Host "=========================================="
Write-Host "   🚀 IGNITING THE WONDER PEDAL STACK"
Write-Host "=========================================="

# 1. Start the PC Python Bridge in a new window
Write-Host "1. Starting the Python Bridge (Ricochet)..."
Start-Process powershell -ArgumentList "-NoExit -Command `"cd C:\Users\danie\program\LUMAX; & .\.venv\Scripts\Activate.ps1; python .\Tools\WonderPedal\paradiddle_bridge.py`""

# 2. Start the WebXR Dev Server in a new window
Write-Host "2. Starting the WebXR Dev Server..."
Start-Process powershell -ArgumentList "-NoExit -Command `"cd C:\Users\danie\program\LUMAX\Tools\WonderPedal\WebXR_Sensor; npm run dev`""

Write-Host "`n✅ Both systems have been launched in separate windows!"
Write-Host "`nTo test Paradiddle immediately without the browser:"
Write-Host "1. Put on your Quest headset and open Paradiddle."
Write-Host "2. Click into the 'Python Bridge' terminal window."
Write-Host "3. Press 'k' on your keyboard to hear the kick drum!"
