#!/usr/bin/env bash
# Stop FinAlly (macOS and Linux). Safe to run repeatedly.
# Removes the container only; the data volume (portfolio, trades, chat) is kept.
set -euo pipefail

CONTAINER="${FINALLY_CONTAINER:-finally}"
VOLUME="${FINALLY_VOLUME:-finally-data}"

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
    # stop (SIGTERM, prompt thanks to the CMD's graceful-shutdown cap) before removing,
    # so SQLite is closed cleanly
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
    docker rm -f "$CONTAINER" >/dev/null
    echo "FinAlly stopped. Data is kept in the '$VOLUME' volume."
else
    echo "FinAlly is not running."
fi
