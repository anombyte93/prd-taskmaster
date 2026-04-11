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

**If no provider configured or API key missing**:
- Default to `claude-code` provider (zero API key required for Claude Max users):
```bash
task-master models --set-main claude-code
```
- If user is NOT on Claude Max, offer alternatives:
```
No API key detected. Options:
  1. claude-code (zero API key — requires Claude Max subscription)
  2. anthropic (requires ANTHROPIC_API_KEY)
  3. openai (requires OPENAI_API_KEY)
```

**If provider already configured**: Report status silently.

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
