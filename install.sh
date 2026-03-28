#!/usr/bin/env bash
#
# install.sh — Install autonomous pipeline skill + agent definitions for Claude Code
#
# Usage:
#   ./install.sh           # Copy files (standalone install)
#   ./install.sh --symlink # Symlink files (editable, updates in place)
#   ./install.sh --check   # Verify installation
#   ./install.sh --remove  # Remove installed files
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILL_DIR="${CLAUDE_DIR}/skills/autonomous"
AGENTS_DIR="${CLAUDE_DIR}/agents"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

# Verify source files exist
check_source() {
  local missing=0
  if [[ ! -f "${SCRIPT_DIR}/pipeline/autonomous.md" ]]; then
    error "Missing: pipeline/autonomous.md"
    missing=1
  fi
  local agents=(code-reviewer qa-tester security-auditor security-fixer perf-profiler infra-checker db-analyst dep-auditor)
  for agent in "${agents[@]}"; do
    if [[ ! -f "${SCRIPT_DIR}/agents/${agent}.md" ]]; then
      error "Missing: agents/${agent}.md"
      missing=1
    fi
  done
  return $missing
}

install_copy() {
  echo "Installing autonomous pipeline (copy mode)..."
  echo ""

  mkdir -p "${SKILL_DIR}" "${AGENTS_DIR}"

  cp "${SCRIPT_DIR}/pipeline/autonomous.md" "${SKILL_DIR}/skill.md"
  info "Pipeline skill → ${SKILL_DIR}/skill.md"

  for f in "${SCRIPT_DIR}"/agents/*.md; do
    cp "$f" "${AGENTS_DIR}/$(basename "$f")"
    info "Agent $(basename "$f") → ${AGENTS_DIR}/$(basename "$f")"
  done

  echo ""
  info "Installation complete. Run './install.sh --check' to verify."
}

install_symlink() {
  echo "Installing autonomous pipeline (symlink mode)..."
  echo ""

  mkdir -p "${SKILL_DIR}" "${AGENTS_DIR}"

  ln -sf "${SCRIPT_DIR}/pipeline/autonomous.md" "${SKILL_DIR}/skill.md"
  info "Pipeline skill → ${SKILL_DIR}/skill.md (symlink)"

  for f in "${SCRIPT_DIR}"/agents/*.md; do
    ln -sf "$f" "${AGENTS_DIR}/$(basename "$f")"
    info "Agent $(basename "$f") → ${AGENTS_DIR}/$(basename "$f") (symlink)"
  done

  echo ""
  info "Installation complete (symlink). Edits to source files take effect immediately."
}

check_install() {
  echo "Checking installation..."
  echo ""

  local ok=0
  local fail=0

  if [[ -f "${SKILL_DIR}/skill.md" ]]; then
    info "Pipeline skill installed"
    ok=$((ok + 1))
  else
    error "Pipeline skill NOT found at ${SKILL_DIR}/skill.md"
    fail=$((fail + 1))
  fi

  local agents=(code-reviewer qa-tester security-auditor security-fixer perf-profiler infra-checker db-analyst dep-auditor)
  for agent in "${agents[@]}"; do
    if [[ -f "${AGENTS_DIR}/${agent}.md" ]]; then
      info "Agent: ${agent}"
      ok=$((ok + 1))
    else
      error "Agent NOT found: ${agent}"
      fail=$((fail + 1))
    fi
  done

  echo ""
  echo "Results: ${ok} installed, ${fail} missing"

  if [[ $fail -gt 0 ]]; then
    echo ""
    warn "Run './install.sh' to install missing components."
    return 1
  fi
}

remove_install() {
  echo "Removing autonomous pipeline..."
  echo ""

  if [[ -f "${SKILL_DIR}/skill.md" ]]; then
    rm "${SKILL_DIR}/skill.md"
    info "Removed pipeline skill"
    rmdir "${SKILL_DIR}" 2>/dev/null && info "Removed ${SKILL_DIR}" || true
  else
    warn "Pipeline skill not found (already removed?)"
  fi

  local agents=(code-reviewer qa-tester security-auditor security-fixer perf-profiler infra-checker db-analyst dep-auditor)
  for agent in "${agents[@]}"; do
    if [[ -f "${AGENTS_DIR}/${agent}.md" ]]; then
      rm "${AGENTS_DIR}/${agent}.md"
      info "Removed agent: ${agent}"
    fi
  done

  echo ""
  info "Removal complete."
}

# Main
case "${1:-}" in
  --symlink|-s)
    check_source && install_symlink
    ;;
  --check|-c)
    check_install
    ;;
  --remove|-r)
    remove_install
    ;;
  --help|-h)
    echo "Usage: ./install.sh [--symlink|--check|--remove|--help]"
    echo ""
    echo "  (default)    Copy files to ~/.claude/ (standalone)"
    echo "  --symlink    Symlink files (edits in source take effect immediately)"
    echo "  --check      Verify installation status"
    echo "  --remove     Remove installed files"
    ;;
  "")
    check_source && install_copy
    ;;
  *)
    error "Unknown option: $1"
    echo "Run './install.sh --help' for usage."
    exit 1
    ;;
esac
