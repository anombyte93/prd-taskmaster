# prd-taskmaster-v3 — Final Consolidated Spec

**Date:** 2026-04-09
**Status:** Approved by user, ready for implementation

## What It Is

A Claude Code plugin that takes any goal and turns it into a working result. Uses TaskMaster as source of truth, /brainstorming for discovery, /writing-plans for planning, and ralph-loop for execution.

## The 3 Pillars

```
/start              = Entry point (where am I? what's next?)
prd-taskmaster-v3   = Engine (brainstorm → spec → tasks)
TaskMaster          = Source of truth (tasks.json via MCP)
```

## User Flow

```
User: /start
    │
    ├── Check TaskMaster (get_tasks)
    │   ├── No .taskmaster/ → "Fresh project. What do you want to achieve?"
    │   │                      → invoke prd-taskmaster-v3
    │   ├── Tasks pending   → "Resuming. N/M tasks done. Next: [task]."
    │   │                      → jump to execution mode
    │   └── All done        → "Complete. New goal?"
    │
    └── Set up session context files + TodoWrite
```

## prd-taskmaster-v3 (The Engine)

```
User: /prd-taskmaster-v3 "I want to achieve X"
    │
    ├── AUTO-DETECT (silent, zero questions)
    │   ├── TaskMaster installed? (MCP or CLI)
    │   ├── Playwright available? (for verification)
    │   ├── Research provider? (WebSearch / user's choice)
    │   └── Auto-configure providers
    │
    ├── DISCOVER
    │   └── Invoke /brainstorming (superpowers plugin)
    │       → One question at a time, adaptive, domain-agnostic
    │       → Intercept before it chains to writing-plans
    │       → User approves the design
    │
    ├── GENERATE
    │   ├── Write spec from brainstorm output
    │   ├── Validate (regex + placeholder detection via script.py)
    │   ├── TaskMaster parse_prd → tasks.json
    │   └── Enrich tasks with metadata (update_task)
    │
    └── HANDOFF — "How do you want to execute?"
        │
        ├── A) Plan only (manual execution)
        │   → Invoke /writing-plans
        │   → Plan references TaskMaster task IDs
        │   → Show commands, user drives
        │   → DONE
        │
        ├── B) TaskMaster auto-execute
        │   → autopilot_start → autopilot_next → loop
        │   → DONE
        │
        ├── C) Plan + Ralph Loop (recommended FREE)
        │   → /writing-plans creates plan
        │   → Ralph-loop wraps execution:
        │     Each iteration:
        │       next_task → set_task_status("in_progress")
        │       → /writing-plans for this task's steps
        │       → superpowers:subagent-driven-development executes
        │         → fresh subagent implements
        │         → spec reviewer checks
        │         → quality reviewer checks
        │       → set_task_status("done")
        │       → update TodoWrite
        │       → repeat
        │   → Research via WebSearch (or user's provider)
        │
        └── D) ★ Atlas Loop (PREMIUM)
            → Same as C but:
            → atlas-loop (not ralph-loop)
            → atlas-cdd cards per task (evidence hierarchy)
            → Tier S browser verification (Playwright)
            → /question deep research per task
            → /stepback on 2 failures
            → /research-before-coding before implementation
            → atlas-gamify scoring (promise-based, verification multipliers)
            → Insight publishing (extract + Discord + RAG)
            → Walk away, come back to proof
```

## Skills Inventory

### Ships With Plugin (Free)

| Skill | Purpose |
|-------|---------|
| `atlas-start` (/start) | Entry point — check TaskMaster, route to engine or resume |
| `prd-taskmaster-v3` | Engine — brainstorm → spec → tasks → handoff |
| `atlas-plan` | Step-by-step plan from tasks |
| `atlas-sync` | Save session context files |

### Uses From Superpowers Plugin (Free, already installed)

| Skill | Where Used |
|-------|-----------|
| `superpowers:brainstorming` | DISCOVER phase of prd-taskmaster-v3 |
| `superpowers:writing-plans` | Mode A plan + Mode C per-task planning |
| `superpowers:subagent-driven-development` | Mode C task execution inside ralph-loop |

### Premium (Atlas Infra subscription)

| Skill | Purpose |
|-------|---------|
| `atlas-loop` | Walk-away execution with gamified scoring |
| `atlas-cdd` | Acceptance cards with evidence hierarchy (S/A/B/C/D tiers) |
| `atlas-go` | Fresh subagent executor with two-stage review |
| `atlas-user-test` | Visual browser verification |
| `/question` | Deep Perplexity research pipeline |
| `/stepback` | Forced architectural reassessment |
| `/research-before-coding` | Full research pipeline |
| **Insight publishing** | Auto-extract learnings, push to Discord, consolidate to RAG |

### Design References (not invoked directly)

| Skill | Purpose |
|-------|---------|
| `atlas-gamify` | Scoring system design — read by atlas-loop for prompt generation |

### External Dependencies

| Dependency | Required? | Notes |
|---|---|---|
| Claude Code | Yes | The runtime |
| TaskMaster (`task-master-ai` npm) | Yes | Source of truth |
| Ralph Loop plugin | Yes (Mode C) | Free execution loop |
| Playwright MCP | Recommended | Tier S verification. Caps at Tier A without it. |
| Research provider | Optional | WebSearch default, user can configure |

## TaskMaster Integration

### MCP Tools Used

```
parse_prd         → PRD → tasks.json (one-time in GENERATE)
next_task          → dependency-ready next task (each iteration)
set_task_status    → mark in_progress / done (each task)
get_tasks          → view current state (on /start, as needed)
update_task        → add metadata to tasks (enrichment)
get_task           → single task details (for plan reference)
expand_task        → break complex tasks mid-execution
```

### Rules

- **TaskMaster = source of truth for task state**
- **TodoWrite = user visibility for progress**
- **Always use MCP tools, never edit tasks.json directly**
- **Project CLAUDE.md gets pipeline instructions appended** during HANDOFF

### CLAUDE.md Section (generated by HANDOFF)

```markdown
## Task Execution Workflow (prd-taskmaster-v3)

When implementing tasks, use TaskMaster MCP tools in this order:
1. `next_task` — get the next dependency-ready task
2. `set_task_status(task_id, "in_progress")` — mark started
3. Implement the task (follow the plan step linked to this task)
4. `set_task_status(task_id, "done")` — mark complete
5. Update TodoWrite with progress
6. Repeat from step 1

### Progress Tracking
- Update TodoWrite BEFORE and AFTER each task
- Cannot proceed to next task without updating TodoWrite
- TodoWrite = what the user sees. TaskMaster = source of truth.

### Installed Capabilities
[auto-detected at setup time]
✅ TaskMaster (MCP/CLI)
✅/○ Playwright (browser verification)
✅/○ Research provider (WebSearch / Perplexity / other)
```

## Progress Gates (TodoWrite)

Every skill MUST:
1. Initialize TodoWrite with task list before starting work
2. Mark current task `in_progress` before doing it
3. Mark task `completed` after finishing
4. **Cannot proceed to next task without updating TodoWrite**

## What We're NOT Building (Yet)

- Web dashboard (TodoWrite simulates this)
- Atlas-OS integration (premium, separate project)
- MOLL-E Discord bot (premium, separate project)
- Deployment automation (future)
- Cross-task context sharing (future — tasks are independent for now)

## Files in This Project

- `docs/FINAL-SPEC-v2.md` — THIS FILE
- `docs/v4-spec.md` — Full product spec (1,091 lines, market context)
- `docs/PARENT-CONTEXT-DUMP.md` — Original research from parent session
- `docs/SESSION-FINDINGS.md` — Brainstorm findings
- `docs/RESEARCH-writing-plans.md` — Writing-plans audit
- `docs/RESEARCH-cdd-subagent-sync.md` — CDD + subagent + sync audits
- `CLAUDE.md` — Project instructions (20 decisions)
- `session-context/` — Session state files
