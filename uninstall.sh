#!/usr/bin/env bash
# ============================================================================
# prd-taskmaster-v2 uninstaller (closes ship-readiness issue #20)
# ============================================================================
# Usage:
#   bash uninstall.sh          # interactive confirmation
#   bash uninstall.sh --yes    # non-interactive
#   bash uninstall.sh --dry-run
#
# Removes ~/.claude/skills/prd-taskmaster-v2/ and the update-tracker entry
# created by install.sh. Leaves user-generated .taskmaster/ artifacts in
# downstream projects alone — those are user data, not skill data.
# ============================================================================

set -euo pipefail

SKILL_NAME="prd-taskmaster-v2"
SKILL_DIR="${SKILL_DIR:-${HOME}/.claude/skills/${SKILL_NAME}}"
UPDATES_FILE="${HOME}/.config/claude-skills/updates.json"

YES=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y)    YES=1 ;;
        --dry-run)   DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

if { [[ -t 1 ]] || [[ -t 2 ]]; } && [[ -z "${CI:-}" ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

info() { printf "${CYAN}[info]${RESET}  %s\n" "$*" >&2; }
ok()   { printf "${GREEN}[ok]${RESET}    %s\n" "$*" >&2; }
warn() { printf "${YELLOW}[warn]${RESET}  %s\n" "$*" >&2; }
err()  { printf "${RED}[error]${RESET} %s\n" "$*" >&2; }

if [[ ! -d "${SKILL_DIR}" ]]; then
    warn "Skill not installed at ${SKILL_DIR} — nothing to do."
    exit 0
fi

info "Found skill at ${BOLD}${SKILL_DIR}${RESET}"
if [[ -f "${SKILL_DIR}/.version" ]]; then
    info "Installed version: $(head -1 "${SKILL_DIR}/.version" 2>/dev/null || echo unknown)"
fi

if [[ ${YES} -eq 0 ]] && [[ ${DRY_RUN} -eq 0 ]]; then
    printf "${YELLOW}Remove ${SKILL_DIR}? [y/N]${RESET} " >&2
    read -r reply
    case "$reply" in
        y|Y|yes|YES) ;;
        *) info "Aborted."; exit 0 ;;
    esac
fi

if [[ ${DRY_RUN} -eq 1 ]]; then
    info "[dry-run] would remove: ${SKILL_DIR}"
    [[ -f "${UPDATES_FILE}" ]] && info "[dry-run] would prune ${SKILL_NAME} entry from ${UPDATES_FILE}"
    exit 0
fi

rm -rf "${SKILL_DIR}"
ok "Removed ${SKILL_DIR}"

# Best-effort prune of the updates tracker entry. Non-fatal if jq is missing
# or the file doesn't exist — worst case a stale entry survives.
if [[ -f "${UPDATES_FILE}" ]] && command -v jq >/dev/null 2>&1; then
    tmp="$(mktemp)"
    if jq "del(.[\"${SKILL_NAME}\"])" "${UPDATES_FILE}" > "${tmp}" 2>/dev/null; then
        mv "${tmp}" "${UPDATES_FILE}"
        ok "Pruned ${SKILL_NAME} from ${UPDATES_FILE}"
    else
        rm -f "${tmp}"
        warn "Could not prune updates tracker (non-fatal)"
    fi
fi

ok "Uninstall complete. Downstream .taskmaster/ directories in your projects were left untouched."
