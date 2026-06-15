#!/usr/bin/env bash
# External gate for T3 (google-aware _provider_usable + validate_setup wiring).
# pytest (new contract + existing validate regression) + ruff, all must pass.
set -u
REPO=/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
cd "$REPO" || exit 9
env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u OPENAI_COMPATIBLE_API_KEY \
  python -m pytest tests/core/test_provider_usable_google.py tests/core/test_mode_recommend_validate.py -q || exit 1
ruff check prd_taskmaster/providers.py prd_taskmaster/mode_recommend.py || exit 1
echo "GATE_OK"
