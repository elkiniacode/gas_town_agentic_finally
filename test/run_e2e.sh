#!/usr/bin/env bash
# Build the app image, run the Playwright suite against it in Docker, tear down.
# Extra arguments go to `playwright test`, e.g. test/run_e2e.sh e2e/chat.spec.ts
set -euo pipefail

cd "$(dirname "$0")"
compose=(docker compose -f docker-compose.test.yml)
# Test output is handed back to this user (see entrypoint.sh).
export HOST_UID HOST_GID
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

cleanup() { "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

"${compose[@]}" build finally
# `run` starts both app containers, waits for them to be healthy, and exits with the suite's status.
"${compose[@]}" run --rm playwright "$@"
