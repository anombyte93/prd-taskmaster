#!/usr/bin/env bash
# External gate for T2 (_parse_version 3-tuple). pytest + ruff, both must pass.
set -u
REPO=/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
cd "$REPO" || exit 9
env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  python -m pytest tests/core/test_parse_version_tuple.py -q || exit 1
ruff check prd_taskmaster/mode_recommend.py || exit 1
echo "GATE_OK"
