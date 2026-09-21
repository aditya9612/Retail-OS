# PowerShell script to start local Redis server
$redisDir = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\taizod1024.redis-windows-fork_Microsoft.Winget.Source_8wekyb3d8bbwe\Redis-8.10.1-Windows-x64-msys2"

$existing = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Redis is already running (PID: $($existing.Id))."
} else {
    Write-Host "Starting Redis server on port 6379..."
    Start-Process -FilePath "$redisDir\redis-server.exe" -WorkingDirectory $redisDir -WindowStyle Hidden
    Start-Sleep -Seconds 1
    $proc = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Redis started successfully (PID: $($proc.Id))."
    } else {
        Write-Error "Failed to start Redis server."
    }
}
