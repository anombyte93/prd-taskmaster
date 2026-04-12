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

**Important:** TaskMaster's CLI uses a two-argument model syntax: `--set-main <model-id> --<provider-flag>`. The model ID is NOT the provider name.

### Recommended stack (v4 default)

**Gemini + Perplexity** is the documented default as of v4:

```bash
task-master models --set-main gemini-3-pro-preview --gemini-cli
task-master models --set-research sonar-pro --perplexity   # requires PERPLEXITY_API_KEY
task-master models --set-fallback gemini-3-flash-preview --gemini-cli
```

Why this stack: Gemini is 113× more token-efficient than sonnet for parse-prd (measured 6K vs 684K tokens on the same PRD), free via any Google account, no subscription. Perplexity's `sonar-pro` model is web-grounded so research calls return up-to-date citations instead of stale training data.

**If PERPLEXITY_API_KEY is not set**, research falls back to Gemini:
```bash
task-master models --set-research gemini-3-pro-preview --gemini-cli
```

### Alternative: Claude Max

If you already have a Claude Max subscription, this is the zero-install path:
```bash
task-master models --set-main sonnet --claude-code
task-master models --set-research opus --claude-code
task-master models --set-fallback haiku --claude-code
```

### Alternative: other providers

TaskMaster supports 12 provider families. Pick whichever you already have credentials for:
```
  anthropic       — ANTHROPIC_API_KEY
  openai          — OPENAI_API_KEY
  openrouter      — OPENROUTER_API_KEY (single key, many models, free tiers available)
  ollama          — local, free, slower, no cloud
  bedrock         — AWS Bedrock
  vertex          — GCP Vertex AI
  codex-cli       — OpenAI Codex CLI (free via ChatGPT subscription)
  lmstudio        — local LM Studio
  openai-compatible — any OpenAI-schema-compatible endpoint
```

Run `task-master models --help` for the full flag syntax.

**Common failure mode:** users who run `task-master models --set-main claude-code` (without a model ID) see `Error: Model ID "claude-code" not found`. That's the wrong syntax — `claude-code` is a provider flag, not a model ID. Always use `--set-main <model_id> --<provider-flag>`.

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
