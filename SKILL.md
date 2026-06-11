---
name: prd-taskmaster
description: >-
  Zero-config goal-to-tasks engine (the Atlas engine). Takes any goal (software, pentest,
  business, learning), runs adaptive discovery via brainstorming, generates a validated spec,
  parses into TaskMaster tasks, and hands off to execution. Use when user says "PRD", "product
  requirements", "I want to build", invokes /atlas, or wants task-driven development.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
  - WebSearch
---

# prd-taskmaster — the Atlas engine

Zero-config goal-to-tasks engine. AI handles discovery and content; `script.py` handles mechanics.

**Command:** `/atlas` is the canonical invocation (or `/prd-taskmaster`, or just say "I want to
build …"). The full plugin install also exposes phase skills; this standalone skill runs the whole
pipeline inline.

**Script:** `~/.claude/skills/prd-taskmaster/script.py` (all commands output JSON). It is a thin
shim over the bundled `prd_taskmaster/` package — the single source of truth shared with the plugin.

**Manual flag:** If the user says `--manual`, `manual=true`, or "do it manually", perform the
TaskMaster mechanics yourself: write `.taskmaster/docs/prd.md`, write `.taskmaster/tasks/tasks.json`
with tasks and subtasks, run `validate-tasks`, then run `enrich-tasks`. Do not block on TaskMaster
CLI/MCP parsing.

## When to Use

Activate: PRD, product requirements, taskmaster, task-driven development, "I want to build X", any goal.
Skip: API docs, test specs, project timelines, PDF creation.

## Phase 1: Zero-Config Preflight

Run preflight and auto-detect everything. Ask zero setup questions.

**MCP (preferred — ONE batched call, no script spam):** if an `engine_preflight`
MCP tool is available in your session (plugin install, or the engine's MCP server
registered), call it once — it covers preflight + taskmaster detection + provider
configuration + capabilities and returns a `summary` list to present verbatim.
Skip the individual script calls below entirely.

**CLI fallback (zero-dependency installs):** one batched subcommand, same result:

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py engine-preflight
```

**From preflight JSON, determine the state:**

| Condition | Action |
|-----------|--------|
| `prd_path` exists + `task_count > 0` | Ask: execute tasks / update PRD / new PRD / review |
| `taskmaster_method == "none"` + no manual flag | Show install: `npm install -g task-master-ai`, wait, re-detect |
| manual flag present | Proceed using Native Mode (TaskMaster optional), regardless of TaskMaster CLI/MCP state |
| `has_taskmaster == false` + CLI present | Run `init-taskmaster` (below), then continue |
| `has_taskmaster` but no PRD | Proceed to Discovery |
| `has_crash_state` | Offer: resume from crash point or start fresh |

**Initialise the project if needed, then auto-configure providers** (silent). Always use
`init-taskmaster` — it protects an existing `.mcp.json`, which raw `task-master init`
overwrites with a placeholder template:

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py init-taskmaster      # only when .taskmaster/ absent
python3 ~/.claude/skills/prd-taskmaster/script.py configure-providers
python3 ~/.claude/skills/prd-taskmaster/script.py detect-providers
```

If `configure-providers` returns `recommended_action: "init_taskmaster"`, run
`init-taskmaster` and retry once.

Report compact status:
```
  ✓ Detected: TaskMaster (MCP|CLI)
  ✓ Detected: Provider (Claude Code|Codex CLI|Anthropic API)
  ✓ Detected: Research (Perplexity API Free|Perplexity MCP|Perplexity API|fallback)
```

**Gate: TaskMaster detected OR manual flag present. Providers configured. Proceed to Discovery.**

### Provider Defaults

Always prefer subscription/native providers before paid API keys:

1. Main: `claude-code` / `sonnet` when `claude` exists; otherwise `codex-cli` / `gpt-5.2-codex` when `codex` exists.
2. Fallback: `codex-cli` / `gpt-5.2-codex` when available; otherwise `claude-code` / `sonnet`.
3. Research: local Perplexity API Free through TaskMaster `openai-compatible` provider:
   - model: `sonar`
   - baseURL: `http://127.0.0.1:8765`
   - `.env` key: `OPENAI_COMPATIBLE_API_KEY="local-perplexity-api-free"` (dummy local key only)

Do not require `ANTHROPIC_API_KEY` or paid `PERPLEXITY_API_KEY` when native Claude/Codex and Perplexity API Free are available.

## Phase 2: Discovery

Read the phase file and follow it:
```
Read ~/.claude/skills/prd-taskmaster/phases/DISCOVER.md
```

Progressive, adaptive, domain-agnostic discovery via superpowers:brainstorming.

**Gate: Discovery complete and user approved design. Proceed to Generate.**

## Phase 3: Generate & Validate

Read the phase file and follow it:
```
Read ~/.claude/skills/prd-taskmaster/phases/GENERATE.md
```

Generate spec, validate quality, parse tasks, enrich with metadata.

**Gate: PRD validated GOOD+ and tasks created through TaskMaster parse/expand OR Native Mode. Proceed to Handoff.**

### Native Mode (TaskMaster optional)

Formerly "Manual Mechanics Mode". The engine produces the same validated task graph without
TaskMaster — use it when the user passes `--manual`, TaskMaster isn't installed, or its
parsing/expansion is a poor fit.

1. Generate `.taskmaster/docs/prd.md` normally.
2. Manually write `.taskmaster/tasks/tasks.json` in TaskMaster-compatible shape:
   - top-level object with `tasks: []`
   - each task has `id`, `title`, `description`, `details`, `testStrategy`, `status`, `dependencies`, `priority`, and `subtasks`
   - every task has at least 2 subtasks with `id`, `title`, `description`, `status`, and `dependencies`
3. Run:
   ```bash
   python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks
   python3 ~/.claude/skills/prd-taskmaster/script.py enrich-tasks
   python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks --require-phase-config
   ```
4. Treat successful validation + enrichment + phaseConfig validation as equivalent to TaskMaster parse + expand.

## Phase 4: Handoff

Read the phase file and follow it:
```
Read ~/.claude/skills/prd-taskmaster/phases/HANDOFF.md
```

Detect capabilities, recommend ONE execution mode, hand off. Modes (user-facing names):
**Verified Loop** (recommended when superpowers + a loop runner are present), **Auto-Execute**
(TaskMaster's native loop), **Plan & Drive** (plan only). **Atlas Fleet** — parallel multi-session
execution — appears as an **Atlas Pro** option when a licensed `atlas-launcher` is detected;
otherwise it shows as a locked teaser pointing to https://atlas-ai.au/pro. The free engine is
always fully usable on its own.

**Gate: User chose mode and handoff complete.**

## Script Commands Reference

| Command | Purpose |
|---------|---------|
| `engine-preflight` | ONE batched call: preflight + taskmaster + providers + capabilities + summary |
| `preflight` | Detect environment state |
| `detect-taskmaster` | Find MCP or CLI taskmaster |
| `init-taskmaster` | task-master init with `.mcp.json` protection |
| `configure-providers` | Configure native Claude/Codex + local Perplexity API Free defaults |
| `detect-providers` | Auto-detect AI providers |
| `detect-capabilities` | Scan for available skills/tools; returns tier + recommended mode with reason |
| `load-template --type comprehensive\|minimal` | Load PRD template |
| `calc-tasks --requirements <count> [--scale solo\|team\|enterprise]` | Recommended task count (scale-banded) |
| `validate-prd --input <path>` | Quality checks + placeholder detection |
| `backup-prd --input <path>` | Timestamped backup |
| `validate-tasks [--input <path>]` | Validate manually-authored tasks.json |
| `enrich-tasks` | Add phaseConfig metadata to tasks |
| `parallel-plan [--missing-only]` | Emit per-task research packets for parallel subagents |
| `parallel-apply --input <results.json>` | Merge parallel research results atomically |
| `parallel-extract --output <path>` / `parallel-inject --input <path>` | Tagged ⇄ flat tasks bridge |

## Parallel Research & Complexity

**Decision tree for expansion + research** (token-economy aware):

```
Manual flag                        → Native Mode (unchanged)
pending tasks ≤ 3                  → serial NATIVE: analyze-complexity --research, then expand per task (main dir)
task-master ≥ 0.43 AND research
  role is a REAL structured API    → NATIVE-PARALLEL (DEFAULT): script.py tm-parallel
  (sonar/anthropic/openai… key)      one serial analyze-complexity, then N isolated workdirs each running
                                     native `expand --id N --research` with an economy-tier model; ONE
                                     atomic harvest merge. Failed packets → agent-parallel rerun.
free local proxy / no API key /
  TM provider errors / TM < 0.43   → AGENT-PARALLEL (fallback): parallel-plan → N subagents → parallel-apply
```

Why isolation dirs: task-master 0.43+ uses proper-lockfile + atomic writes, but its 10s lock-stale
window vs 30–120s AI calls makes concurrent invocations in ONE directory unsafe — N isolated
project dirs sidestep the lock entirely and double as the per-attempt model mechanism (expand has
no --model flag; each workdir carries its own config.json). The free local Perplexity proxy returns
prose where TaskMaster needs strict JSON — that is why the proxy keeps the agent-normalized path
while real APIs get the native path.

Pattern — the parallelism lives in the AGENT, not the script:

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py parallel-plan --missing-only   # research packets JSON
# AGENT: split packets into N groups (by lane/domain), spawn N parallel research
#   subagents; each verifies files in-repo + researches APIs and returns
#   [{id, complexityScore, recommendedSubtasks, reasoning, researchNotes, subtasks[]}]
# AGENT: concatenate results -> results.json
python3 ~/.claude/skills/prd-taskmaster/script.py parallel-apply --input results.json   # ONE atomic write
#   + writes .taskmaster/reports/task-complexity-report[_<tag>].json (TaskMaster format)
#   + returns needs_more_subtasks (score >= threshold w/ too-few subtasks) for a second pass
```

If the `perplexity-api-free` MCP wrapper times out or says the proxy is unreachable, check direct
proxy health:

```bash
curl -sS -X POST http://127.0.0.1:8765/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"sonar","messages":[{"role":"user","content":"Return exactly: ok"}],"max_tokens":16}'
```

If direct `curl` works, continue: use MCP, direct proxy calls, or agent research to produce the
`results.json` schema, then normalize prose into valid JSON before `parallel-apply`. Do not block on
native `task-master analyze-complexity --research`.

Tag bridge for explicit flat-file workflows (the script also reads tagged TaskMaster files directly):

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py parallel-extract --output /tmp/flat.json
python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks --input /tmp/flat.json
python3 ~/.claude/skills/prd-taskmaster/script.py enrich-tasks  --input /tmp/flat.json
python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks --input /tmp/flat.json --require-phase-config
python3 ~/.claude/skills/prd-taskmaster/script.py parallel-inject --input /tmp/flat.json
```

All commands default `--tag` to `.taskmaster/state.json` currentTag and run from the project root.

## Context

**Standalone:** Works on its own. Takes any goal, produces spec + tasks.
**Produces:** spec.md + tasks.json (in `.taskmaster/`).
**Then:** hand off to an execution mode (Verified Loop / Auto-Execute / Plan & Drive), or
**Atlas Fleet** for parallel multi-session execution with Atlas Pro.

## Critical Rules

1. Zero setup questions — detect everything, ask only discovery questions
2. Discovery via superpowers:brainstorming — one question at a time, adaptive
3. Domain-agnostic — works for any goal (app, pentest, business, anything)
4. Validate PRDs catch placeholders — mustache, TBD, TODO patterns fail validation
5. Manual flag means "do the TaskMaster mechanics manually", not "skip validation"
6. Handoff recommends ONE mode — present best fit, not equal choices
7. Phase files must be Read explicitly — they are not auto-loaded
8. Native/free provider defaults are enforced by `configure-providers`; do not drift back to paid Anthropic/Perplexity APIs unless native/free routes are unavailable
9. Perplexity API Free research must be normalized through `parallel-apply`; native TaskMaster research is only acceptable when it returns valid structured output and validation passes
