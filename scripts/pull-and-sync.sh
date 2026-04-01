#!/usr/bin/env bash
#
# pull-and-sync.sh — Git pull then sync prompt pack to all configured hosts
#
# Designed to be run by launchd, cron, or manually.
# Exits cleanly on any failure (launchd will retry next interval).
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/.runs/logs"

mkdir -p "${LOG_DIR}"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "${LOG_DIR}/prompt-pack-sync.log"
}

log "Starting pull-and-sync"

# 1. Git pull (fast-forward only, no merge commits)
cd "${REPO_ROOT}"
if git rev-parse --git-dir >/dev/null 2>&1; then
  BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
  git pull --ff-only --quiet 2>/dev/null || {
    log "git pull failed (non-ff or no remote) — syncing from local state"
  }
  AFTER=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
  if [ "${BEFORE}" != "${AFTER}" ]; then
    log "Updated: ${BEFORE:0:8} → ${AFTER:0:8}"
  else
    log "Already up to date (${BEFORE:0:8})"
  fi
else
  log "Not a git repo — syncing from local state"
fi

# 2. Sync to all configured host targets
# Need Python 3.10+ for dataclass slots=True. Prefer homebrew over system Python 3.9.
if [ -x /opt/homebrew/bin/python3 ]; then
  PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
PYTHONPATH="${REPO_ROOT}" "${PYTHON_BIN}" "${REPO_ROOT}/scripts/sync_prompt_pack.py" sync --repo-root "${REPO_ROOT}" 2>&1 | while read -r line; do
  log "  ${line}"
done

log "Pull-and-sync complete"
