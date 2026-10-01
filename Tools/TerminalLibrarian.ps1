# ==============================================================================
# FOVEA TERMINAL LIBRARIAN
# Ambient Foveated Memory AI Companion for the LUMAX activated environment.
# ==============================================================================

$lumaxRoot = $PSScriptRoot | Split-Path -Parent

# We only want to inject once per session
if ($global:FoveaLibrarianHooked) {
    return
}
$global:FoveaLibrarianHooked = $true

# Store the original prompt function so we don't destroy their setup (e.g., oh-my-posh)
$originalPrompt = Get-Content Function:\prompt -ErrorAction SilentlyContinue
if (-not $originalPrompt) {
    # Fallback to standard PS prompt
    $originalPrompt = 'return "PS $($executionContext.SessionState.Path.CurrentLocation)$('' >'' * ($nestedPromptLevel + 1)) "'
}

# Rename the original prompt
Set-Item -Path Function:\OriginalPrompt -Value $originalPrompt

# We use a RunspacePool to do the Foveated Memory HTTP calls asynchronously.
# If we blocked the prompt function, the terminal would freeze for 3 seconds every Enter!
$global:LibrarianRunspacePool = [runspacefactory]::CreateRunspacePool(1, 2)
$global:LibrarianRunspacePool.Open()

# Define the new prompt function
$newPrompt = {
    $lastHistory = Get-History -Count 1
    $lastCmd = $null
    if ($lastHistory) {
        $lastCmd = $lastHistory.CommandLine.Trim()
    }

    $lastErrorStatus = $?

    # Only process if they actually typed something
    if ($lastCmd) {
        $trigger = $false
        $triggerReason = ""

        # TRIGGER 1: Command Failed (Error)
        if (-not $lastErrorStatus) {
            $trigger = $true
            $triggerReason = "error"
        }
        # TRIGGER 2: Git Command
        elseif ($lastCmd.StartsWith("git ")) {
            $trigger = $true
            $triggerReason = "git"
        }
        # TRIGGER 3: 15% Random Chance for Tips
        elseif ((Get-Random -Maximum 100) -lt 15) {
            $trigger = $true
            $triggerReason = "random"
        }

        if ($trigger) {
            $scriptBlock = {
                param($cmd, $reason, $lumaxRoot)
                try {
                    $uri = "http://127.0.0.1:8400/v1/chat/completions"
                    $headers = @{ "Authorization" = "Bearer Librarian" }
                    
                    $sysPrompt = "You are the Librarian AI. The user just ran a terminal command in the LUMAX repo."
                    if ($reason -eq "error") {
                        $sysPrompt += " The command FAILED with an error. Give a 1-sentence tip on what went wrong or how to fix it."
                    } elseif ($reason -eq "git") {
                        $sysPrompt += " They ran a git command. Give a 1-sentence repository/context tip."
                    } else {
                        $sysPrompt += " Give a 1-sentence ambient tip about the repo architecture or a feature. Be cozy but brief."
                    }

                    $body = @{
                        model = "auto"
                        messages = @(
                            @{ role = "system"; content = $sysPrompt },
                            @{ role = "user"; content = "I ran command: $cmd" }
                        )
                        max_tokens = 50
                    } | ConvertTo-Json

                    # Timeout is 10 seconds. If proxy is down, it fails silently in background.
                    $res = Invoke-RestMethod -Uri $uri -Method Post -Body $body -Headers $headers -ContentType "application/json" -TimeoutSec 10
                    $advice = $res.choices[0].message.content.Trim()

                    if ($advice) {
                        # Write asynchronously to the console
                        [Console]::ForegroundColor = [ConsoleColor]::Cyan
                        [Console]::WriteLine("`n[LIBRARIAN] $advice")
                        [Console]::ResetColor()
                    }
                } catch {
                    # Fail silently in the background
                }
            }

            # Fire and forget into the RunspacePool
            $ps = [powershell]::Create()
            $ps.RunspacePool = $global:LibrarianRunspacePool
            [void]$ps.AddScript($scriptBlock).AddArgument($lastCmd).AddArgument($triggerReason).AddArgument($lumaxRoot)
            [void]$ps.BeginInvoke()
        }
    }

    # Call and return the original prompt
    return OriginalPrompt
}

Set-Item -Path Function:\prompt -Value $newPrompt
Write-Host "🦋 Lumax super terminal. Active features: Foveated memory, Smart advice. (Feature list and help: lumax --help)" -ForegroundColor Cyan
