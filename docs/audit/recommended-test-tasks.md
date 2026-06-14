# Recommended Test Tasks — must go GREEN (and prove RED) before viral relaunch

Prioritized by `riskIfFalse × current evidence weakness`. Each task names the claim it protects,
the exact test to add/fix, the assertions, why current coverage is insufficient, and the command
that verifies it. Several existing tests must be FIXED, not just added — they currently lock the bug.

The prior audit (`defect-register.json` P2-6) named 6 regression tests. They are validated and
extended below as T1-T8 (T1-T6 ≈ the original six; T7-T8 added: the anti-regression-lock fix and the
parallel-path argument-drop guard, which the original list under-specified).

---

## P0 — these block relaunch

### T1 — configure-providers CORRECTS a keyless anthropic stock default (protects C1 / P0-1)
- **Add** `tests/core/test_dogfood_fixes.py::test_configure_providers_corrects_keyless_stock_anthropic_to_cli`
- **Setup:** seed `.taskmaster/config.json` with the real `task-master init` trio:
  `main=anthropic/claude-sonnet-4-20250514`, `research=perplexity/sonar`,
  `fallback=anthropic/claude-3-7-sonnet-20250219`; `ANTHROPIC_API_KEY` and `PERPLEXITY_API_KEY`
  unset; patch `providers.shutil.which` so `claude` and `codex` resolve.
- **Assert:** `result["models"]["main"]["provider"] == "claude-code"` (NOT anthropic);
  `"main" in result["changed"]`; research migrated off paid perplexity to the local proxy or a
  usable provider.
- **Why current coverage fails:** test_dogfood_fixes.py:113/140/157/174/215 only seed EMPTY `{}` or
  user-custom `openai` roles; 0 tests construct the keyless stock trio
  (`grep -rn 'claude-sonnet-4-20250514' tests/` -> 0 hits). `_role_empty` (providers.py:55) skips all
  rewrites on a populated config, so this is the no-op that ships.
- **Red/green:** RED against current providers.py (main stays anthropic); GREEN after the P0-1
  repair (KNOWN_STOCK_TASKMASTER_DEFAULTS + provider-decision-before-tier).
- **Verify:** `python3 -m pytest tests/core/test_dogfood_fixes.py -k corrects_keyless_stock -q`

### T2 — configure-providers with NO usable provider surfaces a critical error (protects C1 / P0-1)
- **Add** `..._configure_providers_no_usable_provider_fails_loudly`
- **Setup:** keyless stock trio; `shutil.which` -> None for claude AND codex; local proxy not
  reachable.
- **Assert:** result signals an unrecoverable setup (e.g. raises CommandError or returns a critical
  flag) rather than silently leaving paid keyless defaults; `changed` does not falsely imply success.
- **Why:** today this exact case returns `changed=['.env:...']` only and leaves a 0-task config that
  the gate then approves (live-reproduced).
- **Verify:** `python3 -m pytest tests/core/test_dogfood_fixes.py -k no_usable_provider -q`

### T3 — validate_setup reports ready=False for a keyless anthropic config (protects C2 / P0-2)
- **Add** `tests/core/test_capabilities.py::TestValidateSetup::test_validate_setup_not_ready_when_anthropic_keyless`
- **Setup:** fake task-master on PATH (so binary/version pass); `.taskmaster/config.json` with the
  REAL shape `main={"provider":"anthropic","modelId":"claude-sonnet-4-20250514",...}`;
  `ANTHROPIC_API_KEY` unset.
- **Assert:** `result["ready"] is False`; `result["critical_failures"] >= 1`; the failing check
  names the missing ANTHROPIC_API_KEY with a fix hint.
- **Why current coverage fails:** `test_validate_setup_passes_with_full_project` (:203) uses a
  fixture with NO `provider` field and asserts ready=True — proven this session to still pass even
  after a correct provider-keyed credential fix (degenerate fixture).
- **Red/green:** RED against current mode_recommend.py (ready=True, live-reproduced);
  GREEN after the P0-2 credential-usability checks land.
- **Verify:** `python3 -m pytest 'tests/core/test_capabilities.py::TestValidateSetup' -q`

### T4 — FIX the existing validate_setup happy-path fixture to use a real, credentialed config (protects C2 / P0-2)
- **Fix** `test_validate_setup_passes_with_full_project` (test_capabilities.py:203):
  add `provider: "claude-code"` to `main` (a CLI provider needing no key) OR set `ANTHROPIC_API_KEY`
  and use `provider: "anthropic"`. The fixture must represent a config that can *actually* produce
  tasks, so ready=True is earned, not asserted on a shape that never occurs.
- **Why:** without this fix, T3 and the P0-2 code change can both be correct while this test stays
  green for the wrong reason — a permanent false-green.
- **Verify:** `python3 -m pytest 'tests/core/test_capabilities.py::TestValidateSetup::test_validate_setup_passes_with_full_project' -q`

### T5 — expand degrades to STRUCTURAL (no --research) on a research-only failure (protects C3 / P0-3)
- **Add** `tests/core/test_tm_parallel.py::test_expand_falls_back_to_structural_when_research_fails`
- **Setup:** extend the fake task-master (test_tm_parallel.py:15) with a new mode, e.g. `research_fail`,
  that exits non-zero **iff** `--research` is in argv and exits 0 (writing 2 subtasks) when `--research`
  is absent. Seed >0 pending tasks.
- **Assert:** the run ultimately succeeds with subtasks > 0; a no-`--research` `expand` was actually
  executed (inspect the logged argv); result surfaces `degraded=True`.
- **Why current coverage fails:** test_tm_run_failure_retries (:184) uses `mode='fail'` which fails on
  ALL expands regardless of `--research`, so it asserts `failed==[1]` and codifies that the retry
  re-runs `--research`. tm_parallel.py:335 hardcodes `--research` with no structural attempt.
- **Red/green:** RED against current tm_parallel.py (structural never attempted -> still fails);
  GREEN after the P0-3 fix adds a no-research retry on rate_limit/quota/auth/no_key.
- **Verify:** `python3 -m pytest tests/core/test_tm_parallel.py -k structural -q`

### T6 — serial expand also degrades to structural on research failure (protects C3 / P0-3)
- **Add** `tests/core/test_backend.py::test_serial_expand_retries_without_research_on_research_failure`
- **Setup:** <=3 pending tasks; fake task-master that fails the `--research` expand and succeeds the
  plain `expand`.
- **Assert:** `result["ok"] is True`; the logged commands include a no-`--research` retry for the
  failed task; `degraded` surfaced.
- **Why:** backend.py:744-746 serial branch appends `--research` and never retries structurally.
- **Verify:** `python3 -m pytest tests/core/test_backend.py -k retries_without_research -q`

### T7 — FIX the anti-regression lock so the P0-3 structural fix is not blocked (protects C3 / P0-3) — CRITICAL
- **Fix** `test_expand_serial_branch_runs_binary_and_appends_telemetry` (test_backend.py:180-204).
  Today it hard-asserts `commands == [[expand,--id,N,--research]...]`. Mutation-proven this session:
  dropping `--research` turns it RED, so it will block the correct fix at review.
- **Change:** assert the *initial* attempt uses `--research` (the happy path) but stop pinning it as
  the *only* command. Replace the exact-list equality with: each task got at least one `--research`
  attempt; allow (do not forbid) a subsequent structural attempt. Or split into a happy-path test
  (research succeeds -> only --research) and let T6 own the failure path.
- **Why:** a passing test that enforces the bug is worse than no test; this is the single most likely
  reason a correct fix gets reverted in review.
- **Verify:** `python3 -m pytest tests/core/test_backend.py -k serial_branch -q` (must still pass on
  the happy path AND not fail when a structural fallback exists)

---

## P1 — land with the P0 cluster

### T8 — the >3-pending parallel path threads research/task_ids through (protects C7 / P2-1)
- **Fix/extend** `test_expand_delegates_to_tm_parallel_for_more_than_three_pending` (test_backend.py:160).
  Call `expand(task_ids=[2], research=False, tag="master")` with >3 pending and **assert
  `called.get("research") is False` and `called.get("task_ids") == [2]`** (after backend.py:727 is
  fixed to pass them).
- **Why:** today it asserts only `called["tag"]`; the test passes while research/task_ids are dropped.
- **Red/green:** RED until backend.py:727 forwards the args and run_tm_parallel accepts them.
- **Verify:** `python3 -m pytest tests/core/test_backend.py -k delegates_to_tm_parallel -q`

### T9 — parse-prd returns ok=False on returncode==0 with zero tasks (protects C4 / P1-1)
- **Add** `tests/core/test_backend.py::test_parse_prd_zero_tasks_is_failure`
- **Setup:** fake task-master `parse-prd` that exits 0 but writes `{tag:{tasks:[]}}` (warn-to-stderr,
  zero tasks — the real model-produced-nothing case).
- **Assert:** `result["ok"] is False`; explanatory `error`; CLI wrapper exits non-zero.
- **Why:** backend.py:719 returns ok=True for any returncode==0; no test seeds 0 tasks.
- **Verify:** `python3 -m pytest tests/core/test_backend.py -k zero_tasks -q`

### T10 — research selection prefers the free proxy over an INVALID paid key (protects C5 / P1-2)
- **Add** `..._configure_providers_prefers_proxy_when_perplexity_key_invalid`
- **Setup:** empty research role; `PERPLEXITY_API_KEY="junk"`; proxy reachable; a stubbed validity
  probe that reports the key invalid.
- **Assert:** `result["models"]["research"]["provider"] == "openai-compatible"` (proxy), not paid
  perplexity.
- **Why:** providers.py:211-216 prefers paid on key *presence*; test_dogfood_fixes.py:140/157 assert
  the presence-only behavior is correct.
- **Verify:** `python3 -m pytest tests/core/test_dogfood_fixes.py -k prefers_proxy -q`

---

## Definition of done for relaunch

Run all new/fixed tests and the full suite:

```
python3 -m pytest tests/core/test_dogfood_fixes.py tests/core/test_capabilities.py \
  tests/core/test_backend.py tests/core/test_tm_parallel.py -q
python3 -m pytest tests/ -q          # full suite must stay green WITH the fixes
```

Acceptance gate: T1-T7 must each demonstrate RED on current `main` and GREEN after the corresponding
P0 fix (T4 and T7 are fixture/lock corrections that must pass *with* the fix and *not* re-pin the bug).
Until then, the contract in `TEST_CONTRACT.md` (C1/C2/C3) is NOT met and the engine can ship 0 tasks
to a keyless first-time user with all tests green — which is the state at HEAD ~d506b93.
