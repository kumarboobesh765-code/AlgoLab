# Stops StrategyLab dev servers (API on 8000, web on 3000).

foreach ($port in 8000, 3000) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $conn | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            Write-Host "Stopping PID $_ (port $port)"
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "Nothing on port $port"
    }
}
