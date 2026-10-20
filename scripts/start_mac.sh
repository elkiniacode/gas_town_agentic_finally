#!/usr/bin/env bash
# Start FinAlly in Docker (macOS and Linux). Safe to run repeatedly.
#
#   scripts/start_mac.sh            build the image if missing, (re)start the container
#   scripts/start_mac.sh --build    rebuild the image first
#   scripts/start_mac.sh --no-open  don't open a browser
#
# FINALLY_IMAGE, FINALLY_CONTAINER, FINALLY_VOLUME and FINALLY_PORT override
# the defaults (finally, finally, finally-data, 8000).
set -euo pipefail

IMAGE="${FINALLY_IMAGE:-finally}"
CONTAINER="${FINALLY_CONTAINER:-finally}"
VOLUME="${FINALLY_VOLUME:-finally-data}"
PORT="${FINALLY_PORT:-8000}"
URL="http://localhost:${PORT}"

build=false
open_browser=true
for arg in "$@"; do
    case "$arg" in
        --build) build=true ;;
        --no-open) open_browser=false ;;
        -h | --help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg (try --help)" >&2
            exit 2
            ;;
    esac
done

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed. Get it from https://docs.docker.com/get-docker/" >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running. Start Docker Desktop (or the docker daemon) and try again." >&2
    exit 1
fi

# The container reads its configuration from .env; it is never baked into the image (R34).
if [ ! -f .env ]; then
    cp .env.example .env
    echo "WARNING: .env not found; created it from .env.example."
    echo "         The app runs without keys (simulated prices, chat disabled)."
    echo "         Add OPENROUTER_API_KEY to .env to enable AI chat, then re-run this script."
fi

if [ "$build" = true ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building image '$IMAGE' (the first build takes a few minutes)..."
    docker build -t "$IMAGE" .
fi

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
    docker rm -f "$CONTAINER" >/dev/null
fi
docker run -d \
    --name "$CONTAINER" \
    -v "$VOLUME":/app/db \
    -p "$PORT":8000 \
    --env-file .env \
    "$IMAGE" >/dev/null

printf 'Starting FinAlly'
status=starting
for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || echo missing)"
    case "$status" in
        healthy) break ;;
        unhealthy | exited | dead | missing) break ;;
    esac
    printf '.'
    sleep 1
done
echo

if [ "$status" != healthy ]; then
    echo "FinAlly did not become healthy (status: $status). Recent logs:" >&2
    docker logs --tail 40 "$CONTAINER" >&2 || true
    exit 1
fi

echo "FinAlly is running at $URL"
echo "Stop it with scripts/stop_mac.sh (your data is kept in the '$VOLUME' volume)."

if [ "$open_browser" = true ]; then
    if command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
    fi
fi
