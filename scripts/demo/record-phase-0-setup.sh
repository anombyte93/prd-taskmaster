#!/usr/bin/env bash
# Record Phase 0 SETUP — the zero-friction diagnostic loop.
#
# This script is meant to be wrapped in asciinema:
#   asciinema rec recordings/phase-0-setup.cast -c './record-phase-0-setup.sh'
#
# Or run standalone for a dry test:
#   ./record-phase-0-setup.sh

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$SKILL_ROOT/script.py"

say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; sleep 1; }
run() { printf "\033[1;32m\$\033[0m %s\n" "$*"; sleep 0.5; eval "$@"; }

TMPDIR=$(mktemp -d)
cd "$TMPDIR"

say "== Phase 0 SETUP demo =="
say "A fresh tmp dir with nothing installed."
run "ls -la"

say "Step 1: run validate-setup to see what's missing."
run "python3 $SCRIPT validate-setup | jq -r '.checks[] | \"[\\(.passed | tostring)] \\(.name): \\(.detail)\"'"

say "Notice: each failing check has a fix command."
run "python3 $SCRIPT validate-setup | jq -r '.checks[] | select(.passed == false) | \"  FIX: \\(.fix)\"'"

say "Step 2: copy-paste the fix commands."
run "task-master init --yes > /dev/null 2>&1 && echo '  ✓ task-master init'"
run "task-master models --set-main gemini-3-pro-preview --gemini-cli 2>&1 | tail -1"
run "task-master models --set-research gemini-3-pro-preview --gemini-cli 2>&1 | tail -1"
run "task-master models --set-fallback gemini-3-flash-preview --gemini-cli 2>&1 | tail -1"

say "Step 3: re-run validate-setup to confirm ready."
run "python3 $SCRIPT validate-setup | jq -r '\"ready: \\(.ready)  |  next_action: \\(.next_action)\"'"

say "Zero-friction Phase 0 complete. Total elapsed: ~30 seconds."
cd "$SKILL_ROOT"
rm -rf "$TMPDIR"
