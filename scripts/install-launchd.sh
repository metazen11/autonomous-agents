#!/usr/bin/env bash
#
# install-launchd.sh — Install or uninstall the prompt-pack auto-sync launchd agent
#
# Usage:
#   ./scripts/install-launchd.sh              # Install and load
#   ./scripts/install-launchd.sh --uninstall  # Unload and remove
#   ./scripts/install-launchd.sh --status     # Check if loaded
#
# What it does:
#   1. Writes a launchd plist to ~/Library/LaunchAgents/
#   2. The plist runs scripts/pull-and-sync.sh every 15 minutes
#   3. pull-and-sync.sh does: git pull --ff-only → sync agents to ~/.claude/agents/ etc.
#
# Result: Your autonomous-agents repo stays in sync with GitHub,
# and all host agent folders (~/.claude/agents/, ~/.codex/agents/, etc.)
# are automatically updated with the latest enriched agent definitions.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LABEL="com.metazen11.autonomous-prompt-pack-sync"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
SYNC_SCRIPT="${REPO_ROOT}/scripts/pull-and-sync.sh"
LOG_DIR="${REPO_ROOT}/.runs/logs"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

show_status() {
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    info "Loaded: ${LABEL}"
    launchctl list "${LABEL}" 2>/dev/null | grep -E "PID|LastExitStatus" || true
    echo ""
    if [ -f "${PLIST_PATH}" ]; then
      info "Plist: ${PLIST_PATH}"
    fi
    if [ -f "${LOG_DIR}/prompt-pack-sync.log" ]; then
      echo ""
      echo "Recent log:"
      tail -5 "${LOG_DIR}/prompt-pack-sync.log" 2>/dev/null || true
    fi
  else
    warn "Not loaded: ${LABEL}"
    if [ -f "${PLIST_PATH}" ]; then
      warn "Plist exists but agent is not loaded. Run: launchctl load ${PLIST_PATH}"
    fi
  fi
}

uninstall() {
  echo "Uninstalling ${LABEL}..."
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    info "Unloaded from launchd"
  fi
  if [ -f "${PLIST_PATH}" ]; then
    rm -f "${PLIST_PATH}"
    info "Removed ${PLIST_PATH}"
  else
    warn "Plist not found at ${PLIST_PATH}"
  fi
}

install() {
  # Verify prerequisites
  if [ ! -f "${SYNC_SCRIPT}" ]; then
    error "Missing: ${SYNC_SCRIPT}"
    error "Run this from the autonomous-agents repo root."
    exit 1
  fi

  if [ ! -f "${REPO_ROOT}/.env" ]; then
    error "Missing: ${REPO_ROOT}/.env"
    error "Copy .env.example to .env and configure host paths first."
    exit 1
  fi

  # Ensure log directory exists
  mkdir -p "${LOG_DIR}"

  # Unload existing if present
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    warn "Unloaded previous version"
  fi

  # Write plist
  mkdir -p "$(dirname "${PLIST_PATH}")"
  cat > "${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>WorkingDirectory</key>
    <string>${REPO_ROOT}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>${SYNC_SCRIPT}</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
      <key>HOME</key>
      <string>${HOME}</string>
    </dict>
  </dict>
</plist>
PLIST

  info "Wrote ${PLIST_PATH}"

  # Load
  launchctl load "${PLIST_PATH}"
  info "Loaded into launchd"

  # Run immediately to verify
  echo ""
  echo "Running initial sync..."
  bash "${SYNC_SCRIPT}" 2>&1
  info "Initial sync complete"

  echo ""
  info "Auto-sync installed. Every 15 minutes:"
  echo "  1. git pull --ff-only (from GitHub)"
  echo "  2. Copy agents + pipeline to ~/.claude/agents/ etc."
  echo ""
  echo "Commands:"
  echo "  ./scripts/install-launchd.sh --status     # Check status"
  echo "  ./scripts/install-launchd.sh --uninstall  # Remove"
  echo "  ./scripts/pull-and-sync.sh                # Run manually"
  echo "  tail -f ${LOG_DIR}/prompt-pack-sync.log   # Watch logs"
}

# Parse args
case "${1:-}" in
  --uninstall|-u)
    uninstall
    ;;
  --status|-s)
    show_status
    ;;
  --help|-h)
    echo "Usage: ./scripts/install-launchd.sh [--uninstall|--status|--help]"
    echo ""
    echo "Install a launchd agent that auto-syncs the autonomous-agents prompt pack."
    echo "Runs git pull + sync to ~/.claude/agents/ every 15 minutes."
    ;;
  *)
    install
    ;;
esac
