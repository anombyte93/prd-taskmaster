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

## Step 3: Configure Provider (DETECT FIRST, MUTATE ONLY IF EMPTY)

```bash
task-master models
```

**READ the output carefully before running any `--set-*` commands.** If Main, Research, and Fallback slots are already populated with a supported provider, **SKIP the rest of this step entirely and proceed to Step 4 (probe test).** The user already has a working config and we must not overwrite it.

### How to decide: mutate or skip?

| `task-master models` output | Action |
|---|---|
| Main/Research/Fallback all show a provider + model ID | **SKIP** — config is valid, do not mutate. Go to Step 4. |
| Main is set but Research/Fallback are empty | **Partial mutate** — only set the missing roles, never overwrite what exists. |
| All three empty, no config file, fresh install | **Full configure** — use the recommended stack below. |
| Provider name shown but flagged as "unsupported" or "deprecated" | **Ask the user before mutating.** Do not silently swap. |

This detect-first rule exists because v4 dogfood (2026-04-13) surfaced LEARNING #9: the skill blindly overrode an existing `gemini-cli / gemini-3-pro-preview` config with `claude-code / sonnet` because the prose documentation made the child think "I should configure this." That was a scope violation. **A user whose config already works wants the skill to leave them alone in that dimension.**

**Important:** TaskMaster's CLI uses a two-argument model syntax: `--set-main <model-id> --<provider-flag>`. The model ID is NOT the provider name.

### Recommended stack (v4 default)

**Gemini CLI across all three roles** is the documented default as of v4:

```bash
task-master models --set-main gemini-3-pro-preview --gemini-cli
task-master models --set-research gemini-3-pro-preview --gemini-cli
task-master models --set-fallback gemini-3-flash-preview --gemini-cli
```

Why this stack: Gemini is 113× more token-efficient than sonnet for parse-prd (measured 6K vs 684K tokens on the same PRD), free via any Google account, no subscription, no API key. One provider, three roles, zero cost.

**Research role is provider-agnostic.** The default uses Gemini CLI for the research role (free, same provider as main/fallback). If you want a different research backend you have three options, in order of simplicity:

1. **Any task-master provider**: pick any of the 12 supported provider families for the research role — `task-master models --set-research <model_id> --<provider-flag>`. Works for OpenAI, Anthropic, OpenRouter, Ollama, Bedrock, Vertex, etc.
2. **Your own MCP research tool**: if you have an MCP server that exposes research-style tools (search/ask/reason), register it in `~/.claude.json` `mcpServers` block. Claude Code will make those tools available during the DISCOVER phase. The skill does not hard-code any specific MCP — it uses whatever's available.
3. **Web-grounded research via paid API**: task-master supports Perplexity via `--perplexity` when `PERPLEXITY_API_KEY` is set. Only use this path if you already have a paid key — it is not the recommended default.

**Default recommendation:** Gemini CLI for all three task-master roles. Zero keys, zero setup, one provider, free.

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
