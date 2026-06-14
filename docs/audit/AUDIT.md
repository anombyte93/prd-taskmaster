# AUDIT.md — prd-taskmaster (Atlas) Engine, pre-relaunch 5.2.0

**Auditor:** lead synthesis pass over 29 verified findings (refuted ones removed)
**Repo audited:** `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public` @ HEAD `d506b93` (version **5.2.0**, published to npm)
**Live dogfood consumer:** `/home/anombyte/Hermes/current-projects/shade-browser-mcp`
**Context:** viral relaunch, 509 GitHub stars. A broken first run torches the goodwill.

---

## 1. Executive summary

**HOLD the relaunch.** The engine's headline promise — *"zero setup, no paid API key, uses the model CLIs you already have"* — is **broken on the documented first-run path**, and the gate built to prevent exactly this **green-lights the broken state**.

The root cause is a single causal chain, raised independently by multiple finders across the provider-config, skills, and dogfood-replay dimensions, and reproduced firsthand at HEAD `d506b93`:

1. `task-master init` pre-populates all three model roles with **paid defaults** (`main=anthropic/claude-sonnet-4`, `research=perplexity/sonar`, `fallback=anthropic/claude-3-7-sonnet`).
2. `configure-providers` is a **no-op** on populated roles — it only fills *empty* roles, so it never migrates a keyless `anthropic` role to the available `claude`/`codex` CLI, nor paid Perplexity to the free local proxy. The setup SKILL even instructs **SKIP** when roles are "populated with a supported provider."
3. The **SETUP gate** reports `ready=True` because it checks only that a non-empty model-id *string* is present — never that the provider has a usable credential.

Net effect: a brand-new user with `ANTHROPIC_API_KEY` unset follows the recommended path, the SETUP gate passes, and their first `parse-prd`/`expand` **silently produces 0 tasks**, then falls back to a degraded "Atlas Native Mode." A compounding 4th P0-class defect: when the research provider is **out of quota** (the actual dogfood condition), `expand` **hard-fails to 0 subtasks** and never degrades to the documented "always available" structural expand.

A **237/318 all-green test suite shipped this** because it only covers the empty-role happy path. None of the three regression tests that would have caught the bug exist.

**Verdict gate:** 3 P0s survive → **HOLD**. Ship only after the three P0 fixes plus three named regression tests are green.

---

## 2. Verdict

| | |
|---|---|
| **Decision** | **HOLD** |
| **P0 (relaunch blockers)** | **3** (deduplicated) |
| **P1 (major)** | **8** |
| **P2 (moderate)** | **6** |
| **P3 (minor/polish)** | **4** |
| **Rule** | HOLD because ≥1 P0 survives |
| **Path to SHIP** | Land the 3 P0 fixes + 3 regression tests (Section 5), re-run full suite green, re-run the dogfood replay to `task_count>0` end-to-end |

---

## 3. Prioritized defect register

> **De-duplication note.** The "configure no-op" root cause was raised by **five** finders across four dimensions (`configure-noop-on-populated-roles`, `configure-providers-noop-on-populated-paid-roles`, `configure-noop-on-stock-paid-defaults`, `setup-skill-skips-stock-paid-defaults`, `empty-role-configure-picks-native-correctly`). They are merged into **P0-1** with the others cited as corroboration. Likewise the "research prefers paid Perplexity on key presence" finding was raised three times (`research-real-api-if-key-...`, `research-prefers-paid-perplexity-on-key-presence-not-validity`, `research-prefers-paid-perplexity-on-key-presence`) and is merged into **P1-2**.

### P0 — relaunch blockers (first run breaks)

#### P0-1 · `configure-providers` is a no-op on TaskMaster's stock paid defaults → first run produces 0 tasks
*(merges: configure-noop-on-populated-roles, configure-providers-noop-on-populated-paid-roles, configure-noop-on-stock-paid-defaults, setup-skill-skips-stock-paid-defaults, empty-role-configure-picks-native-correctly)*

**Evidence (reproduced firsthand at HEAD d506b93):**
- `prd_taskmaster/providers.py:55` `_role_empty()` returns `False` for any non-empty dict. Every model-role write is gated on it: `:176` (main), `:190` (fallback), `:207` (research). The only populated-main branch (`:180-187`) only re-tiers a `modelId` when start_tier≠standard AND the role is already a `KNOWN_ENGINE_DEFAULTS` value — it never changes `provider`, and under the default `balanced`/`standard` economy it never fires.
- Live repro in `/tmp/audit_final` with stock paid config, `ANTHROPIC_API_KEY`+`PERPLEXITY_API_KEY` unset, **`claude` AND `codex` both on PATH**, proxy up:
  ```
  changed: ['.env:OPENAI_COMPATIBLE_API_KEY', '.env:PERPLEXITY_API_BASE_URL']
  main:     {'provider': 'anthropic', 'modelId': 'claude-sonnet-4-20250514'}   # UNCHANGED
  research: {'provider': 'perplexity', 'modelId': 'sonar'}                     # UNCHANGED
  fallback: {'provider': 'anthropic', 'modelId': 'claude-3-7-sonnet-...'}      # UNCHANGED
  ```
  Zero model roles corrected despite no usable key and an available native CLI + free proxy.
- End-to-end (separate finder): `init-taskmaster` → `configure-providers` → `parse-prd` in this env returns `{"ok": false, "task_count": 0}`, stderr `"Perplexity API error … Invalid API key"` and `Required API key ANTHROPIC_API_KEY … not set`; **tasks.json never created**.
- The setup SKILL is wired to make this worse: `skills/setup/SKILL.md:126` table row `| Main / Research / Fallback all populated with a supported provider | SKIP — go to Step 4. |`, and `grep configure-providers skills/setup/SKILL.md` → **no matches** (the skill never even calls the repair command).
- **Smoking gun:** emptying the three roles to `{}` first makes the identical configure run correctly pick `main→claude-code`, `fallback→codex-cli`. The *only* difference between broken and correct is whether roles were empty.

**Contradicts:** `cli.py:178` help "Configure native TaskMaster providers and local Perplexity API Free"; `README.md:50` "configures it. Zero setup questions"; `README.md:89` "The free engine needs no paid API key — it uses the model CLIs you already have."

**Fix:** Make configure **REPAIR, not just fill**. Define a "TaskMaster stock default" set (the exact init dicts) and treat those roles like empty ones — eligible for repopulation. Overwrite any role whose provider is unusable in the current env (`provider==anthropic` with `ANTHROPIC_API_KEY` unset; `provider==perplexity` with no/invalid key when the free proxy is up). Resolve the desired *usable* provider first, then apply tier on top of it (folds in P1-4). Preserve only genuinely user-customized non-default providers (openrouter, ollama, a key-bearing provider). Then change `skills/setup/SKILL.md` Step 3 to ALWAYS run `configure-providers` and reword the DETECT-FIRST table so "populated with an *unreachable* provider" is a CORRECT-not-skip case. **Verified:** a config with `main=claude-code` (+`fallback=codex-cli`) makes parse-prd return `ok:true/task_count>0` in the identical broken env.

---

#### P0-2 · SETUP gate `validate_setup` reports `ready=True` for the exact 0-task config — checks model-id string presence, never credential usability

**Evidence (reproduced firsthand):**
- `prd_taskmaster/mode_recommend.py:459` `provider_ok = bool(main_model)` — check 5 (provider_main) passes on any non-empty modelId string; `:480` (provider_research) is likewise `bool(research_model)`. A grep of the module for `API_KEY|getenv|os.environ|credential|reachable` inside the validation logic returns **zero** hits.
- Live repro against the stock paid config with `ANTHROPIC_API_KEY` unset: `validate_setup()` → `ready: True critical_failures: 0`.
- `prd_taskmaster/pipeline.py:90-93` gates the SETUP transition on `validate_setup.ready` AND `critical_failures==0`, so the gate built to prevent the 0-task failure **approves the precise config that produces it**.

**Contradicts:** `skills/setup/SKILL.md:36` and `:195` ("Gate first, always") — the gate is presented as the guarantee that providers are configured.

**Fix:** Add a credential-usability dimension to provider_main / provider_research / provider_fallback: if `provider==anthropic` require `ANTHROPIC_API_KEY` (else FAIL critical with fix "set ANTHROPIC_API_KEY or run configure-providers to switch to claude-code"); if `provider in {claude-code,codex-cli}` require the CLI on PATH; if `provider==perplexity` require a key (warn + suggest the free proxy if `127.0.0.1:8765` is reachable). The gate must verify the configured provider is reachable, not merely that a string is present.

---

#### P0-3 · `expand` hard-fails to 0 subtasks when the research provider is out of quota — never degrades to structural expand (THE dogfood failure)

**Evidence (reproduced firsthand):**
- `prd_taskmaster/tm_parallel.py:335` hardcodes the argv `[binary, "expand", "--id", str(task_id), "--research", "--force"]`. The retry in `_run_packet` (`:359-409`) only escalates tier via `shift_tier` — it re-runs the SAME `--research` command; **no structural (no-`--research`) attempt exists anywhere.**
- `prd_taskmaster/backend.py:724` routes >3 pending tasks to this parallel path (the dogfood case has 5 tasks). The serial ≤3 path (`backend.py:742-771`) also has no structural retry.
- `NativeBackend._expand_packet` (`backend.py:502-510`) is the same shape: only `kind=='invalid_json'` escalates; `rate_limit/quota/auth` LLMError hard-fails immediately.
- Live repro with a fake `task-master` that fails iff `--research` is present: `ok=False`, `failed=[1,2,3,4,5]`, subtask counts `[0,0,0,0,0]`; the structural expand that would have succeeded was **never attempted**.

**Contradicts:** `skills/generate/SKILL.md:276-277` documents `# Fallback: structural-only (still valuable; always available) task-master expand --all`; `skills/expand-tasks/SKILL.md:175` error row only says "Exit skill" on rate-limit. The "always available" fallback exists only in prose.

**Fix:** On research-provider failure (timeout / non-zero exit / LLMError kind in `{rate_limit, quota, auth, no_key}`), retry the SAME expansion **without** `--research` before marking the task failed — add a final attempt dropping `--research` from `_run_one_attempt`'s argv, and a `research=False` structural retry in `NativeBackend._expand_packet` on non-`invalid_json` LLMError. Surface a `degraded=True` flag so the UX reports "expanded structurally (research unavailable)" instead of failing.

---

### P1 — major (silent wrong behavior / broken documented feature / risk)

#### P1-1 · `parse-prd` reports `ok=true`/`task_count=0` (CLI exits 0) when the model produced zero tasks
`backend.py:718-722` returns `{"ok": True, "task_count": len(tasks)}` on `returncode==0` with **no guard** that `len(tasks)>0`; `cli.py:87-89` exits 0 whenever `ok` is truthy. Reproduced live: fake parse-prd that warns to stderr and exits 0 → `ok:true, task_count:0, EXIT 0`. The only downstream defense is the GENERATE gate (`pipeline.py:100-101`), and `generate/SKILL.md:39-44` tells the agent to "proceed past this gate on first entry." **Fix:** treat `len(tasks)==0` on `returncode==0` as `ok=False` with an explanatory error; mirror in `NativeBackend.parse_prd`; stop documenting a gate bypass.

#### P1-2 · `research_choice='real_api_if_key'` (balanced default) selects paid Perplexity on KEY PRESENCE over the available free local proxy, never validating the key
*(merges three finder reports)* `providers.py:209-216`: the paid-Perplexity branch (`:211-212`) is evaluated **before** the `elif local_proxy_available` branch (`:215`); `_has_perplexity_api_key()` (`:125-129`) checks presence only. Reproduced: with `PERPLEXITY_API_KEY=pplx-JUNK` and proxy up, research→`perplexity/sonar` (paid); with the key unset, research→the free `openai-compatible` proxy. Fires only when the research role is empty (so latent behind P0-1, not the dogfood cause). **Fix:** when the free proxy answers a real 200 probe, prefer it unless the user explicitly opted into paid AND the key passes a validity probe.

#### P1-3 · Zero provider credential validity/health check before writing config or before parse — presence is the only signal
`has_anthropic_key` (`providers.py:171`) and `_has_perplexity_api_key` (`:125`) are pure presence checks; the local-proxy "availability" check (`:202-206`) trusts a URL substring OR a bare TCP-open (`lib.py:259`, no HTTP 200 probe); `backend.py:701-722` shells to the provider with no pre-flight and returns `task_count:0`+stderr on failure. Out-of-quota keys (the dogfood reality) are undetectable. **Fix:** add a lightweight health probe used by both configure (pre-write) and the SETUP gate (pre-parse): `which`+`--version` for CLIs, a real HTTP 200 for the proxy, at minimum key-format sanity (optionally a cheap auth ping) for paid APIs.

#### P1-4 · The one branch that mutates a populated main role (tier-migration) keeps the unusable provider, only swaps modelId
`providers.py:180-187` → `_main_model_for_start_tier` (`:114-122`) rewrites only `modelId` (provider preserved). Under `conservative` it turns a keyless `claude-sonnet-4` into a keyless `claude-haiku-4-5` — still anthropic, still no key. (One finder downgraded this to P2 because the branch is gated behind a non-default `conservative` economy nothing in the relaunch path selects, and the resulting state is equivalently-broken, not worse.) **Kept at P1 as part of the P0-1 fix scope:** when configure is made to repair, the provider decision must precede and dominate the tier decision. Folding it in costs nothing; shipping the repair without it reintroduces the keyless trap on non-default economies.

#### P1-5 · Skills reference MCP tools that are not registered
`tm_parse_prd` (`generate/SKILL.md:211`), `tm_analyze_complexity` (`generate/SKILL.md:225`), `update_pipeline_task_status` (`execute-task/SKILL.md:207`) — none appear in `server.py`'s 33 registered tools (correct names: `parse_prd`, `rate_tasks`, `set_task_status`). An agent following the documented MCP fallback calls a tool that does not exist. (One finder downgraded to P2 since these are labeled "fallback" beneath working CLI primary paths and FastMCP returns a loud not-found error, not silent corruption.) **Fix:** rename in skills, or add thin alias tools in `server.py`.

#### P1-6 · `execute-task` Step 10c pipeline-consistency write is broken on BOTH branches
Primary path calls unregistered `mcp__plugin_prd_go__update_pipeline_task_status` (`execute-task/SKILL.md:207`); the documented fallback points to `mcp-server/pipeline.py:locked_update()` which **does not exist** (real module is `prd_taskmaster/pipeline.py`; `locked_update` lives in `prd_taskmaster/lib.py:78`); the fallback also writes a `phase_evidence.EXECUTE.tasks_completed` key no code reads. The step that exists to keep `pipeline.json` and `tasks.json` consistent has no executable path — `pipeline.json` silently drifts. **Fix:** add an `update_pipeline_task_status(task_id, status)` tool delegating to `prd_taskmaster/pipeline.py`, or rewrite Step 10c onto `advance_phase`/`log_progress` and fix the module path.

#### P1-7 · Concurrent `apply_results`/`write_atomic` on tasks.json loses updates AND crashes (FileNotFoundError)
`parallel.py:84` uses a FIXED tmp name (`path.with_suffix(".json.tmp")`, not pid-unique) and an unlocked read-modify-write (`:125-182`). The correct primitives exist unused (`lib.py:73` pid-suffixed `atomic_write`, `lib.py:78` flock `locked_update`). A 60-run two-thread repro produced 9 lost-update runs and 48 `FileNotFoundError` runs. (One finder downgraded to P3 on the grounds that no shipped engine path invokes `apply_results` concurrently — fan-out is research-only, the apply is single-threaded post-join, fleet workers use isolated worktrees.) **Kept at P1** because the CLI exposes `apply`/`inject` subcommands and the module docstring falsely claims "single-writer safety preserved"; the fix is cheap (route through `lib.atomic_write` + `lib.locked_update`) and removes a latent corruption class. Treat as P1-to-fix / P3-to-block: do not let it block the relaunch on its own, but land it with the cluster.

#### P1-8 · `configure-providers` falsely reports `local_perplexity_api_free:true` while research still points at paid Perplexity
`providers.py:250-251` emits `local_perplexity_api_free` from `local_proxy_available` (`:202-206`, mere reachability), **decoupled** from whether the research role was actually set to the proxy. A consumer/agent trusting the flag believes research is free+working when it is paid — masks the failure. (One finder downgraded to P2: the field is diagnostic-only with no programmatic reader, and on a *clean* stock config the `.env`-write the finding cited does not fire.) **Fix:** only report `true` when `models['research']` is actually the local proxy (check the role dict's own baseURL, not the env-var fallback).

---

### P2 — moderate (degraded UX / fragile / missing fallback)

- **P2-1 · `expand --no-research` and `expand --id` silently ignored when >3 tasks pending.** `backend.py:724-731` calls `tm_parallel.run_tm_parallel(tag=tag)` dropping both `research` and `task_ids`; the serial ≤3 path honors them (`backend.py:744-746`). A fresh viral PRD almost always yields >3 tasks, so the first real run takes the parallel path that hardcodes `--research` — eliminating the one escape hatch precisely when P0-3 bites. **Fix:** thread `research` down to `_run_one_attempt`'s argv and add task selection to `run_tm_plan` (note: `run_tm_parallel`'s signature currently accepts *neither* — full plumbing required, not just arg forwarding).
- **P2-2 · `package.json` postinstall silently pip-installs into the user's active Python env.** `package.json:26` `pip install -r mcp-server/requirements.txt 2>/dev/null || echo WARN`. On PEP-668 distros (Debian 12+/Ubuntu 23.04+/Fedora) this fails with `externally-managed-environment`, swallowed by `2>/dev/null`; the MCP server then can't import `mcp`/`fastmcp` at runtime. Reproduced on this box (has the EXTERNALLY-MANAGED marker). **Fix:** don't auto-pip in postinstall; print the exact venv/pipx command, detect PEP-668, and drop `2>/dev/null` so failure is visible.
- **P2-3 · Engine writes `.env` but never adds `.env`/`.taskmaster/` to `.gitignore`.** `providers.py:223-241` writes `.env`; grep finds zero `.gitignore` writers in the engine. Protection is inherited from `task-master init`, and even that covers `.env` but not `.taskmaster/`. In a repo with a pre-existing hand-rolled `.gitignore`, the engine-created `.env` (and any real keys the user adds beside the dummy) is one `git add .` away from being committed. **Fix:** idempotently ensure `.env` and `.taskmaster/` are in `.gitignore` whenever the engine writes them.
- **P2-4 · Local proxy research role is incompatible with task-master `--research` parse path (envelope shape mismatch).** Proxy returns a bare `{tasks:[...]}` body; task-master's openai-compatible adapter expects `{choices:[{message:{content}}]}` → `AI_TypeValidationError … path ["choices"]`. Degraded-not-fatal (falls through to fallback) and the engine's default parse-prd doesn't pass `--research`, but `expand`/`rate` do route to the research role. **Fix:** have the proxy emit a proper OpenAI chat-completions envelope (durable), or guard expand/rate away from the proxy.
- **P2-5 · `handoff` skill calls `script.py append-workflow`/`debrief`/`handoff-gate` — none exist as CLI subcommands.** `cli.py` DISPATCH has none; verified `invalid choice`. They exist only as MCP tools; `handoff-gate` exists nowhere ("(when implemented)" shipped in `handoff/SKILL.md:341`). MCP-mode works; the documented CLI fallback is dead. **Fix:** add the CLI subcommands as thin wrappers, or relabel as MCP-only with a real inline fallback; implement or remove `handoff-gate`.
- **P2-6 · Test suite encodes the no-op as desired behavior / has no coverage for stock-default correction.** `test_dogfood_fixes.py:174-189` asserts a populated role "is not touched"; no test seeds the stock anthropic/perplexity/anthropic trio keyless and asserts correction. (One finder corrected the mechanism claim — stock anthropic IS in `KNOWN_ENGINE_DEFAULTS` so it doesn't share the exact branch the test covers — and downgraded the "green bar certifies 0-tasks" thesis; the residual coverage gap is real and is folded into Section 5.)

### P3 — minor / polish

- **P3-1 · SHIP_CHECK_OK Gate-5 override is a hardcoded plaintext constant** (`skel/ship-check.py:57` `OVERRIDE_TOKEN="SHIP_CHECK_OVERRIDE_ADMIN"`). The gates themselves are genuinely unfakable; the override is audit-logged + marked `[OVERRIDE]` and is never auto-supplied (not reachable on a first run). README never claims the token is secret. **Fix (optional):** move the override behind an env-set secret/nonce; clarify wording.
- **P3-2 · `package.json` missing `author`/`bugs`/`homepage`** (confirmed: all three `None` at 5.2.0). The npm page 509 stars land on shows no author byline and no "Report issues" link. **Fix:** mirror the three fields from `.claude-plugin/plugin.json`.
- **P3-3 · `install.sh --with-taskmaster` runs `npm install -g task-master-ai`** (the interactive default is YES). Bounded, gated, reversible; `curl|bash` skips it via the `! -t 0` guard. (Title's "pip side-effects" is unsupported — no pip in install.sh.) **Fix:** default the prompt to N; surface that it's a global install.
- **P3-4 · MCP prefix divergence** (`mcp__plugin_prd_go__` hardcoded in skills/hooks). Empirically verified CORRECT for plugin `prd`+server `go` (commit `9c44027`); mitigated by ToolSearch discovery preferring `mcp__atlas-engine__`. Residual polish: re-verify against a clean `/plugin install prd`.
- **P3-5 · parse-prd failure passes through task-master stderr** — the PRD-leak actually goes to STDOUT (which `parse_prd`'s error dict discards), so the named vector is inert in the dogfood replay. No action required beyond optional redaction in the expand `stdout` path.

---

## 4. Ordered fix plan (what to fix first to unblock relaunch)

**Fix 1 — Make `configure-providers` REPAIR keyless stock defaults (closes P0-1, folds in P1-4).**
In `run_configure_providers`: add a `KNOWN_STOCK_TASKMASTER_DEFAULTS` set (the exact init dicts). Treat a role as correctable when it is empty OR a stock default whose provider is unusable in the current env (anthropic w/o key, perplexity w/o valid key while proxy up). Resolve the desired *usable* provider first (claude-code/codex-cli when CLI present + no key; free proxy for research when a 200 probe passes), THEN apply tier on top of that provider. Then edit `skills/setup/SKILL.md` Step 3 to ALWAYS run configure-providers and fix the DETECT-FIRST table so "unreachable provider" ≠ SKIP.

**Fix 2 — Make the SETUP gate credential-aware (closes P0-2).**
In `mode_recommend.validate_setup`, replace `provider_ok = bool(main_model)` with reachability checks per provider type (key present for anthropic/perplexity, CLI on PATH for claude-code/codex-cli, 200 probe for the proxy). A keyless paid stack must produce a critical failure with an actionable fix string.

**Fix 3 — Add structural fallback to `expand` on research-provider failure (closes P0-3).**
In `tm_parallel._run_one_attempt`/`_run_packet` add a final attempt dropping `--research`; in `NativeBackend._expand_packet` add a `research=False` retry on non-`invalid_json` LLMError. Surface `degraded=True`. This is the single highest-leverage fix for the most common first-run outage.

**Fix 4 — Quota/validity-aware research routing + honest reporting (closes P1-2, P1-3, P1-8).**
Add the shared health probe (P1-3); prefer the free proxy over an unvalidated paid key (P1-2); only report `local_perplexity_api_free:true` when the research role IS the proxy (P1-8).

**Fix 5 — parse-prd zero-task = failure (closes P1-1).**
Return `ok=False` on `returncode==0` with `len(tasks)==0`; stop documenting the GENERATE-gate bypass.

**Fix 6 — Skill/MCP plumbing (closes P1-5, P1-6, P2-5).**
Rename the three dead tool refs; add `update_pipeline_task_status` + the `append-workflow`/`debrief` CLI subcommands (or fix the docs + module paths); implement or remove `handoff-gate`.

**Fix 7 — Hygiene + polish (P1-7, P2-1, P2-2, P2-3, P3-2).**
Route parallel writes through `lib.atomic_write`+`lib.locked_update`; forward `--no-research`/`--id` through the parallel path; replace the postinstall auto-pip with an informational message; ensure `.gitignore` entries; add npm metadata.

**Re-gate before SHIP:** full suite green + the three regression tests below + a clean dogfood replay (`init → configure → parse → expand`) reaching `task_count>0` and non-zero subtasks with `ANTHROPIC_API_KEY` unset and Perplexity out-of-quota.

---

## 5. Tests that must be added (the coverage gaps that let this ship)

A 237/318 all-green suite shipped a guaranteed-broken first run because it only exercises the empty-role happy path. Gate the relaunch on these going green:

1. **Stock-default correction (catches P0-1, P1-4, P2-6).** Seed `{main:anthropic/claude-sonnet-4, research:perplexity/sonar, fallback:anthropic/claude-3-7-sonnet}` with `ANTHROPIC_API_KEY`/`PERPLEXITY_API_KEY` unset and `claude` CLI + local proxy available. Assert configure-providers rewrites `main→claude-code`, `fallback→codex-cli`, `research→openai-compatible` local proxy. Repeat under `conservative` economy and assert provider is corrected before tier. Also update `test_configure_providers_user_configured_main_is_not_touched` to seed an actually-usable (key-bearing) provider, not a keyless paid one.

2. **Credential-aware SETUP gate (catches P0-2).** With the stock paid config and no keys, assert `validate_setup().ready == False` and `critical_failures > 0` with a provider-credential failure naming the fix.

3. **Research-failure structural degradation (catches P0-3).** Fake `task-master` that fails iff `--research` is present and succeeds structurally. Assert `expand` still lands subtasks via a no-`--research` retry, returns `ok=True`, and marks `degraded=True`. Cover both the parallel (>3 tasks) and serial (≤3) paths.

4. **parse-prd zero-task = failure (catches P1-1).** Fake parse-prd that exits 0 without writing tasks. Assert `parse_prd` returns `ok=False`. Mirror for `NativeBackend`.

5. **Research routing prefers free proxy / validates key (catches P1-2, P1-8).** Empty research role + an exhausted/garbage `PERPLEXITY_API_KEY` + proxy up: assert research resolves to the free proxy (or paid only after a validity probe) and that `local_perplexity_api_free` is reported `true` ONLY when the role is the proxy.

6. **Concurrent apply integrity (catches P1-7).** Two-thread/two-process `apply_results` for different ids: assert both ids' subtasks survive and no `FileNotFoundError`.

> The unifying lesson: every existing provider test asserts "we don't touch the user's config" against an *empty* or *user-customized* baseline. None assert "we CORRECT a keyless stock default" — which is the exact production state `task-master init` creates. The relaunch's stability depends on inverting that test bias.
