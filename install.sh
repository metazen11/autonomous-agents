#!/usr/bin/env bash
#
# install.sh — Export the prompt pack to a target directory
#
# Usage:
#   ./install.sh --target /path/to/export
#   ./install.sh --target /path/to/export --symlink
#   ./install.sh --target /path/to/export --check
#   ./install.sh --target /path/to/export --remove
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR=""
MODE="copy"
ACTION="install"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

usage() {
  cat <<'EOF'
Usage: ./install.sh --target /path/to/export [--symlink] [--check|--remove]

Exports this repository's prompt pack to a target directory without assuming a
specific host runtime. Host-specific wiring should happen separately.

Options:
  --target DIR   Required. Destination directory.
  --symlink      Symlink files instead of copying them.
  --check        Verify exported files at the target directory.
  --remove       Remove exported files from the target directory.
  --help         Show this help message.
EOF
}

require_target() {
  if [[ -z "${TARGET_DIR}" ]]; then
    error "Missing required --target argument."
    usage
    exit 1
  fi
}

check_source() {
  local missing=0
  local required=(
    "README.md"
    "plan.txt"
    "pipeline/autonomous.md"
    "agents/AGENT_AGNOSTIC_GUIDE.md"
  )

  for path in "${required[@]}"; do
    if [[ ! -f "${SCRIPT_DIR}/${path}" ]]; then
      error "Missing: ${path}"
      missing=1
    fi
  done

  local agents=(
    code-reviewer
    qa-tester
    security-auditor
    security-fixer
    dep-auditor
    db-analyst
    perf-profiler
    infra-checker
    soc2-auditor
    hipaa-auditor
    compliance-fixer
    skill-promoter
  )

  for agent in "${agents[@]}"; do
    if [[ ! -f "${SCRIPT_DIR}/agents/${agent}.md" ]]; then
      error "Missing: agents/${agent}.md"
      missing=1
    fi
  done

  return "${missing}"
}

link_or_copy() {
  local src="$1"
  local dst="$2"

  mkdir -p "$(dirname "${dst}")"
  if [[ "${MODE}" == "symlink" ]]; then
    ln -sf "${src}" "${dst}"
  else
    cp "${src}" "${dst}"
  fi
}

install_pack() {
  require_target
  check_source

  echo "Exporting prompt pack to ${TARGET_DIR} (${MODE})..."
  echo ""

  link_or_copy "${SCRIPT_DIR}/README.md" "${TARGET_DIR}/README.md"
  info "README.md"

  link_or_copy "${SCRIPT_DIR}/plan.txt" "${TARGET_DIR}/plan.txt"
  info "plan.txt"

  link_or_copy "${SCRIPT_DIR}/pipeline/autonomous.md" "${TARGET_DIR}/pipeline/autonomous.md"
  info "pipeline/autonomous.md"

  link_or_copy "${SCRIPT_DIR}/agents/AGENT_AGNOSTIC_GUIDE.md" "${TARGET_DIR}/agents/AGENT_AGNOSTIC_GUIDE.md"
  info "agents/AGENT_AGNOSTIC_GUIDE.md"

  for f in "${SCRIPT_DIR}"/agents/*.md; do
    [[ "$(basename "${f}")" == "AGENT_AGNOSTIC_GUIDE.md" ]] && continue
    link_or_copy "${f}" "${TARGET_DIR}/agents/$(basename "${f}")"
    info "agents/$(basename "${f}")"
  done

  echo ""
  info "Export complete."
}

check_pack() {
  require_target

  local missing=0
  local required=(
    "README.md"
    "plan.txt"
    "pipeline/autonomous.md"
    "agents/AGENT_AGNOSTIC_GUIDE.md"
    "agents/code-reviewer.md"
    "agents/qa-tester.md"
    "agents/security-auditor.md"
    "agents/security-fixer.md"
    "agents/dep-auditor.md"
    "agents/db-analyst.md"
    "agents/perf-profiler.md"
    "agents/infra-checker.md"
    "agents/soc2-auditor.md"
    "agents/hipaa-auditor.md"
    "agents/compliance-fixer.md"
    "agents/skill-promoter.md"
  )

  echo "Checking exported prompt pack at ${TARGET_DIR}..."
  echo ""

  for path in "${required[@]}"; do
    if [[ -e "${TARGET_DIR}/${path}" ]]; then
      info "${path}"
    else
      error "Missing: ${path}"
      missing=1
    fi
  done

  echo ""
  if [[ "${missing}" -eq 0 ]]; then
    info "Export is complete."
  else
    warn "Export is incomplete."
    return 1
  fi
}

remove_pack() {
  require_target

  echo "Removing exported prompt pack from ${TARGET_DIR}..."
  echo ""

  rm -f "${TARGET_DIR}/README.md"
  rm -f "${TARGET_DIR}/plan.txt"
  rm -f "${TARGET_DIR}/pipeline/autonomous.md"
  rm -f "${TARGET_DIR}/agents/AGENT_AGNOSTIC_GUIDE.md"
  rm -f "${TARGET_DIR}/agents/code-reviewer.md"
  rm -f "${TARGET_DIR}/agents/qa-tester.md"
  rm -f "${TARGET_DIR}/agents/security-auditor.md"
  rm -f "${TARGET_DIR}/agents/security-fixer.md"
  rm -f "${TARGET_DIR}/agents/dep-auditor.md"
  rm -f "${TARGET_DIR}/agents/db-analyst.md"
  rm -f "${TARGET_DIR}/agents/perf-profiler.md"
  rm -f "${TARGET_DIR}/agents/infra-checker.md"
  rm -f "${TARGET_DIR}/agents/soc2-auditor.md"
  rm -f "${TARGET_DIR}/agents/hipaa-auditor.md"
  rm -f "${TARGET_DIR}/agents/compliance-fixer.md"
  rm -f "${TARGET_DIR}/agents/skill-promoter.md"

  rmdir "${TARGET_DIR}/agents" 2>/dev/null || true
  rmdir "${TARGET_DIR}/pipeline" 2>/dev/null || true
  rmdir "${TARGET_DIR}" 2>/dev/null || true

  info "Removal complete."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="${2:-}"
      shift 2
      ;;
    --symlink|-s)
      MODE="symlink"
      shift
      ;;
    --check|-c)
      ACTION="check"
      shift
      ;;
    --remove|-r)
      ACTION="remove"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

case "${ACTION}" in
  install)
    install_pack
    ;;
  check)
    check_pack
    ;;
  remove)
    remove_pack
    ;;
esac
