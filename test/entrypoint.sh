#!/bin/sh
# Playwright container entrypoint (docker-compose.test.yml). Arguments go to `playwright test`.
# Results are written into the bind-mounted test/ as root, so hand them back to the
# host user (HOST_UID/HOST_GID, set by run_e2e.sh) afterwards.
npm ci --no-audit --no-fund || exit 1
npx playwright test "$@"
status=$?
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" test-results playwright-report 2>/dev/null
exit $status
