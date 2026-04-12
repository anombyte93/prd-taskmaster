#!/usr/bin/env bash
# Record Phase 4 HANDOFF — tool-agnostic mode recommendation.
#
# asciinema rec recordings/phase-4-handoff.cast -c './record-phase-4-handoff.sh'

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$SKILL_ROOT/script.py"

say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; sleep 1; }
run() { printf "\033[1;32m\$\033[0m %s\n" "$*"; sleep 0.5; eval "$@"; }

say "== Phase 4 HANDOFF demo =="
say "v4 detects installed AI tools and recommends ONE primary mode."
say "It also lists alternative modes for external tools you have installed."

run "python3 $SCRIPT detect-capabilities | jq '.tier, .recommended_mode, .recommended_reason'"

say "Detected external AI tools:"
run "python3 $SCRIPT detect-capabilities | jq '.capabilities | with_entries(select(.key | test(\"cursor|codex|gemini-cli|roo|coderabbit|aider|continue\")))'"

say "Alternative execution modes (user can pick any of these instead):"
run "python3 $SCRIPT detect-capabilities | jq -r '.alternative_modes[] | \"  Mode \\(.mode) (\\(.tool)): \\(.description)\"'"

say "Phase 4 complete — user picks a mode and hands off."
