#!/usr/bin/env bash
# Daily refresh: fetch upstream data, rebuild public/, optionally deploy.
#
#   ./scripts/update.sh
#   DEPLOY_CMD='rsync -a --delete public/ web:/var/www/buckboard/' ./scripts/update.sh
#
# Safe to run from cron: it takes a lock so overlapping runs can't collide, and
# it leaves the existing site untouched if the fetch fails.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PYTHON="${PYTHON:-python3}"
LOCK="${TMPDIR:-/tmp}/bbh-standings.lock"

# mkdir is atomic on every POSIX filesystem — portable where flock isn't.
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "another update is already running (lock: $LOCK); exiting" >&2
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

echo "=== $(date -u '+%Y-%m-%d %H:%M:%SZ') update starting ==="

if ! "$PYTHON" scripts/fetch.py "$@"; then
  echo "fetch failed — site left at the last good build" >&2
  exit 1
fi

"$PYTHON" scripts/build.py

if [ -n "${DEPLOY_CMD:-}" ]; then
  echo "deploying: $DEPLOY_CMD"
  eval "$DEPLOY_CMD"
fi

echo "=== $(date -u '+%Y-%m-%d %H:%M:%SZ') update complete ==="
