# Subtask T3: gate google/gemini providers on a Google API key

Work in the current repo (prd-taskmaster-public). This is a cross-file change.
Edit ONLY these two source files (do NOT touch anything under tests/):
  - prd_taskmaster/providers.py
  - prd_taskmaster/mode_recommend.py

## Why
`llm_client` now supports a raw-API `google` provider (GOOGLE_API_KEY / GEMINI_API_KEY).
But `_provider_usable()` still treats `google`/`gemini` as unknown providers and
returns True (assumed usable). So `validate_setup` green-lights a `google` main
model even with NO Google key — the same silent "0 tasks" defect already prevented
for anthropic/openai. Fix it.

## Required changes
1. In `prd_taskmaster/providers.py`, function `_provider_usable`:
   - Add a new keyword-only parameter `has_google_key: bool = False` (MUST default
     to False so existing callers keep working).
   - Treat provider names `"google"` and `"gemini"` (case-insensitive) as usable
     ONLY when `has_google_key` is True.
   - Leave all other behaviour unchanged: anthropic/openai/perplexity/claude-code/
     codex-cli as-is, and genuinely unknown providers (openrouter, ollama, …) still
     return True.

2. In `prd_taskmaster/mode_recommend.py`, function `validate_setup`:
   - Where it builds `usable_kwargs` for `_provider_usable`, also compute and pass
     `has_google_key` = bool(os.environ.get("GOOGLE_API_KEY") or
     os.environ.get("GEMINI_API_KEY")).
   - This makes the `provider_main` check fail for a google main with no key, and
     pass when a Google key is present.

## Hard constraints
- Edit ONLY the two source files named above. Do NOT modify any test file.
- Pure stdlib. Keep existing tests green.

## Acceptance (must pass before declaring done)
    python -m pytest tests/core/test_provider_usable_google.py tests/core/test_mode_recommend_validate.py -q
    ruff check prd_taskmaster/providers.py prd_taskmaster/mode_recommend.py
Iterate until pytest is all-green AND ruff says "All checks passed".
