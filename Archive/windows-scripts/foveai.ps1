<#
.SYNOPSIS
  FoveAI — One-word ignition. Fires the full Diamond Concordia stack.
.USAGE
  .\foveai
#>

$FoveAI_ROOT = $PSScriptRoot
Set-Location $FoveAI_ROOT
.\Start_Concordia.ps1
