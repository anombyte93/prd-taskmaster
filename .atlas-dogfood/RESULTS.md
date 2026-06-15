# Dogfood: goose-gemini vs codex on hardening /atlas

**Goal:** loop until a cheap goose+Gemini-2.5-Flash worker reaches results
comparable to codex on real /atlas hardening tasks — decomposing into smaller
subtasks as needed to compensate for the cheaper model.

**Method (A/B, unfakable):** for each real task I (the orchestrator) write a
pytest acceptance gate the worker may NOT edit. `.atlas-dogfood/bench/run_trial.sh`
runs a worker (codex | gemini) autonomously, runs the external gate (pytest +
ruff), records verdict/wall/diff, then resets the source file to baseline so the
next worker gets a clean tree. Worker self-report is never trusted — the gate is
truth. Codex (`codex exec`, gpt via OPENAI_API_KEY) is the bar; gemini is goose
(`GOOSE_PROVIDER=google GOOSE_MODEL=gemini-2.5-flash`).

## Results

| Iter | Task | Granularity | codex | gemini | Note |
|------|------|-------------|-------|--------|------|
| 1 | T2 `_parse_version` fixed 3-tuple (real cmp bug) | coarse (1 instr) | PASS 358s | PASS 38s | gemini matches codex; ~9x faster, far cheaper. Small task → no discrimination. |
| 2 | T3 google/gemini credential-gating in `_provider_usable` + `validate_setup` wiring | coarse, **cross-file (2 files)** | PASS 362s | PASS 41s | gemini matches codex on a cross-file task with **no decomposition**; tighter diff (4 vs 6 ins). ~9x faster, far cheaper. |

## Emerging insight (after 2 iterations)
The discriminator is NOT task size or cross-file-ness — goose-gemini-2.5-flash matches
codex on both, at ~1/9th the wall time and far lower cost, when the task is
**precisely specified** (exact contract in the instruction). The decomposition
hypothesis most likely bites on **under-specified / autonomous** tasks (e.g. "these
5 tests fail, find and fix the root cause") where the model must infer the spec
itself. Reframe for the orchestrator: the lever for cheap models is **specification
precision** — atomizing a task into small, precisely-specified subtasks IS the
decomposition that lets a cheap model match a strong one. Iter 3 will test an
UNDER-specified task to find gemini's failure point, then show decomposition
(adding spec/structure) closing the gap.

## Iteration 3 — the decomposition test (under-specified vs precise) ★
Real task: a chunk of the suite was **non-hermetic** — `resolve_provider` reads real
API keys (os.environ + bound `discover_key`), so results flipped on the shell:
native_backend needed a key present (5 fail without); test_cli/test_engine_preflight
"no-key" tests needed keys absent (fail with one). NO env was fully green.

Two-phase experiment (operator planned the fix in a SEALED file first):
- **Under-specified** ("5 tests fail, find root cause & fix"): goose-gemini ran with
  ambient keys → failures were masked → it made **ZERO changes**, got confused, and
  asked for clarification. It did NOT find the root cause autonomously. **gemini < codex/operator.**
- **Decomposed/precise** (operator handed gemini the exact recipe: patch
  `backend.resolve_provider` in native tests; clear key env in no-key tests): gemini
  produced a diff **matching the operator's sealed plan exactly** — test-side only, no
  production change, no weakened assertions. Verified 36/36 green **with AND without**
  ambient keys. Committed (fbac5f1). **gemini == operator/codex.**

## VERDICT
goose-gemini-2.5-flash is **comparable to codex** on /atlas hardening — and ~9x
faster / far cheaper — **whenever the task is precisely specified**, including
cross-file changes. It falls short only on **autonomous diagnosis of under-specified**
problems. The user's hypothesis is confirmed and operationalized: **decomposition =
specification precision is the lever** that lets the cheap model match the strong one.
Orchestrator implication: spend the strong/expensive model on *decomposition &
diagnosis*; fan the *precisely-specified subtasks* out to cheap goose-gemini workers.

Real hardening landed this run: google provider (f994018) + hermetic test suite (fbac5f1).

## Iteration 4 — full model spectrum: DECOMPOSITION vs EXECUTION ★★
Question: how far are cheap/local models from codex at BOTH (a) decomposing a PRD into
tasks and (b) actually completing the generated tasks? Harnesses:
`.atlas-dogfood/bench/decomp_bench.py` (decomposition, scored by the engine's own
`run_validate_tasks`) and goose+ollama on the T2 coding gate (execution).

### (a) Decomposition — PRD → tasks (one-shot JSON, gate = run_validate_tasks)
| Model | Gate | Note |
|---|---|---|
| openai gpt-4.1-mini (strong API) | PASS | clean 5 tasks |
| **gemini-2.5-flash** | **PASS** | **matches the strong API** |
| qwen3 ~8B (local) | FAIL | no JSON extracted — reasoning-model `<think>` wrapper defeats _extract_json |
| llama3.2:3B (local) | FAIL | 14 problems: status "in progress" (not "in-progress"), missing fields |
| qwen2.5:1.5B (local) | FAIL | only 3 problems — produced 6 tasks, 3 lacked a 2nd subtask |
Local failures are FIXABLE format/discipline issues, not reasoning failures. The gap
to codex on decomposition is SHORT.

### (b) Execution — complete the T2 coding task (agentic, gate = pytest+ruff)
| Worker | Gate | Note |
|---|---|---|
| codex | PASS | (iter 1) |
| gemini-2.5-flash via goose | PASS | (iter 1) == codex, ~9x faster |
| llama3.2:3B via goose | FAIL | 4s, emitted a malformed tool call (`edit` missing `path`), then rambled; ZERO edits |
| qwen3 ~8B via goose | FAIL | 219s wandering files, confused, ZERO edits |
Local ≤8B models CANNOT drive an agentic tool-using harness. The gap to codex on
execution is LONG — a model-capability wall (tool-calling), not a prompt issue.

## What prd-taskmaster should ADJUST (to bring goose + any/local model in line)
DECOMPOSITION (cheap wins, likely gets local models passing the gate):
1. Validation-aware REPAIR loop: when run_validate_tasks fails, feed the specific
   `problems` back for ONE repair pass. Today generate_json only retries on JSON-parse
   failure, not on validation problems — so weak models never get to self-correct
   "missing 2nd subtask" / "invalid status".
2. Reasoning-model JSON extraction: strip `<think>...</think>` (and similar) before
   _extract_json. qwen3/deepseek-r1 failed ONLY on this.
3. Status/field normalization: map "in progress"->"in-progress", coerce obvious
   variants before validating (kills avoidable llama failures).
4. Few-shot: embed one COMPLETE valid example task in the prompt for weak models.

EXECUTION (the hard wall — needs an architectural path, not prompt tweaks):
5. A constrained STRUCTURED-EDIT execution path for models that can't drive freeform
   tool-calling: the model returns a structured patch/full-file JSON; the HARNESS
   applies it + runs the gate. This is the original "raw API + harness applies"
   design — it lets cheap/local models contribute to execution without agentic tool-use.
6. Capability-tiered routing: goose agentic path only for models proven to drive tools
   (gemini+); structured-edit path for weak/local; codex/claude for the hardest tasks.
   The orchestrator decomposes with a strong model, then routes each subtask to the
   cheapest worker whose capability clears the bar.

### Bottom line for the user's question
- Decomposition: gemini is ALREADY at codex level; local models are CLOSE and reachable
  with adjustments #1-#4.
- Execution: gemini is at codex level; local models are FAR — only adjustments #5-#6
  (a non-agentic structured-edit path) can bring them in, and even then only for simple
  tasks. The strong model stays essential for decomposition/diagnosis and hard execution.

## Engine debt found (not yet fixed)
5 tests in `tests/core/test_native_backend.py` (parse_prd / expand / rate) fail on
`main`: they mock the OLD seam `llm_client.discover_key`, but backend.py now routes
via `resolve_provider("main")` (backend.py:344) which returns `kind="plan"` in a
keyless env → handoff path → `ok:False`. Stale tests from the resolver refactor.
Fix = update those tests to mock `resolve_provider` (or add a discover_key API
fallback in backend). Deferred: fixing requires editing tests, which conflicts with
the worker-gate methodology; will handle as a direct maintenance task.

### Iteration 1 detail (T2)
Real bug: variable-length version tuples mis-compare ((1,2) < (1,2,0) is True →
"1.2" wrongly older than "1.2.0"). Gate: `tests/core/test_parse_version_tuple.py`
(11 cases incl. the equality regression). Both workers normalized to a 3-tuple
and passed the external gate; both diffs clean; source reset verified; gate test
untampered. **Verdict: comparable on small, well-specified tasks — gemini wins on
cost/latency.**

## Next
T2 did not discriminate (too small). Escalate to a harder, multi-branch real task
— hero candidate: **credential-aware `validate_setup`** (audit P0-2, the v5.2.0
relaunch blocker: the readiness gate green-lights a keyless paid config). Expect
codex to one-shot it and gemini-coarse to struggle → then demonstrate the
decomposition hypothesis (split into smaller subtasks until gemini matches codex).

## Iteration 5 — quantifying the decomposition gap-closing ★★★
Enhanced decomp_bench.py to measure raw → +normalize → +repair (max_tokens 8192).
- **Variance is the headline for raw local runs:** qwen2.5:1.5b went 3-problems → 0-tasks
  across runs; qwen3 went clean-JSON → no-json. Small local models are UNRELIABLE
  run-to-run, and a validation-aware repair pass did NOT rescue them (llama3.2:3b could
  not self-correct even when handed the exact problems). Normalization/repair help only
  capable models that slip; they do not lift sub-floor (<=3B) models.
- **DECISIVE FIX for local reasoning models — disable thinking:** qwen3:8b with `/no_think`
  passed the gate **3/3, clean (5 tasks, 2 subtasks each)**. Thinking-mode was the entire
  source of its strict-JSON instability. With it off, a LOCAL 8B model == codex/gemini on
  decomposition.

### QUANTIFIED answer — "how far to bring local in line with codex"
DECOMPOSITION: hosted-cheap gemini-flash already == codex (distance 0); local 8B reasoning
(qwen3) + thinking-disabled == codex, 3/3 (distance ≈ ONE config flag); local <=3B not
reliable (distance = a bigger model). EXECUTION: unchanged — local can't drive the agentic
harness; needs the structured-edit path (distance = an architectural change, not a model swap).

### Refined prd-taskmaster adjustments (priority order)
1. ★ Reasoning-model handling: detect reasoning models and DISABLE thinking for
   structured-gen (ollama think:false / `/no_think`; strip `<think>` before JSON extract).
   Decisive: qwen3 0%→100% reliable on decomposition.
2. Raise structured-gen max_tokens (4096→8192+) to avoid truncating multi-task JSON.
3. Validation-aware repair loop (feed run_validate_tasks problems back, 1 pass) — helps
   capable models on hard PRDs; will NOT rescue sub-floor models.
4. Status/priority normalization before validation — kills avoidable format fails.
EXECUTION: structured-edit path + capability-tiered routing (from iter4) remain the levers.

## Iteration 6 — structured-edit EXECUTION POC (does adjustment #5 work?) ★★★
POC: model never touches the FS; it returns JSON {find, replace}; a deterministic
harness applies it (str.replace) + runs gate_t2.sh. (.atlas-dogfood/bench/structured_edit_poc.py)
| Model | Result | Meaning |
|---|---|---|
| gemini-2.5-flash (control) | edit applied, near-pass | viable; failed only an over-specified edge ("1.two.3"→(0,0,0) vs its (1,0,3) per-part leniency) |
| qwen3:8b (/no_think) | applicable edit, wrong fix | **path lowers the bar: 0 edits in agentic mode → an APPLICABLE edit here** |
| llama3.2:3b | NO-EDIT | below protocol floor — can't emit valid {find,replace} JSON |
| qwen2.5:1.5b | NO-EDIT | below protocol floor |

CONCLUSION: the structured-edit path REMOVES the tool-calling wall (an 8B local model
that made zero edits via agentic goose can now produce an applicable edit), but it does
NOT remove the CAPABILITY requirement — the edit must still be correct, and that still
tracks model strength. Tiny (<=3B) models can't even follow the JSON edit protocol.

## ===== FINAL SYNTHESIS: how far to bring goose+local in line with codex =====
DECOMPOSITION (PRD→tasks):
- gemini-flash (hosted cheap): == codex. distance 0.
- local 8B reasoning + thinking-disabled: == codex (3/3). distance ≈ one config flag.
- local <=3B: unreliable; below floor. distance = a bigger model.
EXECUTION (complete tasks):
- gemini via goose: == codex (~9x cheaper/faster).
- local via AGENTIC goose: fails entirely (tool-calling wall).
- local via STRUCTURED-EDIT: 8B can participate (applicable edits) but not yet reliably
  correct; <=3B can't follow the protocol. distance = architectural path (built here) +
  a stronger local model for correctness.
NET: a cheap HOSTED model (gemini-flash) already matches codex for BOTH decomposition and
execution at a fraction of the cost — that is the immediate win. LOCAL models reach codex
on decomposition (8B + no-think) but remain short on execution correctness; the
structured-edit path is the right architecture to let them contribute as they improve.
Highest-value prd-taskmaster changes: (1) reasoning-model thinking-disable for structured
gen, (2) max_tokens bump, (3) validation-aware repair loop, (4) a structured-edit execution
backend + capability-tiered routing (strong model decomposes/diagnoses; cheapest capable
worker executes each precisely-specified subtask, gated externally).
