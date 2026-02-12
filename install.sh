#!/usr/bin/env bash
# ============================================================================
# Universal Claude Code Skill Installer
# ============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | bash
#   bash install.sh                # fresh install or upgrade
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
VERSION="3.0.0"
SKILL_DIR="${SKILL_DIR:-${HOME}/.claude/skills/${SKILL_NAME}}"

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

    # Optional: script.py (or any .py entrypoint)
    if [[ -f "${src_dir}/script.py" ]]; then
        cp "${src_dir}/script.py" "${SKILL_DIR}/script.py"
        ok "Installed script.py"
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
    info "To use this skill in Claude Code, reference it with:"
    printf "  ${CYAN}/%s${RESET}\n" "${SKILL_NAME}"
    printf "\n"
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
main() {
    case "${1:-}" in
        --check-update|-u)
            check_update
            ;;
        --version|-v)
            echo "${SKILL_NAME} v${VERSION}"
            ;;
        --help|-h)
            printf "Usage: %s [--check-update | --version | --help]\n" "${0##*/}"
            printf "\n"
            printf "  (no args)       Install or upgrade the skill\n"
            printf "  --check-update  Check GitHub for a newer release\n"
            printf "  --version       Print current version\n"
            printf "  --help          Show this help\n"
            ;;
        "")
            install_skill
            check_update
            ;;
        *)
            die "Unknown argument: $1 (try --help)"
            ;;
    esac
}

main "$@"
