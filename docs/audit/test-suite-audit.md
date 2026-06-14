# Test-Suite Contract Audit — prd-taskmaster (Atlas) engine

Audited HEAD ~d506b93, version 5.2.0, 2026-06-14. Suite executed fresh this session:
`python3 -m pytest tests/ -q` -> **318 passed in ~40s**; `python3 -m pytest tests/core -q`
-> **237 passed in ~17s**. Zero skips. All green.

This audit answers one question: **how did a 318-test green suite ship a first-run config that
produces 0 tasks?** It corroborates the existing `defect-register.json` (P0-1/P0-2/P0-3 etc.) and
adds the missing piece those defects don't fully state: the tests don't merely *fail to cover* the
bug — several of them **encode the broken behavior as the expected behavior**.

---

## UNCOMFORTABLE FINDINGS FIRST

### F1 (P0-3) — A passing test ACTIVELY LOCKS the bug in place (worst case)

`tests/core/test_backend.py:180-204` `test_expand_serial_branch_runs_binary_and_appends_telemetry`
asserts the exact command list:

```python
assert commands == [
    ["expand", "--id", "1", "--research"],
    ["expand", "--id", "2", "--research"],
    ["expand", "--id", "3", "--research"],
]
```

P0-3's fix is to retry `expand` *without* `--research` when research is unavailable. **Red/green
proof, executed this session:** I mutated `backend.py:744-746` to drop the `--research` append
(simulating the structural-fallback fix) and ran just this test — it went **RED**:

```
At index 0 diff: ['expand', '--id', '1'] != ['expand', '--id', '1', '--research']
FAILED tests/core/test_backend.py::test_expand_serial_branch_runs_binary_and_appends_telemetry
```

backend.py was then fully reverted (`git diff --stat prd_taskmaster/backend.py` clean). This is the
worst category of test: not absent coverage, but coverage that will make a correct fix fail review.

### F2 (P0-3) — The "failure retry" test can't tell research-failure from any failure

`tests/core/test_tm_parallel.py:184-205` `test_tm_run_failure_retries_with_escalated_config_and_telemetry`
looks like it tests resilience. It doesn't. The fake task-master (`tests/core/test_tm_parallel.py:15-66`)
has modes `ok | slow | fail`; `fail` (:30-33) returns exit 1 on **any** `expand`, regardless of whether
`--research` is present. So the test proves only that a failed expand is retried with an escalated
*tier* — and asserts `attempts == 2` and `failed == [1]`, i.e. it **codifies that the retry re-runs
`--research` and still fails**. There is no fake mode that fails *iff* `--research` is present, so a
structural fallback is impossible to express, let alone require. `tm_parallel.py:335` hardcodes
`[binary, "expand", "--id", N, "--research", "--force"]` and the retry at `_run_packet:359-409` only
calls `shift_tier` + reruns the same `--research` command (`_run_one_attempt:331-347`).

### F3 (P0-2) — The SETUP gate's "ready" test certifies a config that never occurs and can't fail

`tests/core/test_capabilities.py:203-230` `test_validate_setup_passes_with_full_project` seeds:

```python
config = {"models": {"main": {"modelId": "claude-sonnet-4-5"}, ...}}   # NO provider, NO credential
```

and asserts `ready=True, critical_failures=0`. Two problems:
1. **It asserts the bug is correct.** `mode_recommend.py:459` `provider_ok = bool(main_model)` checks
   only that a model-id *string* is present. **Live repro this session:** `validate_setup()` against
   the real keyless stock config (`main=anthropic/claude-sonnet-4-20250514`, `ANTHROPIC_API_KEY`
   unset) returns `ready=True, critical_failures=0`. The gate (`pipeline.py` SETUP->DISCOVER) approves
   the exact 0-task config.
2. **The fixture is degenerate.** Its `main` dict has *no* `provider` key, whereas every real
   `task-master init` config has `provider: "anthropic"`. **Mutation proof:** I applied the natural
   P0-2 fix (`provider_ok = bool(main_model) and (provider != 'anthropic' or ANTHROPIC_API_KEY set)`)
   and this test still **passed** — because the fixture's empty-provider config never trips the
   anthropic branch. So even a *correct* credential check is invisible to this test. mode_recommend.py
   reverted clean.

### F4 (P0-1 / P2-6) — Assertion bias: tests only assert "leave it alone", never "correct it"

The configure-providers tests in `tests/core/test_dogfood_fixes.py` exhaustively cover the
do-nothing directions and never the repair direction:

- `:113` `..._rewrites_engine_default_main_to_fast_tier` seeds `claude-code/sonnet` — a provider that
  is **already usable** — and only checks a *tier* rewrite (sonnet->haiku). Provider migration is never
  tested because the seed never needs migrating.
- `:140` / `:157` seed an **EMPTY** research role (`_seed_taskmaster_config(tmp_path, {})`) and assert
  paid sonar/sonar-pro is chosen — exercising the `_role_empty==True` branch that the real bug never
  reaches.
- `:174` `..._user_configured_main_is_not_touched` seeds `provider: "openai"` (a non-engine-default)
  and asserts it is **NOT** touched. This is the leave-it-alone assertion — against a *customized*
  baseline, never against a *keyless stock* baseline.
- `:215` `..._free_proxy_first_preserves_local_proxy_golden` again seeds **EMPTY** `{}`.

**Live repro this session:** stock keyless trio + `shutil.which` patched to None ->
`configure-providers(balanced)` returns `changed=['.env:OPENAI_COMPATIBLE_API_KEY',
'.env:PERPLEXITY_API_BASE_URL']` and leaves `main=anthropic/claude-sonnet-4-20250514`
**unchanged** (`after['main'] == stock['main']` -> True). The no-op is exactly what the tests'
absence-of-a-correction-test permits. Root cause in code: `_role_empty` (`providers.py:55`) returns
`False` for any non-empty dict, so the writes at `:176/:190/:207` are all skipped on a pre-populated
config. **Grep proof:** `grep -rn 'claude-sonnet-4-20250514\|claude-3-7-sonnet' tests/` -> **0 hits**;
no test ever constructs the trio that ships.

### F5 (P2-1) — The delegation test passes whether or not research/task_ids are dropped

`tests/core/test_backend.py:160-178` `test_expand_delegates_to_tm_parallel_for_more_than_three_pending`
patches `run_tm_parallel(**kwargs)` to capture kwargs, then asserts only `called["tag"] == "master"`.
`backend.py:727` calls `tm_parallel.run_tm_parallel(tag=tag)` — silently dropping the `research` and
`task_ids` arguments the public `expand(task_ids, research, tag)` accepts. The test never asserts those
were threaded through, so it remains green with the drop in place. A fresh viral PRD usually yields >3
tasks, so first run takes this parallel path and loses the `--no-research` escape hatch precisely when
P0-3 bites.

### F6 (P1-1) — parse-prd zero-task success is untested

`backend.py:718-722` returns `{ok:True, task_count:len(tasks)}` on `returncode==0` with no `len>0`
guard. `tests/core/test_backend.py:144` only tests `count=5`; `:245` only tests `returncode=1`. There
is no test where the CLI exits 0 but wrote zero tasks (the real warn-to-stderr-exit-0 behavior), so
`ok=True, task_count=0` is unproven and uncaught.

---

## Why these are mock/can't-fail tests, by category

- **Anti-regression lock:** test_backend.py:180 (F1) — pins the buggy command; blocks the fix.
- **Indistinguishable-failure mock:** test_tm_parallel.py:184 (F2) — fake fails on all expands, so
  research-specific degradation cannot be expressed.
- **Degenerate-fixture / can't-fail-for-the-real-shape:** test_capabilities.py:203 (F3) — fixture omits
  the `provider` field, so a provider-keyed fix is invisible; the assertion is tautological w.r.t. the
  bug.
- **Assertion against the wrong baseline:** test_dogfood_fixes.py:113/140/157/174/215 (F4) — empty or
  user-custom seeds only; the keyless-stock seed that breaks is never constructed.
- **Captured-but-unasserted kwargs:** test_backend.py:160 (F5) — captures **kwargs, asserts one key.
- **Untested success-with-zero:** test_backend.py:144 (F6).
- **Right contract, wrong code path:** test_native_backend.py:204/298 — genuinely tests the NATIVE
  backend's invalid_json escalation and no-key agent path, but the SHIPPED first-run path is the
  TaskMaster-CLI backend (tm_parallel), which has no parallel coverage. The native coverage gives
  false comfort.

No `.skip`/`.todo`/`xit` were found in the four focus files. The disabling here is subtler than skips:
it is *covering the wrong shape*.

---

## HOW the green suite shipped the broken behavior (the mechanism)

1. **Two contracts were conflated.** "Config is well-formed" (a string is present, a dict has the
   right keys) was tested; "config can actually produce tasks" (the credential/CLI/proxy works) was
   not. validate_setup, configure-providers, and expand were all tested at the *shape* level.
2. **The fixtures pre-decided the answer.** configure tests seed only EMPTY or USER-CUSTOM roles —
   never the keyless paid trio that `task-master init` actually writes — so the no-op branch
   (`_role_empty==False`) was never under test. validate_setup's fixture omits `provider` so it can't
   trip a credential check.
3. **One test pinned the bug as a feature.** The serial-expand command-list assertion makes
   `--research` mandatory; the parallel-failure fake can't distinguish research failure from any
   failure. So even an engineer writing the fix would see a test go red and assume *they* broke
   something.
4. **Coverage of an adjacent path masqueraded as coverage of the shipped path.** The Native backend's
   no-key/invalid-json handling is well tested; the TaskMaster-CLI parallel path that strangers
   actually hit is not. "expand is tested" was true for the wrong expand.

Net: 318 green tests, each individually defensible, collectively certifying a product that returns 0
tasks to a keyless first-time user.

---

## STRENGTHS (real coverage that does work)

- `tests/core/test_model_routing.py` (9 tests) — genuine return-value assertions on `route_task`;
  would fail on a routing regression. (Strong, but unrelated to the first-run bug.)
- `tests/core/test_native_backend.py:183` `test_parse_prd_invalid_candidate_returns_error_without_overwrite`
  — asserts ok=False AND that the prior tasks.json is byte-for-byte preserved; a real
  negative-path + no-clobber assertion.
- `tests/core/test_ship_check.py` (8 tests) — per prior audit, real subprocess tests asserting exact
  stdout/returncode (the unfakable-gate claim).
- `tests/core/test_tm_parallel.py` correctly tests dependency-stripping, isolation, version-gate,
  timeout-retain, and workdir cleanup — the parallelism *mechanics* are well covered. The gap is
  purely the research-degradation semantics.

---

## METHODOLOGY & WHAT WAS NOT AUDITED

- Scope: the P0/P1 first-run claims and the four named test files (test_dogfood_fixes,
  test_native_backend, test_taskmaster_wrapper, test_model_routing), plus the source they guard
  (providers.py, mode_recommend.py, tm_parallel.py, backend.py) and the directly adjacent
  test_backend.py / test_capabilities.py.
- Executed: full suite (318) and core (237); two live repros of the shipped code against the exact
  broken config; two non-destructive red/green mutations (backend.py F1 -> RED then reverted;
  mode_recommend.py F3 -> still GREEN, demonstrating fixture degeneracy, then reverted). Working tree
  confirmed clean of source mutations (`git diff --stat` empty; only pre-existing untracked AUDIT.md
  and defect-register.json remain).
- NOT audited fresh: tests/mcp (MCP tool integration), tests/plugin (hooks), tests/integration; the
  install.sh / npm postinstall path; the local Perplexity proxy envelope mismatch (P2-4) end-to-end.
  These are covered in the existing defect-register but not re-executed here.

## RESIDUAL RISK

- **P0-1, P0-2, P0-3 remain unproven by the suite** and P0-3 is anti-regression-locked. The product
  can ship 0 tasks on a keyless first run with all 318 tests green — this is reproduced, not
  hypothesized.
- A correct P0-2 fix may pass the existing validate_setup test for the wrong reason (degenerate
  fixture) — fixing the code without fixing the fixture leaves a false-green.
- A correct P0-3 fix will FAIL test_backend.py:180 until that test is rewritten; reviewers must not
  "restore" the `--research` assertion.
- The Native vs TaskMaster-CLI backend split means passing native tests do not bound CLI-path
  behavior; the shipped path's research-degradation is untested in either direction.
- Anything in tests/mcp, tests/plugin, tests/integration is taken on its prior-audit word, not
  re-executed here.
