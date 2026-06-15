#!/usr/bin/env bash
# A/B worker trial harness for the goose-gemini-vs-codex dogfood.
# usage: run_trial.sh <codex|gemini> <instr_file> <gate_script> <reset_path...>
# Runs the worker autonomously, runs the external gate, prints a one-line JSON
# result, then resets the named source paths to baseline (gate test files are kept).
set -u
WORKER="$1"; INSTR="$2"; GATE="$3"; shift 3; RESETS=("$@")
REPO=/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
BENCH="$REPO/.atlas-dogfood/bench"
cd "$REPO" || exit 9
export PATH="$HOME/.local/bin:$PATH"

start=$(date +%s)
if [ "$WORKER" = "gemini" ]; then
  GOOSE_PROVIDER=google GOOSE_MODEL=gemini-2.5-flash GOOSE_MODE=auto \
  GOOSE_DISABLE_KEYRING=1 GOOGLE_API_KEY="${GEMINI_API_KEY}" \
    timeout 480 goose run -i "$INSTR" > "$BENCH/worker_${WORKER}.log" 2>&1
  wrc=$?
elif [ "$WORKER" = "codex" ]; then
  timeout 480 codex exec --skip-git-repo-check \
    -c approval_policy='"never"' -c sandbox_mode='"workspace-write"' \
    - < "$INSTR" > "$BENCH/worker_${WORKER}.log" 2>&1
  wrc=$?
else
  echo "unknown worker: $WORKER"; exit 9
fi
end=$(date +%s)

bash "$GATE" > "$BENCH/gate_${WORKER}.log" 2>&1
grc=$?

diffstat=$(git diff --stat -- "${RESETS[@]}" 2>/dev/null | tail -1 | tr -s ' ')
verdict="FAIL"; [ "$grc" -eq 0 ] && verdict="PASS"
printf '{"worker":"%s","verdict":"%s","worker_rc":%s,"gate_rc":%s,"wall_s":%s,"diff":"%s"}\n' \
  "$WORKER" "$verdict" "$wrc" "$grc" "$((end-start))" "${diffstat}"

git checkout -- "${RESETS[@]}" 2>/dev/null
