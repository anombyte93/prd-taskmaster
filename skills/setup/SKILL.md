---
name: setup
description: >-
  Phase 0 of the prd-taskmaster pipeline. Resolves the active backend,
  initializes the project, configures the provider stack when the TaskMaster
  backend is active (DETECT-FIRST — never overwrite a working user config),
  and verifies the AI pipeline. Autonomous: zero user questions unless a hard
  block is hit. Declares the Setup phase complete so DISCOVER can follow.
user-invocable: false
allowed-tools:
  - Read
  - Bash
  - Skill
  - ToolSearch
  - mcp__atlas-engine
  - mcp__plugin_prd_go
  - mcp__plugin_prd-taskmaster_go
  - mcp__plugin_atlas-go_go
---

# Phase 0: Setup

Declarative phase skill. Invoked by the prd-taskmaster orchestrator when
`current_phase` is null or `SETUP`. Never called directly by a user.

## Entry gate

1. Call `mcp__plugin_prd_go__check_gate(phase="SETUP", evidence={})` for diagnostics.

   `check_gate` is an EXIT gate: it verifies you have the evidence to *advance*, not to
   *enter*. On first entry you have no evidence yet (Step 4 below produces
   `validate_setup.ready=true`), so a `gate_passed: false` result here is EXPECTED — the
   state machine's legal transitions (`None → SETUP`) already guarantee only legal entry.

   - **First entry** (no evidence yet): note the result and continue with the Procedure.
   - **Re-entry**: if the gate reports violations, report them and stop — it protects
     against re-running a completed phase or skipping ahead.

   Enforce the gate when you ADVANCE (after the procedure), not on entry.

## Procedure (5 steps, abort on hard failure)

### Step 1: Backend detection

Run backend detection:

```bash
python3 script.py backend-detect
```

The native engine is the sole generator and needs no external binary — a
keyless host CLI (`claude` / `codex` / `gemini`) on PATH, or a provider API key,
is sufficient (see Chunk 7's `atlas setup` wizard). The `task-master` binary is
no longer required or supported; `backend-detect` reports its presence purely as
informational. Continue with the resolved (native) backend.

### Step 2: Project init

Check whether the current project has a `.taskmaster/` directory (the engine
still reads/writes the `.taskmaster/` file format for tasks and config).

If missing, run backend op `init`:

```bash
python3 script.py init-project
```

This initialises the native project state and the `.taskmaster/` file format. If
`.taskmaster/` is present, continue.

### Step 2.5: Customisation bootstrap (REQUIRED — closes execute-task deadlock)

`execute-task` requires `.atlas-ai/customizations/system-prompt-template.md`
to exist as a precondition (its Entry gate halts otherwise). It cannot
create the file from inside the loop — the failure mode is a hard halt with
no recovery path.

This step ensures the file exists BEFORE execute-task ever runs:

```bash
PLUGIN_SKEL="${CLAUDE_PLUGIN_ROOT}/skel/customizations"
mkdir -p .atlas-ai/customizations
if [ ! -f .atlas-ai/customizations/system-prompt-template.md ]; then
  if [ -d "$PLUGIN_SKEL" ]; then
    cp -n "$PLUGIN_SKEL"/*.md .atlas-ai/customizations/  # -n: no-clobber, copy starter pack
  else
    : > .atlas-ai/customizations/system-prompt-template.md  # empty is fine per execute-task Entry gate
  fi
fi
```

The starter pack (`domain-vocabulary.md`, `system-prompt-template.md`,
`task-enrichment-rules.md`, `verification-preferences.md`) is editable —
users tune them to project-specific terminology. Empty is acceptable; the
file simply must exist.

Also scaffold `.atlas-ai/ship-check.py` if it doesn't already exist:

```bash
if [ ! -f .atlas-ai/ship-check.py ] && [ -f "${CLAUDE_PLUGIN_ROOT}/skel/ship-check.py" ]; then
  cp "${CLAUDE_PLUGIN_ROOT}/skel/ship-check.py" .atlas-ai/ship-check.py
  chmod +x .atlas-ai/ship-check.py
fi
```

(Codified 2026-06-04 — yesterday's run halted at execute-task Entry
because `system-prompt-template.md` was missing; the file had to be
manually `touch`-ed from outside the loop.)

### Step 3: Provider configuration — DETECT-FIRST

When the TaskMaster backend is active, **read `task-master models` output BEFORE
setting anything.** This is the load-bearing rule. A working user config must
NOT be overwritten silently. When the native backend is active, provider
configuration is handled by the resolved backend and this TaskMaster-specific
step is informational only.

| `task-master models` output | Action |
|---|---|
| Main / Research / Fallback all populated with a supported provider | SKIP — go to Step 4. |
| Main set, Research/Fallback empty | Partial mutate — fill the empty roles only. |
| All three empty (fresh install) | Full configure — use the default stack below. |
| Provider flagged unsupported / deprecated | Ask the user before mutating. |

**Why DETECT-FIRST:** v4 dogfood (2026-04-13, LEARNING #9) caught the skill
overwriting a working `gemini-cli / gemini-3-pro-preview` config because the
procedure wasn't branch-aware. Detect first, mutate only the empty slots.

**Default stack (fresh install only):**

```bash
task-master models --set-main gemini-3-pro-preview --gemini-cli
task-master models --set-research gemini-3-pro-preview --gemini-cli
task-master models --set-fallback gemini-3-flash-preview --gemini-cli
```

Why Gemini CLI: ~113× more token-efficient than sonnet on parse-prd, free via
any Google account, no API key. One provider, three roles, zero cost.

**Alternatives:** Claude Max (`--claude-code sonnet/opus/haiku`), any of the
12 task-master provider families, or a registered MCP research tool for the
Research role.

### Step 4: Probe test

If tasks already exist, call the MCP tool
`mcp__plugin_prd_go__validate_setup` or run backend op `rate`:

```bash
python3 script.py rate
```

If no tasks exist yet (fresh project), skip the probe — Step 3's provider
configuration is sufficient evidence the pipeline is wired.

### Step 5: Status line

Render the preflight progress panel and print it. MCP-mode: call
`render_status(phase="SETUP")` and print its `rendered` field. CLI-mode:
`python3 script.py status --phase SETUP`. (Fallback if the renderer is
unavailable — emit a compact one-block status:)

```
Setup:
  task-master: installed (<version>)
  project: initialized (.taskmaster/)
  provider: <main-provider> (main) / <research-provider> (research)
  pipeline: verified
```

## Exit gate

After Steps 1–5 report green:

1. Call `mcp__plugin_prd_go__advance_phase(expected_current="SETUP", target="DISCOVER", evidence={"validate_setup": <Step 4 result dict>, "provider_configured": True})`.
   The call atomically transitions `pipeline.json` from SETUP to DISCOVER.
   The `expected_current` field is the compare-and-swap guard;
   `evidence` is stored under `phase_evidence[DISCOVER]` for audit.
2. Return control to the orchestrator (`prd-taskmaster` skill). Do NOT invoke
   DISCOVER directly — the orchestrator re-reads `current_phase` and routes.

## Red flags (stop and report, do not paper over)

- "The config is set but looks wrong — I'll fix it" → NO. Report and ask.
- "No tasks exist so I'll skip backend detection" → NO. Backend detection must
  run before DISCOVER so later backend ops resolve consistently.
- "I'll auto-install task-master via npm" → NO. Installation is a user action;
  this skill only reports that installation unlocks the TaskMaster backend.
- "I can call advance_phase without check_gate" → NO. Gate first, always.

## Non-exits

This skill does not use explicit process termination. A hard block reports
the reason and returns control to the orchestrator; the orchestrator decides
whether to surface to the user.
