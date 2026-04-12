#!/usr/bin/env bash
# Record Phase 3 GENERATE — template load → PRD content → validate → parse tasks.
#
# asciinema rec recordings/phase-3-generate.cast -c './record-phase-3-generate.sh'

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$SKILL_ROOT/script.py"

say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; sleep 1; }
run() { printf "\033[1;32m\$\033[0m %s\n" "$*"; sleep 0.5; eval "$@"; }

TMPDIR=$(mktemp -d)
cd "$TMPDIR"
task-master init --yes > /dev/null 2>&1 || true

say "== Phase 3 GENERATE demo =="
say "Step 1: load the comprehensive template."
run "python3 $SCRIPT load-template --type comprehensive | jq -r '.line_count as \$n | \"template: \\(\$n) lines\"'"

say "Step 2: use the existing demo PRD from the repo's own dogfood."
cp "$SKILL_ROOT/.taskmaster/docs/prd.md" .taskmaster/docs/prd.md 2>/dev/null || {
  echo "# Test PRD" > .taskmaster/docs/prd.md
  echo "(using minimal test content)" >> .taskmaster/docs/prd.md
}
run "wc -l .taskmaster/docs/prd.md"

say "Step 3: validate-prd — 13 deterministic checks."
run "python3 $SCRIPT validate-prd --input .taskmaster/docs/prd.md | jq -r '\"grade: \\(.grade)  score: \\(.score)/\\(.max_score) (\\(.percentage)%)  checks: \\(.checks_passed)/\\(.checks_total)\"'"

say "Step 4: parse-prd through the configured provider."
run "task-master parse-prd --input .taskmaster/docs/prd.md --num-tasks 5 2>&1 | grep -E 'Provider|Model|Tokens|Cost' | head -4"

say "Step 5: inspect resulting task graph."
run "task-master list --format text 2>&1 | head -20"

say "Phase 3 complete — PRD validated, tasks parsed, dependency graph built."
cd "$SKILL_ROOT"
rm -rf "$TMPDIR"
