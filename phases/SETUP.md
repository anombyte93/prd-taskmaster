# Phase 0: Setup Gate

## The One Rule

**Verify TaskMaster is installed, initialized, and working before anything else. Zero user effort.**

## Checklist

Copy into your response:
```
SETUP CHECKLIST:
- [ ] TaskMaster binary found (`which task-master-ai`)
- [ ] `.taskmaster/` exists (or `task-master init` run)
- [ ] Provider configured (`task-master models` shows active provider)
- [ ] Probe test passed (trivial expand_task succeeded)
```

## Step 1: Check Installation

```bash
which task-master-ai
```

**If not found**: Show install instructions and block:
```
TaskMaster not installed. Install with:
  npm install -g task-master-ai

Then re-run this skill.
```

**If found**: Continue silently.

## Step 2: Initialize Project

Check if `.taskmaster/` directory exists in the current project.

**If missing**:
```bash
task-master init --yes
```

**If exists**: Continue silently.

## Step 3: Configure Provider

```bash
task-master models
```

Check the output for an active main model provider.

**Important:** TaskMaster's CLI uses a two-argument model syntax: `--set-main <model-id> --<provider-flag>`. The model ID is NOT the provider name. For the claude-code provider the valid model IDs are `sonnet`, `opus`, and `haiku` (all FREE via Claude Max — no API key required).

**If no provider configured or API key missing**, default to `claude-code` + `sonnet` (zero API key for Claude Max users) and also set research + fallback so task operations work autonomously:

```bash
task-master models --set-main sonnet --claude-code
task-master models --set-research opus --claude-code
task-master models --set-fallback haiku --claude-code
```

This configures the full trio with zero API cost. Verify with `task-master models` — the Main/Research/Fallback rows should all show `claude-code` provider with `Free` cost.

**If user is NOT on Claude Max**, offer alternatives:
```
No Claude Max detected. Provider options:
  1. claude-code (FREE — requires Claude Max subscription)
  2. anthropic (requires ANTHROPIC_API_KEY)
  3. openai (requires OPENAI_API_KEY)
  4. openrouter (single key, many providers — ANTHROPIC-compatible free models available)
  5. ollama (local, free, slower — no cloud calls)
```

**If provider already configured**: Report status silently.

**Common failure mode:** users who run `task-master models --set-main claude-code` (without a model ID) see `Error: Model ID "claude-code" not found`. That's the wrong syntax — `claude-code` is a provider flag, not a model ID. Always use `--set-main <sonnet|opus|haiku> --claude-code`.

## Step 4: Probe Test

Verify the AI pipeline actually works by expanding a trivial task:

**MCP**: Call `analyze_complexity` or `expand_task` on task 1 (if tasks exist)
**CLI**: `task-master analyze-complexity --id 1` (if tasks exist)

If no tasks exist yet (fresh project), skip the probe — provider config from Step 3 is sufficient.

**If probe fails**: Report the error and suggest checking API keys or provider config.
**If probe succeeds**: Continue silently.

## Step 5: Report Status

Display a compact status line:
```
Setup:
  ✓ TaskMaster: installed (vX.Y.Z)
  ✓ Project: initialized (.taskmaster/)
  ✓ Provider: claude-code (zero API key)
  ✓ Pipeline: verified
```

## Evidence Gate

**Gate: TaskMaster installed, project initialized, provider configured, pipeline verified. Proceed to DISCOVER.**
