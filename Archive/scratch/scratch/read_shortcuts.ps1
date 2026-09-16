$sh = New-Object -ComObject WScript.Shell
Get-ChildItem 'C:\Users\danie\OneDrive\Skrivbord\*.lnk' | ForEach-Object {
    try {
        $sc = $sh.CreateShortcut($_.FullName)
        Write-Host "$($_.Name) -> $($sc.TargetPath) $($sc.Arguments)"
    } catch {}
}
