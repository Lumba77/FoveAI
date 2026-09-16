# Compare Lumax vs Lumax_current: newer-in-old may need copying into current.
param(
    [string]$OldRoot = "C:\Users\lumba\Program\Lumax",
    [string]$NewRoot = "C:\Users\lumba\Program\Lumax_current"
)

$ErrorActionPreference = "SilentlyContinue"
$skip = [regex]'\\(\.git|node_modules|\.godot|__pycache__|\.venv|build\\docker-buildkit-cache)(\\|$)'

function Get-Index($root) {
    $idx = @{}
    Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($skip.IsMatch($_.FullName)) { return }
        $rel = $_.FullName.Substring($root.Length).TrimStart('\')
        $idx[$rel] = $_
    }
    $idx
}

Write-Host "Indexing $OldRoot ..."
$oldIdx = Get-Index $OldRoot
Write-Host "  files: $($oldIdx.Count)"
Write-Host "Indexing $NewRoot ..."
$newIdx = Get-Index $NewRoot
Write-Host "  files: $($newIdx.Count)"

$onlyOld = @()
$newerInOld = @()
$onlyNew = @()
$newerInNew = @()

foreach ($k in $oldIdx.Keys) {
    if (-not $newIdx.ContainsKey($k)) {
        $onlyOld += $k
        continue
    }
    $o = $oldIdx[$k].LastWriteTimeUtc
    $n = $newIdx[$k].LastWriteTimeUtc
    if ($o -gt $n) { $newerInOld += [pscustomobject]@{ Rel = $k; OldUtc = $o; NewUtc = $n; DeltaSec = [int]($o - $n).TotalSeconds } }
    elseif ($n -gt $o) { $newerInNew += [pscustomobject]@{ Rel = $k; OldUtc = $o; NewUtc = $n; DeltaSec = [int]($n - $o).TotalSeconds } }
}

foreach ($k in $newIdx.Keys) {
    if (-not $oldIdx.ContainsKey($k)) { $onlyNew += $k }
}

Write-Host ""
Write-Host "=== Only in OLD ($($onlyOld.Count)) — may need copy to current ===" -ForegroundColor Yellow
$onlyOld | Sort-Object | Select-Object -First 80 | ForEach-Object { Write-Host "  $_" }
if ($onlyOld.Count -gt 80) { Write-Host "  ... and $($onlyOld.Count - 80) more" }

Write-Host ""
Write-Host "=== NEWER in OLD ($($newerInOld.Count)) — review / merge into current ===" -ForegroundColor Cyan
$newerInOld | Sort-Object { -$_.DeltaSec } | Select-Object -First 50 | ForEach-Object {
    Write-Host ("  {0}  (+{1}s in old)" -f $_.Rel, $_.DeltaSec)
}
if ($newerInOld.Count -gt 50) { Write-Host "  ... and $($newerInOld.Count - 50) more" }

Write-Host ""
Write-Host "=== NEWER in CURRENT ($($newerInNew.Count)) — keep current; old is stale ===" -ForegroundColor DarkGray
$newerInNew | Sort-Object { -$_.DeltaSec } | Select-Object -First 30 | ForEach-Object {
    Write-Host ("  {0}  (+{1}s in current)" -f $_.Rel, $_.DeltaSec)
}
if ($newerInNew.Count -gt 30) { Write-Host "  ... and $($newerInNew.Count - 30) more" }

Write-Host ""
Write-Host "=== Only in NEW ($($onlyNew.Count)) — new work in Lumax_current only ===" -ForegroundColor Green
$onlyNew | Sort-Object | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
if ($onlyNew.Count -gt 40) { Write-Host "  ... and $($onlyNew.Count - 40) more" }
