$ErrorActionPreference = "Continue"
Write-Host "📡 Connecting to Godot Debug Protocol on 127.0.0.1:6007..."
try {
    $client = [System.Net.Sockets.TcpClient]::new("127.0.0.1", 6007)
    $stream = $client.GetStream()
    $reader = New-Object System.IO.StreamReader($stream)
    
    # Handshake (approximate)
    Write-Host "✅ Connected! Listening for incoming log traffic..." -ForegroundColor Green
    
    while ($client.Connected) {
        if ($stream.DataAvailable) {
            $line = $reader.ReadLine()
            if ($line) {
                Write-Output $line
            }
        }
        Start-Sleep -Milliseconds 100
    }
} catch {
    Write-Error $_.Exception.Message
} finally {
    if ($client) { $client.Close() }
}
