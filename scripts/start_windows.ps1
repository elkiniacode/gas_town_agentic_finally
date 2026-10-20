# Start FinAlly in Docker (Windows PowerShell). Safe to run repeatedly.
#
#   .\scripts\start_windows.ps1            build the image if missing, (re)start the container
#   .\scripts\start_windows.ps1 -Build     rebuild the image first
#   .\scripts\start_windows.ps1 -NoOpen    don't open a browser
#
# FINALLY_IMAGE, FINALLY_CONTAINER, FINALLY_VOLUME and FINALLY_PORT override
# the defaults (finally, finally, finally-data, 8000).
param(
    [switch]$Build,
    [switch]$NoOpen
)

# Native-command failures are checked via $LASTEXITCODE. Don't set
# $ErrorActionPreference = 'Stop': Windows PowerShell 5.1 then throws on any
# redirected docker stderr output.

$Image = if ($env:FINALLY_IMAGE) { $env:FINALLY_IMAGE } else { 'finally' }
$Container = if ($env:FINALLY_CONTAINER) { $env:FINALLY_CONTAINER } else { 'finally' }
$Volume = if ($env:FINALLY_VOLUME) { $env:FINALLY_VOLUME } else { 'finally-data' }
$Port = if ($env:FINALLY_PORT) { $env:FINALLY_PORT } else { '8000' }
$Url = "http://localhost:$Port"

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'Docker is not installed. Get it from https://docs.docker.com/get-docker/'
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Docker is not running. Start Docker Desktop and try again.'
    exit 1
}

# The container reads its configuration from .env; it is never baked into the image (R34).
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Warning '.env not found; created it from .env.example.'
    Write-Warning 'The app runs without keys (simulated prices, chat disabled).'
    Write-Warning 'Add OPENROUTER_API_KEY to .env to enable AI chat, then re-run this script.'
}

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building image '$Image' (the first build takes a few minutes)..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    docker stop $Container *> $null
    docker rm -f $Container *> $null
}
docker run -d --name $Container -v "${Volume}:/app/db" -p "${Port}:8000" --env-file .env $Image > $null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host -NoNewline 'Starting FinAlly'
$Status = 'starting'
for ($i = 0; $i -lt 60; $i++) {
    $Status = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $Container 2> $null
    if ($LASTEXITCODE -ne 0) { $Status = 'missing' }
    if ($Status -in @('healthy', 'unhealthy', 'exited', 'dead', 'missing')) { break }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ''

if ($Status -ne 'healthy') {
    Write-Host "FinAlly did not become healthy (status: $Status). Recent logs:"
    docker logs --tail 40 $Container
    exit 1
}

Write-Host "FinAlly is running at $Url"
Write-Host "Stop it with .\scripts\stop_windows.ps1 (your data is kept in the '$Volume' volume)."

if (-not $NoOpen) {
    Start-Process $Url
}
