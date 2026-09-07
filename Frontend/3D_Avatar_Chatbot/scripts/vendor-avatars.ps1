# vendor-avatars.ps1
# Windows PowerShell downloader for VRM avatar models
# Downloads CC0 VRoid sample models from GitHub

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$AvatarDir = Join-Path $RootDir "vendor" "avatars"

Write-Host "==> Installing 3D Avatar vendor files" -ForegroundColor Cyan
Write-Host "==> Target: $AvatarDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Path $AvatarDir -Force | Out-Null

# Source URLs for VRM files (CC0 licensed)
$sources = @(
    @{ File = "AvatarSample_A.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/stable/AvatarSample_A.vrm" }
    @{ File = "AvatarSample_B.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/stable/AvatarSample_B.vrm" }
    @{ File = "AvatarSample_C.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/stable/AvatarSample_C.vrm" }
    @{ File = "fem_vroid.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/fem_vroid.vrm" }
    @{ File = "masc_vroid.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/masc_vroid.vrm" }
    @{ File = "Sendagaya_Shibu.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Sendagaya_Shibu.vrm" }
    @{ File = "Sendagaya_Shino.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Sendagaya_Shino.vrm" }
    @{ File = "Victoria_Rubin.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Victoria_Rubin.vrm" }
    @{ File = "Vita.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Vita.vrm" }
    @{ File = "Vivi.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Vivi.vrm" }
    @{ File = "Darkness_Shibu.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Darkness_Shibu.vrm" }
    @{ File = "HairSample_Female.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/HairSample_Female.vrm" }
    @{ File = "HairSample_Male.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/HairSample_Male.vrm" }
    @{ File = "Sakurada_Fumiriya.vrm"; Url = "https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/Sakurada_Fumiriya.vrm" }
)

$successCount = 0
$failCount = 0

foreach ($source in $sources) {
    $outPath = Join-Path $AvatarDir $source.File
    $url = $source.Url
    
    Write-Host "==> Downloading $($source.File)..." -NoNewline
    
    try {
        # Check if file already exists and is valid (>1KB)
        if (Test-Path $outPath) {
            $size = (Get-Item $outPath).Length
            if ($size -ge 1024) {
                Write-Host " already exists ($([math]::Round($size/1KB, 1)) KB)" -ForegroundColor Green
                $successCount++
                continue
            }
        }
        
        # Use WebClient for binary-safe download
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($url, $outPath)
        $wc.Dispose()
        
        # Validate: VRM files start with "glTF" (same as GLB format)
        if ((Get-Item $outPath).Length -ge 1024) {
            $bytes = New-Object byte[] 4
            $stream = [System.IO.File]::OpenRead($outPath)
            $stream.Read($bytes, 0, 4) | Out-Null
            $stream.Close()
            $header = [System.Text.Encoding]::ASCII.GetString($bytes)
            if ($header -eq "glTF") {
                $size = (Get-Item $outPath).Length
                Write-Host " OK ($([math]::Round($size/1KB, 1)) KB)" -ForegroundColor Green
                $successCount++
            } else {
                Write-Host " INVALID (not a VRM file)" -ForegroundColor Yellow
                Remove-Item $outPath -Force -ErrorAction SilentlyContinue
                $failCount++
            }
        } else {
            Write-Host " TOO SMALL" -ForegroundColor Yellow
            Remove-Item $outPath -Force -ErrorAction SilentlyContinue
            $failCount++
        }
    }
    catch {
        Write-Host " FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $failCount++
    }
}

Write-Host ""
Write-Host "=== Download Summary ===" -ForegroundColor Cyan
Write-Host "Success: $successCount" -ForegroundColor Green
Write-Host "Failed: $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Yellow" } else { "Green" })

if ($successCount -gt 0) {
    Write-Host ""
    Write-Host "Files in $AvatarDir :" -ForegroundColor Cyan
    Get-ChildItem $AvatarDir | Select-Object Name, @{N="Size(KB)";E={[math]::Round($_.Length/1KB, 1)}} | Format-Table -AutoSize
}