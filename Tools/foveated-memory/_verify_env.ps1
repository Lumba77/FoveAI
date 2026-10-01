$raw = [System.IO.File]::ReadAllText('C:\Users\danie\program\LUMAX\.env')
$lines = $raw -split "`n"
$match = $lines | Where-Object { $_ -match 'LUMAX_CPU_ONLY_MODELS' }
if ($match) { Write-Output ('FOUND: ' + $match) } else { Write-Output 'NOT_FOUND' }
Write-Output '--- LAST 8 LINES ---'
$lines | Select-Object -Last 8
