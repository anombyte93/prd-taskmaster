# TEST_CONTRACT.md — prd-taskmaster (Atlas) engine

Behavioral contract the test suite is responsible for proving. Audited at HEAD ~d506b93
(version 5.2.0) on 2026-06-14. Suite executed: `python3 -m pytest tests/ -q` -> **318 passed**;
`python3 -m pytest tests/core -q` -> **237 passed** (the remaining ~81 live under tests/mcp,
tests/plugin, tests/integration). The suite is fully green while the documented first-run
zero-config path ships broken.

Evidence strength legend: `none` (no executable check) | `weak` (test exists but would still
pass if the behavior broke) | `partial` (real behavior asserted, key paths uncovered) |
`strong` (asserts observable behavior, fails when the claim is false, executed fresh in this audit).

| # | Claim the engine makes | Verification command | Evidence |
|---|---|---|---|
| C1 | configure-providers corrects a keyless/paid stock default to an available CLI or the free proxy so first run yields tasks | `python3 -m pytest tests/core/test_dogfood_fixes.py -q` + keyless-stock repro | **none** |
| C2 | validate_setup reports ready=True only when the provider can actually produce tasks (credential usable) | `python3 -m pytest 'tests/core/test_capabilities.py::TestValidateSetup' -q` | **weak** |
| C3 | expand degrades to structural (no --research) on research quota/auth failure ("always available") | `python3 -m pytest tests/core/test_tm_parallel.py tests/core/test_backend.py -q` | **weak** (anti-regression lock present) |
| C4 | parse-prd returns ok=false when zero tasks were produced | `python3 -m pytest tests/core/test_backend.py -q -k parse_prd` | **partial** |
| C5 | research selection validates the Perplexity key before preferring paid over the free proxy | `python3 -m pytest tests/core/test_dogfood_fixes.py -q -k research` | **weak** |
| C6 | a credential validity/health probe runs before writing config / before parse | `grep -rn 'health\|probe\|200' tests/core/` | **none** |
| C7 | the parallel expand path (>3 pending) honors research choice and task ids | `python3 -m pytest tests/core/test_backend.py::test_expand_delegates_to_tm_parallel_for_more_than_three_pending -q` | **weak** |
| C8 | the suite covers correction of a keyless stock default (not just leave-config-alone) | `grep -rn 'claude-sonnet-4-20250514\|claude-3-7-sonnet' tests/` (0 hits) | **none** |
| C9 | route_task picks per-task models from complexity and falls back on missing backend | `python3 -m pytest tests/core/test_model_routing.py -q` | **strong** (but NOT a first-run-path claim) |
| C10 | NativeBackend no-key path returns agent_action_required | `python3 -m pytest tests/core/test_native_backend.py -q` | **partial** (wrong backend vs. the shipped path) |

## The one-line summary of why a green suite shipped a broken product

The suite asserts **"do not touch user config"** against **EMPTY** roles (`{}`) and **user-CUSTOM**
providers (`provider: "openai"`), and asserts **"setup is ready"** against **model-id strings with
no provider field**. It never once asserts **"CORRECT a keyless stock default"** or **"a string
present is not the same as a credential that works."** The bug lives precisely in the gap between
"config is shaped right" (tested) and "config can actually produce tasks" (never tested).

## Contract status: NOT MET for relaunch

C1, C2, C3 are the three P0 claims behind the guaranteed-broken first run. None is currently
proven; C3 is actively LOCKED in its broken state by a passing test. These must reach `strong`
before the viral relaunch. See `recommended-test-tasks.md`.
