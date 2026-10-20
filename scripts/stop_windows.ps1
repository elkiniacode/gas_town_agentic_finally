# Stop FinAlly (Windows PowerShell). Safe to run repeatedly.
# Removes the container only; the data volume (portfolio, trades, chat) is kept.

$Container = if ($env:FINALLY_CONTAINER) { $env:FINALLY_CONTAINER } else { 'finally' }
$Volume = if ($env:FINALLY_VOLUME) { $env:FINALLY_VOLUME } else { 'finally-data' }

docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    # stop (SIGTERM) before removing, so SQLite is closed cleanly
    docker stop $Container *> $null
    docker rm -f $Container *> $null
    Write-Host "FinAlly stopped. Data is kept in the '$Volume' volume."
} else {
    Write-Host 'FinAlly is not running.'
}
