# Lumax Sovereign Start Script
# Default: VR with VDXR/UltraLight
# Usage: .\Start.ps1              -> VR Ultra
#        .\Start.ps1 menu          -> Show launch menu
#        .\Start.ps1 soul-coder    -> Start coding agent
#        .\Start.ps1 full          -> Full backend

param([string]$Mode = "default")

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Mode -eq "menu") {
    # Show interactive menu
    & (Join-Path $PSScriptRoot "Start_Lumax_Menu.ps1") -Command "menu"
} elseif ($Mode -eq "soul-coder") {
    # Start soul-coder directly
    & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_SoulCoder.ps1") @args
} elseif ($Mode -eq "full") {
    # Full backend with embers + ops
    & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_VR.ps1") -FullBackend @args
} else {
    # Default: VR Ultra
    $script = Join-Path $PSScriptRoot "Scripts\Start_Lumax_VR.ps1"
    if ($args.Count -eq 0) {
        & $script -Ultra
    } else {
        & $script @args
    }
}
