#!/usr/bin/env bash
# Record /customise-workflow — AI-driven user preference capture.
#
# asciinema rec recordings/customise-workflow.cast -c './record-customise-workflow.sh'

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CUSTOMISE="$SKILL_ROOT/companion-skills/customise-workflow/script.py"

say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; sleep 1; }
run() { printf "\033[1;32m\$\033[0m %s\n" "$*"; sleep 0.5; eval "$@"; }

TMPDIR=$(mktemp -d)
cd "$TMPDIR"

say "== /customise-workflow demo =="
say "Step 1: load-config on a fresh project (no file yet)."
run "python3 $CUSTOMISE load-config | jq '.source, .user_customised'"

say "Step 2: list-questions — the AI asks these in sequence via AskUserQuestion."
run "python3 $CUSTOMISE list-questions | jq -r '.questions[] | \"  \\(.id): \\(.prompt)\"'"

say "Step 3: validate-answer — each user response is validated before write."
run "python3 $CUSTOMISE validate-answer --key provider.main --value gemini-cli | jq '.'"
run "python3 $CUSTOMISE validate-answer --key validation.strictness --value strict | jq '.'"

say "Step 4: write-config — answers committed to user-workflow.json."
cat > /tmp/demo-answers.json <<EOF
{
  "provider.main": "gemini-cli",
  "provider.model_main": "gemini-3-pro-preview",
  "validation.strictness": "strict",
  "execution.preferred_mode": "C",
  "autonomous.allow_self_brainstorm": true
}
EOF
run "python3 $CUSTOMISE write-config --input /tmp/demo-answers.json | jq '.keys_updated'"

say "Step 5: show-config — verify it's persisted."
run "python3 $CUSTOMISE show-config | jq '.config.provider, .config.validation, .config.execution'"

say "The AI never asked the user to edit JSON directly. Every answer was validated."
cd "$SKILL_ROOT"
rm -rf "$TMPDIR" /tmp/demo-answers.json
