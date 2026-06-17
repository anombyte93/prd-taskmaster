# Atlas Engine — Hybrid Provider + Setup Layer

**Status:** Design approved (pending written-spec review)
**Date:** 2026-06-15
**Owner:** Hayden
**Sub-project:** #1 of the "remove task-master, build the Atlas engine" initiative
**Surfaces:** CLI (`atlas setup`, `script.py`) and Claude Code skill (`/atlas`)

---

## 1. Context & Problem

Task generation feels slow ("20+ minutes, not parallel") even though parallel
expansion code exists. The root cause (see the full audit:
`docs/audit` / dashboard `cloud.atlas-ai.au/s/AwWXlLaV6gT5DzB`) is **not** missing
parallelism — it is a credential gate:

- `NativeBackend.expand()` fans every task over a `ThreadPoolExecutor`
  (`backend.py:444-451`) — but only runs when `llm_client.discover_key()` finds a
  raw API key (`backend.py:430`).
- In the common interactive Claude Code case there is **no `ANTHROPIC_API_KEY`**,
  so generation falls back to `agent_action_required` (`backend.py:433-435`) and the
  orchestrating session expands tasks one conversational turn at a time. That is the
  slow run.
- `TaskMasterBackend` papers over this by shelling out to the external `task-master`
  npm binary (`tm_parallel.py`), which is a dependency we want to delete.

**Goal:** make the native engine the sole generator, remove the `task-master-ai`
dependency, and make parallel generation work **with zero API key** by adding a
keyless CLI-agent provider — fronted by a setup wizard that beats
`task-master models --setup`.

### The one finding that shapes everything

There are exactly two provider paths today: **raw-key HTTP API** and **agent-plan
fallback**. There is **no in-process "shell out to `claude -p` for structured JSON"**
path. The only code that drives a model CLI is `tm_parallel.py`, and it drives the
`task-master` binary, not `claude`/`codex`/`gemini`. **The keyless CLI-agent provider
is the net-new component** that fills the gap between the two existing paths.

Verified the mechanism exists: `claude --print --output-format json` +
`claude --json-schema <schema>`; `codex exec` (non-interactive); `gemini -p`. All three
CLIs are on PATH in the target runtime.

---

## 2. Decisions (locked)

1. **Provider strategy = HYBRID, 3-tier:** keyless CLI-agent → raw-key API →
   agent-plan floor.
2. **When BOTH a raw key and a CLI exist:** the **setup wizard asks once**
   ("free-but-slower keyless, or paid-but-faster key, as primary?") and writes
   `keyless_default`. **No global default is imposed.** (Resolves the key-vs-CLI
   contradiction.)
3. **claude-code is primary keyless;** codex/gemini are **fallback-only** until their
   schema-less JSON parse-failure rate is measured.
4. **`--json-schema` when available**, graceful demote to prompt + `_extract_json`.
5. **Spawn-probe result cached** (TTL 900s, invalidated on first spawn failure) to kill
   the per-call 60s probe cost.
6. **Concurrency:** sub-project #1 only exposes the `engine.concurrency` hook;
   **sub-project #2 owns the RAM-aware clamp + wave feedback.**
7. **`grokCli` stub dropped** (wired nowhere); may be added as a 4th keyless CLI later.
8. **File formats unchanged:** `.taskmaster/config.json` and `tasks.json` stay; only the
   `task-master` *binary* dependency is removed. Existing projects migrate with zero file
   changes.
9. **`validate_setup` is refactored, not reused verbatim.** Its checks 1–2 (`binary`,
   `version`) are hard-coded to the `task-master` binary (`TASKMASTER_MIN_VERSION="0.43.0"`,
   fix hint `npm install -g task-master-ai`, `mode_recommend.py`). Since §9 deletes that
   binary, those two checks must become no-ops (or be dropped) when `provider_mode != plan_only`,
   so the keyless engine does not fail its own validator on the dependency we are removing.
   Only checks 5–6 (`provider_main`/`provider_research`) are credential/CLI-aware and reused
   as-is.

**Open questions blocking implementation:** none.

---

## 3. Architecture — 3-tier hybrid resolver

```
resolve_provider(role, op_class)  ── per role (main / fallback / research), at gen time
      │
      1  KEYLESS CLI-AGENT   ★ NEW: prd_taskmaster/cli_agent.py ★
      │    claude -p "<prompt>" --output-format json --json-schema <schema>
      │    (uses existing Claude Code session auth — no API key, free, N-parallel)
      │    codex exec / gemini -p for the others
      │
      2  RAW-KEY API         (existing llm_client.generate_json — unchanged)
      │    ANTHROPIC_API_KEY / OPENAI — in-process parallel HTTP, paid
      │
      3  AGENT-PLAN FLOOR    (existing _agent_*_action packets — never deleted)
           hands a parallel fan-out plan to the orchestrating session
```

Precedence order between tier 1 and tier 2 is governed per-project by
`keyless_default` (set by the wizard, decision #2). The CLI-agent worker drops into the
existing `ThreadPoolExecutor` (`backend.py:444`), so **parallel-by-default is inherited
for free** — N concurrent `claude -p` children run exactly like N concurrent HTTP calls.

---

## 4. Config schema — keep / extend

### Keep as-is (no renames; migration-safe)
- **`.taskmaster/config.json`** — role models `main`/`fallback`/`research`, each
  `{provider, modelId, maxTokens, temperature, baseURL?}` (`config.json:2-46`).
- **`.atlas-ai/fleet.json`** — `max_concurrency`, `routing`, `token_economy`, `backend`,
  `escalation` (`fleet.py:43-49`, `load_fleet_config` `fleet.py:75-135`).
- **`.atlas-ai/config/atlas.json`** — `/customise-workflow` token-economy override.

### ADD — `engine` block in `fleet.json` (additive, all defaulted)

```jsonc
{
  "engine": {
    "provider_mode": "hybrid",        // hybrid | api_only | cli_only | plan_only
    "keyless_default": null,          // null until wizard asks; true=CLI-first, false=key-first
    "cli_agent": {
      "structured_json": "auto",      // auto = claude --json-schema if supported, else prompt+extract
      "probe_cache_ttl_s": 900,
      "per_call_timeout_s": 180,
      "max_inflight": null            // null = inherit max_concurrency
    },
    "concurrency": {
      "structured_gen": null,         // null = inherit max_concurrency / tm_concurrency profile
      "ram_aware": false              // reserved for sub-project #2
    }
  }
}
```

- `provider_mode` replaces the legacy `backend` (auto/taskmaster/native) knob once
  TaskMaster is deleted; it is provider-strategy, not backend-binary.
- `keyless_default` encodes decision #2. `null` means "wizard hasn't asked yet" — the
  resolver treats `null` as keyless-first (free) until the user states otherwise. This is the
  **behavioral default of an unset flag, not a persisted global choice** — decision #2's "no
  global default imposed" stands: the persisted value is only ever written by the wizard.

---

## 5. Provider resolution order (exact)

Unify the today-split decision (`discover_key()` + the `agent_action_required` fallback)
into one resolver `resolve_provider(role, op_class) -> ProviderHandle`.

**For `main`/`fallback` (structured generation), with `keyless_default` truthy/null:**

1. **CLI-agent** if `provider_mode ∈ {hybrid, cli_only}` AND the role's provider is a
   spawning CLI (`claude-code`/`codex-cli`/`gemini-cli`, `_SPAWNING_PROVIDERS`
   `providers.py:111`) AND *usable* (binary on PATH **and** `_probe_spawn()` true,
   cached).
2. **Raw-key API** if `provider_mode ∈ {hybrid, api_only}` AND `discover_key()` returns
   creds (`llm_client.py:44-67`).
3. **Agent-plan fan-out** — always the floor.

With `keyless_default=false`, swap (1) and (2).

**For `research`:** explicit chain — local Perplexity proxy → Perplexity MCP →
`PERPLEXITY_API_KEY` → CLI-agent. Research stays off the **strict-JSON** CLI path (free proxy
returns prose, `llm_client.py:6-8`); when the CLI-agent is the research tier it runs in
**prose mode** (no `--json-schema`), and its output is normalized downstream — research never
requires strict JSON.

### "Usable" — single source of truth

Promote `_provider_usable()` (`providers.py:73-99`) to the runtime gate, extended with the
spawn probe:

| Provider | Usable when |
|---|---|
| `anthropic` / `openai` / `perplexity` | respective API key present |
| `claude-code` | `which("claude")` **and** `_probe_spawn("claude-code")` |
| `codex-cli` / `gemini-cli` | `which(bin)` **and** `_probe_spawn` |
| unknown (openrouter/ollama/…) | assumed usable — never clobber user choice |

The spawn-probe extension is the critical fix: a `claude-code` provider inside a nested
Claude session may be refused (`providers.py:108-110`, gh #11); resolution must
**empirically demote** rather than fail.

---

## 6. The keyless CLI-agent provider (net-new)

New module `prd_taskmaster/cli_agent.py`:
`generate_json_via_cli(provider, prompt, *, system, schema_hint, model, op_class, task_id, timeout)`
— the structured-JSON twin of `llm_client.generate_json()`, shelling out to a host CLI
with its existing session auth (no API key).

```python
# claude-code: hard structured output (preferred — flag verified)
[claude, "-p", prompt, "--output-format", "json", "--json-schema", schema_json]
# parse stdout JSON envelope; .result IS the model JSON.

# codex-cli: non-interactive exec, prompt-carried schema + extraction
[codex, "exec", "--skip-git-repo-check", "-"]   # prompt on stdin; _extract_json on stdout

# gemini-cli:
[gemini, "-p", prompt]                            # prompt+schema; _extract_json on stdout
```

**Reuse, don't reinvent:**
- `_extract_json()` (`llm_client.py:79-124`) verbatim for codex/gemini and as the
  fallback when `--json-schema` is unavailable.
- The retry policy from `generate_json` (`llm_client.py:204-254`): one parse-retry with
  the error fed back.
- `_probe_spawn()` (`providers.py:127-146`) as the pre-flight gate, cached. The cache is
  **per-process** (a module-level dict keyed by provider) — sufficient to dedupe the probe
  across the in-process `ThreadPoolExecutor` fan-out, which is the case the acceptance
  criteria target. Cross-invocation dedup (separate `script.py` runs) is out of scope for #1;
  if needed later, back it with an on-disk TTL file. Invalidate the entry on the first spawn
  failure regardless of TTL.
- Telemetry via `append_telemetry()` with `backend="native-cli"` (new value alongside
  `native-api` / `taskmaster-api`) so the economy report covers the keyless path.

**Where it plugs in** — in `NativeBackend.parse_prd/expand/rate`, replace the bare
`if not discover_key(): return agent_action_required` with:

```
handle = resolve_provider(role, op_class)
if   handle.kind == "api": result = llm_client.generate_json(...)
elif handle.kind == "cli": result = cli_agent.generate_json_via_cli(handle.provider, ...)
else:                      return {"ok": False, "agent_action_required": _agent_*_action(...)}
```

The agent-plan return is preserved as the floor — never deleted.

---

## 7. Setup wizard UX — "better than `task-master models --setup`"

task-master makes you manually pick a model per role and validates keys *late* (a typo
dies at `parse-prd`). Ours keeps zero-config as the default and adds an optional guided
layer that explains every auto-decision.

**`atlas setup` (new CLI verb) / `/atlas setup` (skill):**

1. **Detect & recommend** (always runs, no prompts) — reuse `run_detect_providers()`
   (`providers.py:374`) + `detect_capabilities()` (`mode_recommend.py:217`):
   ```
   Atlas detected:  claude ✓   codex ✓   gemini ✗   ANTHROPIC_API_KEY ✗   PERPLEXITY proxy ✓
   Recommended (zero-config, keyless):
     main      claude-code/sonnet      ← free via your Claude session, no API key
     fallback  codex-cli/gpt-5.2-codex ← separate quota pool, runs in parallel
     research  perplexity-api-free     ← local proxy on :8765
   [Enter] accept   [c] customise   [k] add an API key   [v] validate only
   ```
2. **Accept (default)** — `run_configure_providers()` (`providers.py:241`) repair-on-detect;
   only rewrites empty/unusable stock defaults, never clobbers user choices.
3. **Customise (`c`)** — task-master-style per-role picker with availability + reason
   annotations (greyed-out = unusable here, with fix hint).
4. **Add key (`k`)** — prompt + write to `.env` via `_ensure_env_entry`. If a key is added
   **and** a CLI exists, **ask the decision-#2 question** and set `keyless_default`.
5. **Validate (`v`, the differentiator)** — `validate_setup()` (`mode_recommend.py:367`,
   6 credential-aware checks) **plus a live one-token probe** per chosen provider
   (`claude -p ok` / `codex --version` / 1-token HTTP ping). Surfaces a real 401/ENOENT
   *before* the pipeline. Exposed standalone as `atlas setup --validate`.

**Surfaces:** `atlas setup` (interactive), `atlas setup --yes` (accept recommendation,
for CI/dispatch), `atlas setup --validate` (dry-run gate). Skill drives the wizard via
`engine_preflight`/`configure_providers`/`validate_setup` MCP tools; Python owns the logic.

---

## 8. Reuse vs build (~70% reuse)

**Build new:** `cli_agent.py`; `resolve_provider()` unified resolver; the `engine` config
block; `atlas setup` wizard steps 3–5; spawn-probe caching.

**Reuse as-is:** `discover_key` (extend ordering), `generate_json` + retry + `_extract_json`,
`_http_call`, `_provider_usable` (+ spawn probe), `_probe_spawn`/`_SPAWNING_PROVIDERS`,
`_desired_*_model` repair ladder, `KNOWN_STOCK_TASKMASTER_DEFAULTS` non-clobber,
`run_configure_providers`/`run_detect_providers`, `validate_setup`, `detect_capabilities`,
economy presets + telemetry, `NativeBackend` `ThreadPoolExecutor` fan-out, `_agent_*_action`
plan packets.

---

## 9. Migration — deleting `TaskMasterBackend` + `tm_parallel.py`

1. **Reach parity** — `cli_agent.py` covers the one capability only `TaskMasterBackend`
   had: keyless generation without a raw key. Once `NativeBackend.expand` runs keyless and
   already fans out in-process, `tm_parallel` has no job.
2. **Flip the default** — `get_backend` (`backend.py:855-867`): `backend="auto"` resolves to
   `NativeBackend` unconditionally. Keep `backend="taskmaster"` for one deprecation release.
3. **Golden-parity gate** — run `AI-golden-parity-refactor`: capture task-graph outputs from
   the TaskMaster path on sample PRDs, prove `NativeBackend`+`cli_agent` produces equivalent
   graphs. Only intended diffs allowed.
4. **Delete** — `TaskMasterBackend`, `tm_parallel.py` (652 lines), `taskmaster.py` binary
   detection, the `task-master-ai` install in `skills/setup`, and
   `backend_detect`/`init_taskmaster`/`tm_parallel_expand` MCP tools. `BACKEND_CHOICES` → `{native}`.
   Keep `KNOWN_STOCK_TASKMASTER_DEFAULTS` (still repairs legacy config files on read).
5. **Keep the file format** — `.taskmaster/config.json` + `tasks.json` unchanged.

Net deletions: ~837 lines + the npm install. The agent-plan floor and `NativeBackend` survive.

---

## 10. Acceptance criteria

- [ ] In a clean project with **no API key** but `claude` on PATH, `parse_prd` and
  `expand_tasks` complete via the CLI-agent path, in parallel, producing a valid task graph
  (no `agent_action_required` fallback).
- [ ] Telemetry rows for that run show `backend="native-cli"`.
- [ ] With both a key and a CLI present, the wizard asks the keyless/paid question and the
  written `keyless_default` is honored by `resolve_provider`.
- [ ] `atlas setup --validate` reports a real auth failure (e.g. bad key) before the pipeline.
- [ ] `_probe_spawn` is invoked at most once per provider per `probe_cache_ttl_s`.
- [ ] Golden-parity: native+cli_agent task graphs match the TaskMaster path on sample PRDs
  (only intended diffs).
- [ ] `task-master` binary is **not** required for any generation operation.

---

## 11. Out of scope (later sub-projects)

- **#2** — RAM-aware concurrency + wave-by-wave feedback UI (the box). #1 only exposes the
  `engine.concurrency` hook.
- **#4** — pluggable real research (Perplexity MCP / research subagent) to close
  task-master's one genuine quality advantage.
- Full removal of `task-master` happens at the *end* of #1 (step 9), gated on golden parity.

---

## 12. Key files

- `prd_taskmaster/providers.py` — detection/repair/usability/spawn-probe
- `prd_taskmaster/llm_client.py` — API path + `discover_key` + `_extract_json` (reuse)
- `prd_taskmaster/backend.py` — `NativeBackend` (extend), `TaskMasterBackend` (delete), agent packets
- `prd_taskmaster/tm_parallel.py` — npm-dependent parallel expand (delete target, 652 lines)
- `prd_taskmaster/fleet.py` — fleet.json loader (add `engine` block)
- `prd_taskmaster/economy.py` — presets + telemetry (reuse)
- `prd_taskmaster/mode_recommend.py` — `validate_setup` + `detect_capabilities` (wizard)
- `prd_taskmaster/batch.py` — `run_engine_preflight` batched detector
- `skills/setup/SKILL.md` — DETECT-FIRST skill surface to extend
- **NEW:** `prd_taskmaster/cli_agent.py` — keyless CLI-agent structured-JSON provider
