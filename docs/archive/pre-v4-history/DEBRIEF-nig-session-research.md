# Debrief: NIG Session → prd-taskmaster-v2 Overhaul Research

**Parent session**: claude-ags-MeshLAN (nig.atlas-ai.au project)
**Date**: 2026-04-11
**Handoff reason**: Session discovered prd-taskmaster-v2 live skill is stale; real overhaul repo needs the research findings applied

## What Was Done

### 1. NIG Project PRD Generated
- Created comprehensive PRD at `.taskmaster/docs/prd.md` (96.5% EXCELLENT)
- 22 tasks with 98 subtasks in `.taskmaster/tasks/tasks.json`
- Phase 1 (validate Tailscale client connection) is the hard gate
- Plan lives at `~/.claude-accounts/hayden/plans/glittery-waddling-axolotl.md`

### 2. TaskMaster Native Capabilities Discovered
**TaskMaster v0.43.1 already provides:**
- `task-master init` — creates .taskmaster/ structure
- `task-master models` — shows config + API key status table
- `task-master models --setup` — interactive model selection UI
- `task-master models --set-main <model> --claude-code` — zero-API-key provider
- `parse_prd` MCP tool — AI-powered PRD to tasks (with Handlebars-templated prompts)
- `expand_task` MCP tool — AI-powered task expansion into subtasks
- `analyze-complexity` — AI-powered complexity scoring (1-10) with subtask recommendations
- Supports 17+ providers including `claude-code` (no API key needed)

### 3. All TaskMaster Prompts Extracted
Found in `/usr/lib/node_modules/task-master-ai/dist/dependency-manager-BJq6jWA5.js`:
- ADD-TASK system prompt (line ~251)
- ANALYZE-COMPLEXITY system prompt (line ~311)
- EXPAND-TASK system prompts (3 variants: complexity-report, research, default)
- PARSE-PRD system prompt (line ~525, with {{#if research}} Handlebars conditionals)
- RESEARCH system prompt (line ~575, with detail levels low/medium/high)
- UPDATE-SUBTASK system prompt (line ~619)
- UPDATE-TASK system prompt (line ~678)
- UPDATE-TASKS system prompt (line ~953)
All use Vercel AI SDK's generateText()/generateObject() with Handlebars templating.

### 4. prd-taskmaster-v2 Redundancies Identified

| Our Function | TaskMaster Native | Verdict |
|-------------|-------------------|---------|
| `enrich-tasks` (regex) | `analyze-complexity` (AI) | DELETE — TM's is better |
| `_ai_classify_tasks` (claude --print) | `analyze-complexity` (AI) | DELETE — redundant |
| `_get_ai_model_config` | TM reads config internally | DELETE |
| `detect-providers` | `task-master models` | DELETE — TM shows this |
| Manual .env management | TM reads .env natively | DELETE |

### 5. What Our Skill SHOULD Own (Genuine Value)
- Phase 0: SETUP gate (task-master init + models --setup + probe test)
- Phase 1: Discovery via brainstorming (TM has NO discovery/elicitation)
- PRD template loading + validation (quality gate before parse-prd)
- calc-tasks heuristic
- Handoff mode selection (detecting ralph-loop, CDD, etc.)

### 6. {REDACTED: private research MCP architecture notes}
Notes about a private research-provider MCP server architecture were here.
This content has been redacted because it describes internal Atlas infrastructure
that is not part of the public v4 release. v4's research pipeline is
provider-agnostic — see `README.md` and `phases/SETUP.md` for the supported
configuration paths.

### 7. TaskMaster Research Provider Architecture
- Uses Vercel AI SDK (`ai` v5.0.51) with `@ai-sdk/perplexity`
- Calls `generateText()` / `generateObject()` against configured research model
- Config: `.taskmaster/config.json` → `models.research.provider` + `modelId`
- Perplexity baseURL is overridable (hook for local proxy)
- Graceful degradation: local proxy → official API → Anthropic fallback

### 8. /wtf Diagnostic Findings
- 13+ copies of prd-taskmaster scattered across filesystem
- Live skill at `~/.claude/skills/prd-taskmaster-v2/` is the OLD stripped version
- Real overhaul at `~/Shade_Gen/Projects/prd-taskmaster-v2/` (v4 spec, 200 tests)
- Chezmoi only tracks script.py — SKILL.md, phases/, templates/, plugin.json are UNMANAGED
- The overhaul was never deployed to the live skill location

## What the Child Session Should Do

### Priority 1: Apply Research to Overhaul
1. Read the v4-spec.md (already in the overhaul repo)
2. Add Phase 0: SETUP.md — mandatory setup gate using `task-master init` + `task-master models`
3. Remove redundant functions from script.py (enrich-tasks, _ai_classify_tasks, detect-providers)
4. Wire analyze-complexity from TaskMaster instead of custom enrichment
5. Update config to default to `claude-code` provider (zero API key)

### Priority 2: perplexity_taskmaster Bridge Tool
1. Add `perplexity_taskmaster` tool to `~/.claude/mcp-servers/perplexity-mcp/index.js`
2. Accepts research queries in TaskMaster's expected format
3. Returns formatted research results
4. Single entry point: install MCP + API key → everything works

### Priority 3: Deploy Overhaul to Live Skill
1. Copy overhaul files to `~/.claude/skills/prd-taskmaster-v2/`
2. Add ALL files to chezmoi (not just script.py)
3. Test with `chezmoi diff` then `chezmoi apply`
4. Verify skill loads in Claude Code

### Priority 4: Return to NIG Project
1. Use the fixed prd-taskmaster-v2 to re-run task generation for NIG
2. Execute Phase 1: validate Tailscale client connection
3. Continue through the plan at glittery-waddling-axolotl.md

## Key Files Reference

| File | Location | Purpose |
|------|----------|---------|
| v4 spec | ~/Shade_Gen/Projects/prd-taskmaster-v2/docs/v4-spec.md | The vision document |
| Overhaul SKILL.md | ~/Shade_Gen/Projects/prd-taskmaster-v2/SKILL.md | v3 skill (needs v4 update) |
| Overhaul script.py | ~/Shade_Gen/Projects/prd-taskmaster-v2/script.py | 1089 lines, 200 tests |
| Live skill | ~/.claude/skills/prd-taskmaster-v2/ | OLD version to replace |
| Chezmoi source | ~/.local/share/chezmoi/private_dot_claude/skills/prd-taskmaster-v2/ | Only tracks script.py |
| perplexity MCP | ~/.claude/mcp-servers/perplexity-mcp/index.js | 232 lines, add tool here |
| NIG plan | ~/.claude-accounts/hayden/plans/glittery-waddling-axolotl.md | MeshLAN next phases |
| NIG project | ~/Shade_Gen/Projects/nig.atlas-ai.au/ | Current project |
| TM prompts | /usr/lib/node_modules/task-master-ai/dist/dependency-manager-BJq6jWA5.js | All TaskMaster prompts |
