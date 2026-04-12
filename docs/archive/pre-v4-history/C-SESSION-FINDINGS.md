# Session Findings: prd-taskmaster v4 Brainstorm

**Date:** 2026-04-08
**Session:** claude-ags-prd-taskmaster-v2

## Key Decision: Scope Split

prd-taskmaster stays focused on PRD generation + task parsing. The execution pipeline (CDD, ralph-loop, doubt, visual testing, workers) is a SEPARATE product layer (Atlas-Auto / Atlas-OS).

**prd-taskmaster = generate the spec + tasks. That's it.**
**Atlas-Auto = execute the tasks autonomously. Separate product.**

## What Was Done This Session

1. **v4-spec.md written** — 1,091 lines, 20 sections + 4 appendices at `docs/v4-spec.md`
2. **GitHub Issues created:**
   - anombyte93/dotfiles#2 — Gemini Flash summarization gate for handoff files
   - anombyte93/dotfiles#3 — Universal Gemini condenser hook for PreToolUse:Read
3. **Gemini-condenser session spawned** — hook built, tested, working (315 lines)
4. **atlas-mcp-rebuild session** — `session_spawn` + `session_spawn_list` tools added to atlas-session-mcp (25 tools, 1,585 lines, pushed to GitHub)
5. **Atlas-OS discovered** — already has task_manager.py, prd_importer.py, phase_engine.py, worker_manager.py, cdd.py. Replaces TaskMaster dependency for premium tier.

## Architecture Decisions (from brainstorm)

### Dual-Tier Model
- **Free tier**: prd-taskmaster + TaskMaster (npm) — improved, zero-config
- **Premium tier**: Atlas-OS (Python, our code) — no TaskMaster dependency

### prd-taskmaster v4 Improvements (for /skill-forge)
1. **Zero-config**: auto-detect TaskMaster, providers, capabilities. Zero questions on first run.
2. **Anti-wizard**: no setup questions. Start discovery immediately.
3. **Progressive discovery**: fork brainstorming philosophy (one Q at a time, adaptive, domain-agnostic)
4. **Domain-agnostic**: works for any goal (pentest, app, business, anything)
5. **Split into phases**: SKILL.md router + DISCOVER.md + GENERATE.md + HANDOFF.md
6. **4 execution modes**: A (superpowers), B (TaskMaster native), C (manual), D (Atlas-Auto premium)
7. **Plugin format**: marketplace.json + install.sh dual distribution
8. **Validation upgrade**: AI semantic validation + placeholder detection (not just regex)

### Mode D (Atlas-Auto) Pipeline — THE product
```
PRD → /cdd cards → /ralph-loop → /question research → superpowers:subagent-driven-dev →
/cdd GREEN verify → 3x doubt + finality → /atlas-user-test visual gate → OUTPUT
```

### What prd-taskmaster Should NOT Do
- Execute tasks (that's superpowers/Atlas-Auto)
- Manage sessions/fleet (that's atlas-session-mcp)  
- Visual testing (that's /atlas-user-test)
- CDD cards (that's /cdd)
- It generates the spec and tasks, then HANDS OFF to one of the 4 modes

## Research Findings (/question x10)

### Must Fix in Skill Forge
1. **Phase files need explicit Read** — SKILL.md must `Read phases/DISCOVER.md` etc.
2. **Present 1 recommended mode** — not 4 equal choices (choice paralysis)
3. **Zero-config needs confidence levels** — report ambiguity, ask when unsure
4. **CDD cards at execution time** — not pre-generated during PRD (they go stale)

### Validated (keep as-is)
- Domain-agnostic templates (core skeleton + AI fills domain context)
- Commons Clause safe (free tier is integration, premium is independent)
- One-at-a-time progressive questions (UX research supports this)
- Plugin + install.sh dual distribution

## 20-Item Audit (from parent session)

See PARENT-CONTEXT-DUMP.md section "20-ITEM AUDIT FINDINGS" for full list. Key ones for skill-forge:
1. Validation passes on template placeholders → ADD placeholder detection
2. 12-question discovery wall → REDUCE to progressive, adaptive
3. TDD mandate unrealistic → MAKE optional
4. MCP detection wrong paths → FIX
5. Template 2FA bias → MAKE domain-agnostic
6. expand-tasks requires local proxy → FIX to use Perplexity MCP

## Competitor/Market Context

- **Traffic**: 220 unique cloners/14d, 1013 visitors, stars 9→54/month accelerating
- **ChatGPT referring users**: 64 views from chatgpt.com
- **Devin**: $10.2B val, $500/mo. We're $29/mo with proof.
- **Key differentiator**: code + PROOF it works (CDD + doubt + visual testing)

## Files in This Project

- `docs/v4-spec.md` — complete product spec (1,091 lines)
- `docs/DEBRIEF-v4-spec-session.md` — parent session debrief
- `docs/PARENT-CONTEXT-DUMP.md` — full parent research context
- `docs/SESSION-FINDINGS.md` — THIS FILE
- `.claude/handoff-prompt.md` — original handoff from parent
- `.claude/handoff-chain.json` — lineage tracking

## What Needs To Happen Next

1. **Run /skill-forge on prd-taskmaster** — upgrade the skill using these findings
2. Focus on: zero-config, progressive discovery, domain-agnostic, phase split, validation upgrade
3. The execution pipeline (Mode D) is a SEPARATE workstream — don't bolt it onto prd-taskmaster
4. Atlas-OS is the premium backend — continues as its own project
