# prd-taskmaster-v2 Architecture Diagram

## Proven Execution Flow (from dogfood runs + 226 passing tests)

```
USER TRIGGER
"I want to build X" / "PRD" / /prd-taskmaster-v2
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SKILL.md (Index)                            │
│  Thin orchestrator — gates between phases, tells AI when to Read    │
│  phase files. No I/O, no calculations. ~150 lines.                  │
│                                                                     │
│  Tool preference: MCP first (mcp__prd-taskmaster__*) → CLI fallback │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 0: SETUP                    phases/SETUP.md               │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │ which     │───▶│ task-master  │───▶│ task-master  │            │
│  │task-master│    │ init --yes   │    │ models       │            │
│  │  -ai      │    │ (if needed)  │    │ (detect      │            │
│  └──────────┘    └──────────────┘    │  first, set  │            │
│       │                              │  only if     │            │
│       │ not found → BLOCK            │  empty)      │            │
│       │                              └──────┬───────┘            │
│       │                                     │                    │
│       │         ┌───────────────────────────▼──────────┐         │
│       │         │ Probe test: expand_task on task 1    │         │
│       │         │ (verify AI pipeline works)           │         │
│       │         └─────────────────────────────────────-┘         │
│                                                                  │
│  One-shot: script.py validate-setup (6 checks, per-failure fix)  │
│  Gate: ready=true, 0 critical failures                           │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: PREFLIGHT                script.py preflight           │
│  (Zero questions — detect everything)                            │
│                                                                  │
│  Returns JSON:                                                   │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ prd_path, task_count, taskmaster_method,            │         │
│  │ has_crash_state, recommended_action                 │         │
│  │                                                     │         │
│  │ recommended_action ∈ {                              │         │
│  │   recover,       ← crash state found               │         │
│  │   run_setup,     ← no taskmaster                    │         │
│  │   generate_prd,  ← taskmaster but no PRD            │         │
│  │   parse_prd,     ← PRD exists, 0 tasks             │         │
│  │   resume,        ← PRD + tasks, some pending        │         │
│  │   complete        ← all tasks done                  │         │
│  │ }                                                   │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                  │
│  Decision routing:                                               │
│  ┌──────────────────┬───────────────────────────────────┐        │
│  │ prd + tasks > 0  │ ask: execute / update / new / rev │        │
│  │ prd + tasks == 0 │ ask: parse / replace / review     │        │
│  │ no taskmaster    │ → back to Phase 0                 │        │
│  │ taskmaster, no   │ → proceed to Discovery            │        │
│  │ PRD              │                                   │        │
│  │ crash state      │ → offer resume or start fresh     │        │
│  └──────────────────┴───────────────────────────────────┘        │
│                                                                  │
│  Gate: TaskMaster detected and environment ready                 │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: DISCOVER                 phases/DISCOVER.md            │
│  (Adaptive brainstorming — domain-agnostic)                      │
│                                                                  │
│  TWO MODES:                                                      │
│                                                                  │
│  Interactive (default):                                          │
│  ┌──────────────────────────────────────────────┐                │
│  │ Invoke superpowers:brainstorming with goal    │                │
│  │    ↓                                          │                │
│  │ Adaptive Q&A (one Q at a time)                │                │
│  │    ↓                                          │                │
│  │ INTERCEPT: capture output BEFORE it chains    │                │
│  │           to writing-plans                    │                │
│  │    ↓                                          │                │
│  │ Extract constraints (MANDATORY):              │                │
│  │   tech stack, timeline, team, budget,         │                │
│  │   integration, regulatory, domain-specific    │                │
│  │    ↓                                          │                │
│  │ Classify scale: Solo(8-12) / Team(12-20) /    │                │
│  │                  Enterprise(20-30) tasks       │                │
│  │    ↓                                          │                │
│  │ User approval gate                            │                │
│  └──────────────────────────────────────────────┘                │
│                                                                  │
│  Autonomous (ralph-loop / auto-approve):                         │
│  ┌──────────────────────────────────────────────┐                │
│  │ Read goal from args / soul-purpose.md         │                │
│  │    ↓                                          │                │
│  │ Self-brainstorm: answer all discovery Qs      │                │
│  │    ↓                                          │                │
│  │ Self-approve, document assumptions explicitly │                │
│  │    ↓                                          │                │
│  │ Write discovery-{ts}.md as audit trail        │                │
│  └──────────────────────────────────────────────┘                │
│                                                                  │
│  Gate: Discovery approved, constraints extracted, scale set      │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: GENERATE & VALIDATE      phases/GENERATE.md            │
│                                                                  │
│  Step 1: Load template                                           │
│  ┌─────────────────────────────────────────┐                     │
│  │ script.py load-template --type X        │                     │
│  │   comprehensive (4+ answers, complex)   │                     │
│  │   minimal (quick project)               │                     │
│  │                                         │                     │
│  │ templates/taskmaster-prd-comprehensive   │                     │
│  │ templates/taskmaster-prd-minimal         │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  Step 2: AI fills template → .taskmaster/docs/prd.md             │
│  (replace ALL placeholders, domain-neutral vocab for non-SW)     │
│                                                                  │
│  Step 3: Validate                                                │
│  ┌─────────────────────────────────────────┐                     │
│  │ script.py validate-prd --input prd.md   │                     │
│  │                                         │                     │
│  │ 13 deterministic checks:                │                     │
│  │  - word count, section presence,        │                     │
│  │    placeholder detection ({{}} TBD TODO)│                     │
│  │  - vague-word detection,                │                     │
│  │    requirement count, scope section     │                     │
│  │  - deferred decisions (reason: OK)      │                     │
│  │                                         │                     │
│  │ Grades: EXCELLENT(91%+) GOOD(83-90%)    │                     │
│  │         ACCEPTABLE(75-82%) NEEDS_WORK   │                     │
│  │                                         │                     │
│  │ Optional: --ai for LLM holistic review  │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  Step 4: Parse tasks via TaskMaster                              │
│  ┌─────────────────────────────────────────┐                     │
│  │ calc-tasks → recommended count          │                     │
│  │ task-master parse-prd → tasks.json      │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  Step 5: analyze-complexity                                      │
│  ┌─────────────────────────────────────────┐                     │
│  │ task-master analyze-complexity           │                     │
│  │ → .taskmaster/reports/task-complexity-   │                     │
│  │   report.json                           │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  Step 6: Expand tasks (MANDATORY, serial)                        │
│  ┌─────────────────────────────────────────┐                     │
│  │ task-master expand --all [--research]    │                     │
│  │                                         │                     │
│  │ NEVER parallel per-id calls (race on    │                     │
│  │ tasks.json read-modify-write — data     │                     │
│  │ loss confirmed in v4 dogfood)           │                     │
│  │                                         │                     │
│  │ Verify via direct tasks.json read       │                     │
│  │ (NOT task-master list — schema differs) │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                  │
│  Gate: GOOD+ grade AND tasks parsed AND complexity analyzed      │
│        AND all tasks have subtasks                               │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: HANDOFF                  phases/HANDOFF.md             │
│  (Detect capabilities → recommend ONE mode → hand off)           │
│                                                                  │
│  Step 1: Detect capabilities                                     │
│  ┌──────────────────────────────────────────┐                    │
│  │ script.py detect-capabilities            │                    │
│  │ Returns: tier (free|premium), per-cap    │                    │
│  │ flags for superpowers, taskmaster,       │                    │
│  │ ralph-loop, atlas-loop, playwright, etc. │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  Step 2: Recommend ONE mode (first-match):                       │
│  ┌──────────────────────────────────────────┐                    │
│  │ superpowers + ralph-loop → Mode C        │                    │
│  │ superpowers only        → Mode A         │                    │
│  │ taskmaster-only         → Mode B         │                    │
│  │ fallback                → Mode A         │                    │
│  │                                          │                    │
│  │ Mode D (Atlas-Auto) = always coming-soon │                    │
│  │ Modes E-J = external tools (Cursor,      │                    │
│  │   Roo, Codex, Gemini, CodeRabbit, Aider) │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  Step 3: Append workflow to CLAUDE.md                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ script.py append-workflow --target X     │                    │
│  │   --content-file Y [--dry-run]          │                    │
│  │                                          │                    │
│  │ Idempotent (HTML-comment sentinels),     │                    │
│  │ timestamped backup, JSON response:       │                    │
│  │   action ∈ {created, appended, skipped}  │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  Step 5: MANDATORY dual-tool-call gate                           │
│  ┌──────────────────────────────────────────┐                    │
│  │ EnterPlanMode (durable handoff record)   │                    │
│  │        +                                 │                    │
│  │ AskUserQuestion (structured mode picker) │                    │
│  │                                          │                    │
│  │ Hook-blocked fallback: prose option      │                    │
│  │ table + [AI] insight block for           │                    │
│  │ orchestrator detection                   │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  Step 6: Auto-scaffold dogfood debrief                           │
│  ┌──────────────────────────────────────────┐                    │
│  │ script.py debrief --slug X --grade Y     │                    │
│  │   --output-dir docs/v4-release || true   │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  On ExitPlanMode approval, dispatch:                             │
│  ┌──────────────────────────────────────────┐                    │
│  │ Mode A → superpowers:writing-plans       │                    │
│  │ Mode B → task-master next + first task   │                    │
│  │ Mode C → write ralph-loop-prompt.md,     │                    │
│  │          invoke /ralph-loop:ralph-loop   │                    │
│  │ Mode D → waitlist response only          │                    │
│  └──────────────────────────────────────────┘                    │
│                                                                  │
│  Gate: User chose mode, CLAUDE.md updated, handoff delivered,    │
│        debrief scaffolded.                                       │
└──────────────────────────────────────────────────────────────────┘


## The Codification Pattern (what goes where)

┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│   SKILL.md                phases/*.md              script.py       │
│   ─────────               ──────────               ─────────       │
│   AI judgment             Procedural recipes       Deterministic   │
│   Phase gates             Decision trees           JSON on stdout  │
│   When to ask             Prompt templates          15 subcommands │
│   What = "ready"          Tool-call sequences      No AI judgment  │
│   ~150 lines              Read explicitly           ~2000 lines    │
│                           NOT auto-loaded                          │
│                                                                    │
│   "Should we?"            "How to do it"           "Do it + prove" │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘


## Distribution & Integration

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  install.sh (curl|bash)         uninstall.sh                    │
│  ────────────────────           ──────────────                  │
│  Clones to                      Removes                        │
│  ~/.claude/skills/              ~/.claude/skills/               │
│    prd-taskmaster-v2/             prd-taskmaster-v2/            │
│                                                                 │
│  Ships: SKILL.md, script.py,    Leaves .taskmaster/ alone       │
│         phases/, templates/,    Prunes updates.json entry       │
│         reference/                                              │
│                                                                 │
│  MCP Server (optional,          Companion Skills:               │
│  separate registration):        ───────────────────             │
│  ┌─────────────────────┐        expand-tasks/                   │
│  │ mcp_server/server.py│          Parallel research per task    │
│  │ FastMCP wraps        │        customise-workflow/             │
│  │ script.py subcommands│          User preference Q&A          │
│  │ as mcp__prd-         │          → .taskmaster/config/        │
│  │ taskmaster__* tools  │            user-workflow.json          │
│  └─────────────────────┘                                        │
│                                                                 │
│  Works with TaskMaster (MCP or CLI):                            │
│  mcp__task-master-ai__* tools / task-master CLI                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘


## What it produces (per project)

    .taskmaster/
    ├── docs/
    │   └── prd.md                    ← Validated spec (13 checks)
    ├── tasks/
    │   └── tasks.json                ← Parsed tasks with subtasks
    ├── reports/
    │   └── task-complexity-report.json
    ├── config/
    │   └── user-workflow.json        ← User preferences (optional)
    └── state/                        ← Crash recovery state


## Pipeline position

    ┌────────────┐     ┌───────────────────┐     ┌────────────┐
    │atlas-start │────▶│ prd-taskmaster-v2 │────▶│ atlas-plan │
    └────────────┘     └───────────────────┘     └─────┬──────┘
                                                       │
                                                       ▼
                       ┌───────────────────┐     ┌────────────┐
                       │   atlas-sync      │◀────│ atlas-loop │
                       └───────────────────┘     └────────────┘

    Also works standalone: any goal → prd.md + tasks.json
```
