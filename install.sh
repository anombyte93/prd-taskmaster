#!/usr/bin/env bash
# ============================================================================
# Universal Claude Code Skill Installer
# ============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | bash
#   bash install.sh                # fresh install or upgrade
#   bash install.sh --with-taskmaster # also install the optional TaskMaster backend
#   bash install.sh --no-taskmaster   # skip the optional TaskMaster backend offer
#   bash install.sh --check-update # check for newer version only
#
# Customize the variables below for your skill repository.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Skill Configuration (customize these per-repo)
# ---------------------------------------------------------------------------
REPO_OWNER="anombyte93"
REPO_NAME="prd-taskmaster"
SKILL_NAME="prd-taskmaster"
VERSION="4.0.0"
SKILL_DIR="${SKILL_DIR:-${HOME}/.claude/skills/${SKILL_NAME}}"
ALIAS_NAME="atlas"
ALIAS_DIR="${HOME}/.claude/skills/${ALIAS_NAME}"
TASKMASTER_INSTALL_MODE="ask"

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------
UPDATES_DIR="${HOME}/.config/claude-skills"
UPDATES_FILE="${UPDATES_DIR}/updates.json"
UPDATE_INTERVAL_SECONDS=86400  # 24 hours
GITHUB_API="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
CLONE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"

# ---------------------------------------------------------------------------
# Colors (disabled when piped or in CI)
# ---------------------------------------------------------------------------
if [[ -t 1 ]] && [[ -z "${CI:-}" ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' RESET=''
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf "${CYAN}[info]${RESET}  %s\n" "$*"; }
ok()    { printf "${GREEN}[ok]${RESET}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${RESET}  %s\n" "$*"; }
err()   { printf "${RED}[error]${RESET} %s\n" "$*" >&2; }
die()   { err "$@"; exit 1; }

cleanup() {
    if [[ -n "${TMPDIR_SKILL:-}" ]] && [[ -d "${TMPDIR_SKILL}" ]]; then
        rm -rf "${TMPDIR_SKILL}"
    fi
}
trap cleanup EXIT

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

set_taskmaster_install_mode() {
    local requested="$1"
    if [[ "${TASKMASTER_INSTALL_MODE}" != "ask" ]] && [[ "${TASKMASTER_INSTALL_MODE}" != "${requested}" ]]; then
        die "Conflicting TaskMaster backend flags: choose --with-taskmaster or --no-taskmaster"
    fi
    TASKMASTER_INSTALL_MODE="${requested}"
}

install_taskmaster_backend() {
    info "Installing optional task-master-ai package (unlocks the TaskMaster backend)"

    if command -v task-master-ai >/dev/null 2>&1; then
        ok "TaskMaster backend already available"
        return 0
    fi

    if ! command -v npm >/dev/null 2>&1; then
        warn "npm not found; skipping optional TaskMaster backend install"
        warn "Atlas native backend remains available"
        return 0
    fi

    if npm install -g task-master-ai; then
        ok "Installed optional TaskMaster backend"
    else
        warn "Optional TaskMaster backend install failed"
        warn "Atlas native backend remains available"
    fi
}

offer_taskmaster_backend() {
    case "${TASKMASTER_INSTALL_MODE}" in
        with)
            install_taskmaster_backend
            ;;
        without)
            info "Skipping optional TaskMaster backend install (--no-taskmaster)"
            ;;
        ask)
            if [[ ! -t 0 ]]; then
                info "Non-interactive shell; skipping optional TaskMaster backend install"
                info "Use --with-taskmaster to install task-master-ai when you want the TaskMaster backend"
                return 0
            fi

            local answer
            printf "Install optional task-master-ai package (unlocks the TaskMaster backend)? [Y/n] "
            read -r answer || answer=""
            case "${answer:-Y}" in
                Y|y|YES|Yes|yes)
                    install_taskmaster_backend
                    ;;
                N|n|NO|No|no)
                    info "Skipping optional TaskMaster backend install"
                    ;;
                *)
                    warn "Unrecognized answer; skipping optional TaskMaster backend install"
                    ;;
            esac
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Update check (callable standalone)
# ---------------------------------------------------------------------------
check_update() {
    # Respect CI / explicit opt-out
    if [[ -n "${CI:-}" ]] || [[ -n "${NO_UPDATE_CHECK:-}" ]]; then
        return 0
    fi

    require_cmd curl
    require_cmd date

    mkdir -p "${UPDATES_DIR}"

    # Throttle: only check once per UPDATE_INTERVAL_SECONDS
    if [[ -f "${UPDATES_FILE}" ]]; then
        local last_check
        last_check=$(python3 -c "
import json, sys
try:
    d = json.load(open('${UPDATES_FILE}'))
    print(d.get('skills', {}).get('${SKILL_NAME}', {}).get('last_check', 0))
except Exception:
    print(0)
" 2>/dev/null || echo 0)

        local now
        now=$(date +%s)
        local elapsed=$(( now - last_check ))

        if [[ ${elapsed} -lt ${UPDATE_INTERVAL_SECONDS} ]]; then
            # Within cooldown -- read cached result
            local cached_latest
            cached_latest=$(python3 -c "
import json
try:
    d = json.load(open('${UPDATES_FILE}'))
    print(d.get('skills', {}).get('${SKILL_NAME}', {}).get('latest', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

            if [[ -n "${cached_latest}" ]] && [[ "${cached_latest}" != "${VERSION}" ]]; then
                warn "Update available: ${VERSION} -> ${cached_latest}"
                info "Run: curl -fsSL https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/install.sh | bash"
            fi
            return 0
        fi
    fi

    # Fetch latest release from GitHub API
    local api_response
    api_response=$(curl -fsSL --max-time 5 \
        -H "Accept: application/vnd.github+json" \
        "${GITHUB_API}" 2>/dev/null) || {
        # Network failure is non-fatal for update checks
        return 0
    }

    local latest_version
    latest_version=$(printf '%s' "${api_response}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tag = data.get('tag_name', '')
    # Strip leading 'v' if present
    print(tag.lstrip('v'))
except Exception:
    print('')
" 2>/dev/null || echo "")

    if [[ -z "${latest_version}" ]]; then
        return 0
    fi

    # Write cache
    local now
    now=$(date +%s)
    python3 -c "
import json, os

path = '${UPDATES_FILE}'
try:
    data = json.load(open(path))
except Exception:
    data = {}

data.setdefault('skills', {})
data['skills']['${SKILL_NAME}'] = {
    'last_check': ${now},
    'latest': '${latest_version}',
    'current': '${VERSION}'
}

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || true

    if [[ "${latest_version}" != "${VERSION}" ]]; then
        warn "Update available: ${VERSION} -> ${latest_version}"
        info "Run: curl -fsSL https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/install.sh | bash"
    else
        ok "You are on the latest version (${VERSION})"
    fi
}

# ---------------------------------------------------------------------------
# Install logic
# ---------------------------------------------------------------------------
install_skill() {
    local mode="install"

    info "Claude Code Skill Installer"
    info "Skill: ${BOLD}${SKILL_NAME}${RESET} v${VERSION}"
    printf "\n"

    require_cmd git

    # ------------------------------------------------------------------
    # Detect upgrade vs fresh install
    # ------------------------------------------------------------------
    if [[ -d "${SKILL_DIR}" ]]; then
        mode="upgrade"
        local existing_version="unknown"
        if [[ -f "${SKILL_DIR}/.version" ]]; then
            existing_version=$(head -1 "${SKILL_DIR}/.version" 2>/dev/null || echo "unknown")
        fi
        info "Existing installation detected (${existing_version})"
        info "Mode: upgrade"

        # Back up SKILL.md if it exists
        if [[ -f "${SKILL_DIR}/SKILL.md" ]]; then
            cp "${SKILL_DIR}/SKILL.md" "${SKILL_DIR}/SKILL.md.bak"
            ok "Backed up SKILL.md -> SKILL.md.bak"
        fi
    else
        info "Mode: fresh install"
    fi

    # ------------------------------------------------------------------
    # Clone repo to temp directory
    # ------------------------------------------------------------------
    TMPDIR_SKILL=$(mktemp -d "${TMPDIR:-/tmp}/claude-skill-XXXXXX")
    info "Cloning ${REPO_OWNER}/${REPO_NAME}..."

    git clone --depth 1 --quiet "${CLONE_URL}" "${TMPDIR_SKILL}/repo" 2>/dev/null \
        || die "Failed to clone repository. Check REPO_OWNER/REPO_NAME and network."

    # ------------------------------------------------------------------
    # Locate skill source within the repo
    # ------------------------------------------------------------------
    # Convention: skill files live at repo root OR under a directory named
    # after the skill. We check both.
    local src_dir="${TMPDIR_SKILL}/repo"
    if [[ -d "${TMPDIR_SKILL}/repo/${SKILL_NAME}" ]]; then
        src_dir="${TMPDIR_SKILL}/repo/${SKILL_NAME}"
    fi

    # Verify at minimum SKILL.md exists
    if [[ ! -f "${src_dir}/SKILL.md" ]]; then
        die "SKILL.md not found in repository (checked ${src_dir}). Cannot install."
    fi

    # ------------------------------------------------------------------
    # Copy skill files to SKILL_DIR
    # ------------------------------------------------------------------
    mkdir -p "${SKILL_DIR}"

    # Core file: SKILL.md (always required)
    cp "${src_dir}/SKILL.md" "${SKILL_DIR}/SKILL.md"
    ok "Installed SKILL.md"

    # Required: script.py shim + the prd_taskmaster package it imports
    if [[ -f "${src_dir}/script.py" ]]; then
        cp "${src_dir}/script.py" "${SKILL_DIR}/script.py"
        ok "Installed script.py"
    fi
    if [[ -d "${src_dir}/prd_taskmaster" ]]; then
        rm -rf "${SKILL_DIR}/prd_taskmaster"
        cp -r "${src_dir}/prd_taskmaster" "${SKILL_DIR}/prd_taskmaster"
        # drop bytecode caches so the copy is clean
        rm -rf "${SKILL_DIR}/prd_taskmaster/__pycache__"
        ok "Installed prd_taskmaster/ package"
    fi

    # Optional: phases/ directory (the 4-phase runbooks)
    if [[ -d "${src_dir}/phases" ]]; then
        rm -rf "${SKILL_DIR}/phases"
        cp -r "${src_dir}/phases" "${SKILL_DIR}/phases"
        ok "Installed phases/"
    fi

    # Optional: templates/ directory
    if [[ -d "${src_dir}/templates" ]]; then
        rm -rf "${SKILL_DIR}/templates"
        cp -r "${src_dir}/templates" "${SKILL_DIR}/templates"
        ok "Installed templates/"
    fi

    # Optional: reference/ directory
    if [[ -d "${src_dir}/reference" ]]; then
        rm -rf "${SKILL_DIR}/reference"
        cp -r "${src_dir}/reference" "${SKILL_DIR}/reference"
        ok "Installed reference/"
    fi

    # Optional: install.sh itself (so the skill is self-updating)
    if [[ -f "${src_dir}/install.sh" ]]; then
        cp "${src_dir}/install.sh" "${SKILL_DIR}/install.sh"
        chmod +x "${SKILL_DIR}/install.sh"
    fi

    # ------------------------------------------------------------------
    # Write .version file
    # ------------------------------------------------------------------
    local timestamp
    timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    cat > "${SKILL_DIR}/.version" <<VEOF
${VERSION}
installed: ${timestamp}
mode: ${mode}
repo: ${REPO_OWNER}/${REPO_NAME}
VEOF
    ok "Wrote .version (${VERSION}, ${timestamp})"

    # ------------------------------------------------------------------
    # Install the /atlas alias skill (thin delegator to this skill)
    # ------------------------------------------------------------------
    mkdir -p "${ALIAS_DIR}"
    cat > "${ALIAS_DIR}/SKILL.md" <<ALIASEOF
---
name: ${ALIAS_NAME}
description: >-
  The Atlas engine — turn any goal into a validated PRD and an executable,
  verified task graph. Alias for the prd-taskmaster skill. Use when the user
  invokes /atlas, says "I want to build", or asks for a PRD / task-driven build.
allowed-tools:
  - Read
  - Skill
  - Bash
---

# /atlas — the Atlas engine

This is a thin alias. Immediately Read and follow the full engine skill:

\`\`\`
Read ${SKILL_DIR}/SKILL.md
\`\`\`

Then execute that skill's pipeline (Preflight -> Discovery -> Generate -> Handoff)
exactly as written, carrying over whatever goal or arguments the user provided.
ALIASEOF
    ok "Installed /atlas alias skill -> ${ALIAS_DIR}"

    # ------------------------------------------------------------------
    # Deprecation: superseded standalone prd-taskmaster-v2 skill dir
    # ------------------------------------------------------------------
    local legacy_dir="${HOME}/.claude/skills/prd-taskmaster-v2"
    if [[ -d "${legacy_dir}" ]]; then
        warn "Found legacy skill dir: ${legacy_dir}"
        warn "It is superseded by prd-taskmaster v${VERSION}. Remove it with:"
        printf "    rm -rf %s\n" "${legacy_dir}"
    fi

    offer_taskmaster_backend

    # ------------------------------------------------------------------
    # Success
    # ------------------------------------------------------------------
    printf "\n"
    printf "${GREEN}${BOLD}Successfully %s ${SKILL_NAME} v${VERSION}${RESET}\n" \
        "$([ "${mode}" = "upgrade" ] && echo "upgraded" || echo "installed")"
    printf "  Location: %s\n" "${SKILL_DIR}"

    if [[ "${mode}" = "upgrade" ]] && [[ -f "${SKILL_DIR}/SKILL.md.bak" ]]; then
        printf "  Backup:   %s\n" "${SKILL_DIR}/SKILL.md.bak"
    fi

    printf "\n"
    info "Open any project in Claude Code and type:"
    printf "  ${CYAN}/atlas${RESET}   (or ${CYAN}/%s${RESET}, or just say \"I want to build …\")\n" "${SKILL_NAME}"
    printf "\n"
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
main() {
    local action="install"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check-update|-u)
                action="check-update"
                ;;
            --version|-v)
                action="version"
                ;;
            --help|-h)
                action="help"
                ;;
            --with-taskmaster)
                set_taskmaster_install_mode "with"
                ;;
            --no-taskmaster)
                set_taskmaster_install_mode "without"
                ;;
            *)
                die "Unknown argument: $1 (try --help)"
                ;;
        esac
        shift
    done

    case "${action}" in
        check-update)
            check_update
            ;;
        version)
            echo "${SKILL_NAME} v${VERSION}"
            ;;
        help)
            printf "Usage: %s [--with-taskmaster | --no-taskmaster | --check-update | --version | --help]\n" "${0##*/}"
            printf "\n"
            printf "  (no args)           Install or upgrade the skill\n"
            printf "  --with-taskmaster   Install optional task-master-ai package\n"
            printf "  --no-taskmaster     Skip optional TaskMaster backend install\n"
            printf "  --check-update      Check GitHub for a newer release\n"
            printf "  --version           Print current version\n"
            printf "  --help              Show this help\n"
            ;;
        install)
            install_skill
            check_update
            ;;
    esac
}

main "$@"
