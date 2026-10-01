$ports = 8200,8201,8300,8301,7272,8202,8203
$conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
foreach ($port in $ports) {
    $c = $conns | Where-Object { $_.LocalPort -eq $port } | Select-Object -First 1
    if ($c) {
        Write-Output ("Port {0} LISTENING (pid {1})" -f $port, $c.OwningProcess)
    } else {
        Write-Output ("Port {0} not listening" -f $port)
    }
}

