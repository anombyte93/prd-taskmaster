#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-quickstart.XXXXXX")"
ORIGINAL_PATH="${PATH}"

cleanup() {
    rm -rf "${WORKDIR}"
}
trap cleanup EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

write_fake_tools() {
    local bin_dir="$1"
    mkdir -p "${bin_dir}"

    cat > "${bin_dir}/task-master-ai" <<'TMEOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
    echo "task-master-ai 1.2.3"
else
    echo "task-master-ai ok"
fi
TMEOF

    cat > "${bin_dir}/task-master" <<'TMEOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .taskmaster/docs .taskmaster/tasks
    printf '{"currentTag":"master"}\n' > .taskmaster/state.json
    ;;
  parse-prd)
    mkdir -p .taskmaster/tasks
    cat > .taskmaster/tasks/tasks.json <<'JSON'
{"tasks":[{"id":1,"title":"Build CLI todo app","status":"pending","subtasks":[{"id":1,"title":"Create command parser","status":"pending"}]}]}
JSON
    ;;
  --version)
    echo "task-master 1.2.3"
    ;;
  *)
    echo "task-master fake: $*"
    ;;
esac
TMEOF

    cat > "${bin_dir}/git" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "clone" ]]; then
    dest="\${@: -1}"
    mkdir -p "\${dest}"
    cp -R "${ROOT}/." "\${dest}/"
    exit 0
fi
echo "unexpected git invocation: \$*" >&2
exit 1
EOF

    cat > "${bin_dir}/npm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == "install -g task-master-ai" ]]; then
    bin_dir="$(dirname "$0")"
    cat > "${bin_dir}/task-master-ai" <<'TMEOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
    echo "task-master-ai 1.2.3"
else
    echo "task-master-ai ok"
fi
TMEOF
    cat > "${bin_dir}/task-master" <<'TMEOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  init)
    mkdir -p .taskmaster/docs .taskmaster/tasks
    printf '{"currentTag":"master"}\n' > .taskmaster/state.json
    ;;
  parse-prd)
    mkdir -p .taskmaster/tasks
    cat > .taskmaster/tasks/tasks.json <<'JSON'
{"tasks":[{"id":1,"title":"Build CLI todo app","status":"pending","subtasks":[{"id":1,"title":"Create command parser","status":"pending"}]}]}
JSON
    ;;
  --version)
    echo "task-master 1.2.3"
    ;;
  *)
    echo "task-master fake: $*"
    ;;
esac
TMEOF
    chmod +x "${bin_dir}/task-master-ai" "${bin_dir}/task-master"
    exit 0
fi
echo "unexpected npm invocation: $*" >&2
exit 1
EOF

    chmod +x "${bin_dir}/git" "${bin_dir}/npm" "${bin_dir}/task-master-ai" "${bin_dir}/task-master"
}

HOME_DIR="${WORKDIR}/home"
PROJECT_DIR="${WORKDIR}/project"
BIN_DIR="${WORKDIR}/bin"
SKILL_DIR="${HOME_DIR}/.claude/skills/prd-taskmaster"
mkdir -p "${HOME_DIR}" "${PROJECT_DIR}"
write_fake_tools "${BIN_DIR}"

PATH="${BIN_DIR}:${ORIGINAL_PATH}" \
HOME="${HOME_DIR}" \
SKILL_DIR="${SKILL_DIR}" \
ATLAS_TELEMETRY=0 \
CI=1 \
bash "${ROOT}/install.sh" > "${WORKDIR}/install.out"

grep -q 'Try: /atlas or say "I want to build..."' "${WORKDIR}/install.out" \
    || fail "install output missing first-run hint"
test -f "${SKILL_DIR}/SKILL.md" || fail "installed SKILL.md missing"
test -f "${SKILL_DIR}/script.py" || fail "installed script.py missing"
test -d "${SKILL_DIR}/prd_taskmaster" || fail "installed package missing"

cd "${PROJECT_DIR}"
PATH="${BIN_DIR}:${ORIGINAL_PATH}" HOME="${HOME_DIR}" python3 "${SKILL_DIR}/script.py" preflight > "${WORKDIR}/preflight.json"
python3 - "${WORKDIR}/preflight.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    data = json.load(fh)
if data.get("ok") is not True:
    raise SystemExit(f"preflight did not return ok JSON: {data}")
PY

if command -v task-master >/dev/null 2>&1; then
    PATH="${BIN_DIR}:${ORIGINAL_PATH}" HOME="${HOME_DIR}" task-master init --yes
else
    printf 'quickstart notice: task-master unavailable; skipping task-master init\n'
fi

mkdir -p .taskmaster/docs
cat > .taskmaster/docs/prd.md <<'EOF'
# CLI Todo App

Build a small command-line todo app with add, list, complete, and delete commands.
EOF

if [[ "${QUICKSTART_LIVE:-0}" == "1" ]]; then
    PATH="${BIN_DIR}:${ORIGINAL_PATH}" HOME="${HOME_DIR}" task-master parse-prd --input .taskmaster/docs/prd.md --num-tasks 3
    python3 - <<'PY'
import json
from pathlib import Path

path = Path(".taskmaster/tasks/tasks.json")
data = json.loads(path.read_text())
tasks = data.get("tasks", [])
if not tasks:
    raise SystemExit("tasks.json contains no tasks")
PY
else
    printf 'quickstart live parse skipped (set QUICKSTART_LIVE=1)\n'
fi

printf 'quickstart deterministic path ok\n'
