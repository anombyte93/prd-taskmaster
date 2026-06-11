#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="${SCRIPT_UNDER_TEST:-${ROOT}/install.sh}"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-install-telemetry.XXXXXX")"
BASH_BIN="$(command -v bash)"

cleanup() {
    rm -rf "${WORKDIR}"
}
trap cleanup EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

make_fake_repo() {
    local repo="${WORKDIR}/fake-repo"
    mkdir -p "${repo}/prd_taskmaster"
    printf '# fake skill\n' > "${repo}/SKILL.md"
    printf 'print("atlas")\n' > "${repo}/script.py"
    printf '' > "${repo}/prd_taskmaster/__init__.py"
    printf 'def send_event(event):\n    pass\n' > "${repo}/prd_taskmaster/telemetry.py"
    printf '#!/usr/bin/env bash\n' > "${repo}/install.sh"
    chmod +x "${repo}/install.sh"
    printf '%s\n' "${repo}"
}

make_bin_dir() {
    local bin_dir="$1"
    local fake_repo="$2"
    mkdir -p "${bin_dir}"
    for cmd in bash cp mkdir mktemp rm chmod head date cat; do
        if command -v "${cmd}" >/dev/null 2>&1; then
            ln -sf "$(command -v "${cmd}")" "${bin_dir}/${cmd}"
        fi
    done
    cat > "${bin_dir}/git" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "clone" ]]; then
    dest="\${@: -1}"
    mkdir -p "\${dest}"
    cp -R "${fake_repo}/." "\${dest}/"
    exit 0
fi
echo "unexpected git invocation: \$*" >&2
exit 1
EOF
    chmod +x "${bin_dir}/git"
    cat > "${bin_dir}/task-master-ai" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
    echo "task-master-ai 1.2.3"
else
    echo "task-master-ai ok"
fi
EOF
    chmod +x "${bin_dir}/task-master-ai"
}

add_python_stub() {
    local bin_dir="$1"
    cat > "${bin_dir}/python3" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${PYTHON_LOG}"
exit 0
EOF
    chmod +x "${bin_dir}/python3"
}

make_no_python_bin_dir() {
    local bin_dir="$1"
    local fake_repo="$2"
    make_bin_dir "${bin_dir}" "${fake_repo}"
}

run_install() {
    local name="$1"
    local bin_dir="$2"
    shift 2
    local home="${WORKDIR}/home-${name}"
    local log="${WORKDIR}/${name}.python.log"
    mkdir -p "${home}"
    : > "${log}"
    HOME="${home}" \
    SKILL_DIR="${home}/skill" \
    PYTHON_LOG="${log}" \
    CI=1 \
    PATH="${bin_dir}" \
    "${BASH_BIN}" "${SCRIPT_UNDER_TEST}" "$@" >/dev/null
    printf '%s\n' "${log}"
}

fake_repo="$(make_fake_repo)"

default_bin="${WORKDIR}/bin-default"
make_bin_dir "${default_bin}" "${fake_repo}"
add_python_stub "${default_bin}"
default_log="$(run_install default "${default_bin}")"
default_count="$(grep -c 'send_event("install")' "${default_log}" || true)"
[[ "${default_count}" == "1" ]] || fail "default install should invoke install telemetry once, got ${default_count}"

flag_bin="${WORKDIR}/bin-flag"
make_bin_dir "${flag_bin}" "${fake_repo}"
add_python_stub "${flag_bin}"
flag_log="$(run_install flag "${flag_bin}" --no-telemetry)"
flag_count="$(grep -c 'send_event("install")' "${flag_log}" || true)"
[[ "${flag_count}" == "0" ]] || fail "--no-telemetry should suppress telemetry, got ${flag_count}"

env_bin="${WORKDIR}/bin-env"
make_bin_dir "${env_bin}" "${fake_repo}"
add_python_stub "${env_bin}"
env_log="$(ATLAS_TELEMETRY=0 run_install env "${env_bin}")"
env_count="$(grep -c 'send_event("install")' "${env_log}" || true)"
[[ "${env_count}" == "0" ]] || fail "ATLAS_TELEMETRY=0 should suppress telemetry, got ${env_count}"

no_python_bin="${WORKDIR}/bin-no-python"
make_no_python_bin_dir "${no_python_bin}" "${fake_repo}"
run_install no-python "${no_python_bin}" >/dev/null || fail "install should succeed when python3 is absent"

printf 'install telemetry shell tests passed\n'
