# @atlas-ai/prd-taskmaster — Plugin Design Spec

**Date**: 2026-04-16
**Author**: Hayden + Claude
**Status**: Design approved, pending implementation plan
**Approach**: Plugin-native rebuild (Approach 2)
**Package**: `@atlas-ai/prd-taskmaster` on npm

---

## 0. The Single Question This Plugin Answers

> **"How do I know what I built is what I actually wanted?"**

Every mechanism in this design traces back to this one question. AI-assisted development makes it terrifyingly easy to build exactly the wrong thing very efficiently. This plugin is the mechanism for closing the gap between intent and artifact.

Map from mechanism to the question:
- Discovery asks **"what do I actually want?"**
- Spec validation asks **"did I write down what I want?"**
- Task decomposition asks **"do these pieces add up to what I want?"**
- CDD evidence asks **"did each piece do what it claimed?"**
- Triage matrix asks **"is the thing I tested actually the thing I wanted?"**
- Ship-check.py asks **"has it truly satisfied the want?"**
- Triple verification asks **"am I sure it's done, or just convinced?"**

Every feature gets evaluated against this question: does it SERVE the question or DILUTE it? Features that serve stay. Features that dilute get cut.

### The Jobs Lens (surface problems → propose fixes, never demolish)

The Jobs Lens is a **diagnostic and repair mechanism**. It surfaces features that drift from the Core Question — then the AI's job is to figure out HOW TO FIX the drift, not to cut the feature. Deletion is never the first response. It's the last, only after fix attempts have been surfaced and explicitly approved by the human.

How the Jobs Lens works at audit time:

1. **Classify each feature** — label only:
   - **Serves-core** — aligns with the Core Question. Keep as-is. No action.
   - **Serves-but-clumsy** — aligns with core, implementation is rough. The AI's job: surface WHY it's clumsy + propose fixes. "This works but it's not RIGHT yet" — Jobs polished these, not deleted them.
   - **Drifts-from-core** — the feature feels disconnected from the Core Question. The AI's job: diagnose WHY it drifts + propose reframings so it serves the core.

2. **The AI's job after classification is to PROPOSE FIXES, not to cut:**
   - For Serves-but-clumsy: "The implementation is clumsy because X. Proposed fixes: (a) refactor to Y, (b) merge with Z, (c) simplify the interface by W."
   - For Drifts-from-core: "This drifts because it answers a different question. Proposed reframings: (a) restructure it so it DOES serve the Core Question by doing Z, (b) narrow its scope so it complements rather than dilutes, (c) make it opt-in rather than default so it doesn't crowd the core path."

3. **Output format — always fixes, not cuts:**
   ```
   - Feature X — SERVES (no action)
   - Feature Y — SERVES-BUT-CLUMSY — Why clumsy: <reason>. Proposed fixes: <3 options>
   - Feature Z — DRIFTS — Why drifts: <reason>. Proposed reframings: <3 options that pull it back to core>
   ```

4. **Human decides.** The AI surfaces the drift + proposed repairs. The human chooses which fix to apply, OR decides the feature needs to go. Deletion is never the AI's default; repair is.

5. **The Jobs Detail**: the ONE thing users will never articulate but will feel. The click of the button. The weight of the device. For this plugin: the moment a task shows `done` and the user can SEE the evidence file it produced — not just trust a claim. That's the plugin's Jobs Detail. Every audit should ask: is the Jobs Detail still crisp, or have we added noise around it? If noise: the AI proposes how to restore crispness, not what to delete.

**Rule for AI agents consuming this spec:** When the lens surfaces a problem, think: "OK I understand — now how do I FIX it?" not "let me cut it." Deletion is always last resort and always requires human sign-off. Jobs didn't slash — he obsessed over what wasn't right until it was.

---

## 1. Vision

A single `npm install` gives any Claude Code user a complete goal-to-done pipeline: describe what you want, get a validated spec, get parsed tasks, get an implementation plan, and execute with built-in verification. No API keys required (Claude Max), no manual setup, no external orchestrator.

The plugin owns the full lifecycle: **goal → discovery → spec → tasks → plan → execute → verify → done**.

---

## 2. Three Sources of Truth

| Source | Owns | File | Enforcement |
|---|---|---|---|
| **Pipeline phases** | What STAGE we're in | `.taskmaster/state/pipeline.json` | State machine with atomic transitions. Hooks hard-block illegal advances. |
| **Writing-plans output** | HOW to implement | `docs/superpowers/plans/*.md` | Strategy and approach. Read by execute-task for guidance. |
| **TaskMaster tasks** | WHAT specifically needs doing | `.taskmaster/tasks/tasks.json` | Fine-grained work items with status, deps, subtasks. **Task status is law.** |

Enforcement hierarchy:
- TaskMaster task status is the canonical truth. `done` means done. `pending` means not started. No override.
- The plan is the strategy — which task to pick next and how to approach it. Does not override task status.
- The phase is the macro position — prevents executing tasks before they exist.

---

## 3. Workflow Diagram

```
USER: "I want to build X"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PLUGIN ENTRY: prd-taskmaster skill                             │
│  Reads pipeline.json → routes to correct phase                  │
│  Pure routing, ~30 lines. No procedure.                         │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0: SETUP skill                                           │
│                                                                 │
│  MCP tools: preflight(), validate_setup(), detect_taskmaster(), │
│             init_taskmaster()                                   │
│                                                                 │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐             │
│  │ task-master │→ │ init project │→ │ configure   │             │
│  │ installed?  │  │ if needed    │  │ provider    │             │
│  └────────────┘  └──────────────┘  │ (detect     │             │
│       │ no → BLOCK                 │ first, set  │             │
│       │                            │ only if     │             │
│       │                            │ empty)      │             │
│       │                            └──────┬──────┘             │
│       │                                   │                    │
│       │                    ┌──────────────▼──────────┐         │
│       │                    │ Probe test (verify AI   │         │
│       │                    │ pipeline works)          │         │
│       │                    └─────────────────────────┘         │
│                                                                 │
│  Gate: check_gate(SETUP) → advance_phase(SETUP→DISCOVER)       │
│  Hook: gate-enforcer.py hard-blocks advance without evidence    │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: DISCOVER skill                                        │
│                                                                 │
│  MCP tools: (none — this is AI judgment)                        │
│  External: superpowers:brainstorming                            │
│                                                                 │
│  INTERACTIVE:                                                   │
│  ┌──────────────────────────────────────────────┐               │
│  │ Invoke superpowers:brainstorming with goal    │               │
│  │    ↓                                          │               │
│  │ Adaptive Q&A (one Q at a time)                │               │
│  │    ↓                                          │               │
│  │ INTERCEPT before writing-plans chains          │               │
│  │    ↓                                          │               │
│  │ Extract constraints + classify scale           │               │
│  │ (Solo 8-12 / Team 12-20 / Enterprise 20-30)  │               │
│  │    ↓                                          │               │
│  │ User approval                                 │               │
│  └──────────────────────────────────────────────┘               │
│                                                                 │
│  AUTONOMOUS (ralph-loop / auto-approve):                        │
│  ┌──────────────────────────────────────────────┐               │
│  │ Self-brainstorm from goal + context            │               │
│  │ Self-approve, document assumptions             │               │
│  └──────────────────────────────────────────────┘               │
│                                                                 │
│  Gate: check_gate(DISCOVER) → advance_phase(DISCOVER→GENERATE)  │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: GENERATE skill                                        │
│                                                                 │
│  MCP tools: load_template(), validate_prd(), calc_tasks(),      │
│             backup_prd()                                        │
│  External: task-master parse-prd, analyze-complexity,           │
│            expand --all                                         │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Load     │→ │ AI fills │→ │ Validate │→ │ Parse to │       │
│  │ template │  │ template │  │ 13 checks│  │ tasks    │       │
│  └──────────┘  └──────────┘  │ GOOD+    │  └────┬─────┘       │
│                              └──────────┘       │              │
│                                                  ▼              │
│                              ┌──────────┐  ┌──────────┐       │
│                              │ Expand   │← │ Analyze  │       │
│                              │ --all    │  │complexity│       │
│                              │ (serial!)│  └──────────┘       │
│                              └──────────┘                      │
│                                                                 │
│  Gate: GOOD+ AND tasks>0 AND subtask coverage 100%             │
│  check_gate(GENERATE) → advance_phase(GENERATE→HANDOFF)        │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: HANDOFF skill                                         │
│                                                                 │
│  MCP tools: detect_capabilities(), append_workflow(), debrief() │
│  External: superpowers:writing-plans, AskUserQuestion           │
│            (EnterPlanMode dropped per 2026-04-16 audit)         │
│                                                                 │
│  ┌────────────────┐                                             │
│  │ 1. Detect      │ Returns tier (free|premium), per-cap flags  │
│  │    capabilities│                                             │
│  └───────┬────────┘                                             │
│          ▼                                                      │
│  ┌────────────────┐                                             │
│  │ 2. Recommend   │ First-match: superpowers+ralph→C,           │
│  │    ONE mode    │ superpowers→A, taskmaster→B, fallback→A     │
│  │                │ Mode D always coming-soon (hook-blocked)     │
│  └───────┬────────┘                                             │
│          ▼                                                      │
│  ┌────────────────┐                                             │
│  │ 3. User gate:  │ AskUserQuestion (user picks mode)           │
│  │                │ Single gate — Plan Mode dropped per         │
│  │                │ 2026-04-16 audit (three-way approval        │
│  │                │ confusion, redundant artifact)              │
│  └───────┬────────┘                                             │
│          ▼                                                      │
│  ┌────────────────────────────────────────────────────┐         │
│  │ 4. Invoke writing-plans with MODE-SPECIFIC prompt  │         │
│  │                                                    │         │
│  │    Mode A: standard plan, task ID refs             │         │
│  │    Mode B: sequential pickup, clear done-when      │         │
│  │    Mode C: research gates, confidence thresholds   │         │
│  │    Mode D: CDD cards per task (hook-blocked)       │         │
│  │    E-J: SKIP writing-plans, direct task export     │         │
│  └───────┬────────────────────────────────────────────┘         │
│          ▼                                                      │
│  ┌────────────────┐                                             │
│  │ 5. Append      │ Idempotent workflow section to CLAUDE.md    │
│  │    workflow     │                                            │
│  └───────┬────────┘                                             │
│          ▼                                                      │
│  ┌────────────────┐                                             │
│  │ 6. Debrief     │ Auto-scaffold dogfood debrief               │
│  │    scaffold     │                                            │
│  └────────────────┘                                             │
│                                                                 │
│  Gate: check_gate(HANDOFF) — verifies handoff-plan.md exists    │
│        + user_mode_choice recorded in pipeline.json              │
│  advance_phase(HANDOFF→EXECUTE)                                 │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4: EXECUTE (execute-task skill, looped)                  │
│                                                                 │
│  Three sources converge:                                        │
│    Plan (HOW) + TaskMaster (WHAT) + CDD verification (PROOF)   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    EXECUTION LOOP                         │   │
│  │                                                           │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 1. next_task │ Pick next ready task from TaskMaster    │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 2. Read plan│ Find matching plan step for HOW          │   │
│  │  │    step     │                                          │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 3. Generate │ Task subtasks → CDD testing_plan          │   │
│  │  │    CDD card │ Each subtask = a verifiable check        │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 4. set      │ Mark task in-progress in TaskMaster      │   │
│  │  │ in-progress │                                          │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 5. IMPLEMENT│ Follow plan step, write code/content     │   │
│  │  │             │                                          │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────────────────────────────────────────┐      │   │
│  │  │ 6. VERIFY (mode-dependent)                       │      │   │
│  │  │                                                  │      │   │
│  │  │   Mode A: manual — user confirms subtasks done   │      │   │
│  │  │   Mode B: GREEN — run each subtask check,        │      │   │
│  │  │           capture evidence                       │      │   │
│  │  │   Mode C: GREEN + doubt agents before marking    │      │   │
│  │  │           done, research if <80% confidence      │      │   │
│  │  │   Mode D: full CDD — GREEN/RED/BLUE cycle,       │      │   │
│  │  │           Tier S evidence, browser verification  │      │   │
│  │  │           (coming soon, hook-blocked)            │      │   │
│  │  └──────┬──────────────────────────────────────────┘      │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 7. set done │ Mark task done in TaskMaster             │   │
│  │  │   (only if  │ ONLY when all subtask evidence exists    │   │
│  │  │   verified) │                                          │   │
│  │  └──────┬──────┘                                          │   │
│  │         ▼                                                 │   │
│  │  ┌─────────────┐                                          │   │
│  │  │ 8. Loop     │ Back to step 1 until no tasks remain     │   │
│  │  └─────────────┘                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  CDD verification is NATIVE to the plugin:                      │
│    Card = TaskMaster task                                       │
│    testing_plan = task subtasks                                  │
│    Evidence = captured per subtask                               │
│    GREEN = all subtasks verified with evidence                   │
│    RED = subtask failed → triggers BLUE (fix + re-verify)       │
│                                                                 │
│  Terminal: all tasks done → pipeline complete                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Plugin Structure

```
@atlas-ai/prd-taskmaster/
├── .claude-plugin/
│   └── plugin.json                # Metadata only (name, description, author, version)
├── .mcp.json                      # MCP server auto-registration
├── package.json                   # npm packaging, task-master-ai as peerDependency
├── skills/
│   ├── prd-taskmaster/
│   │   └── SKILL.md               # Orchestrator: routes to phase by pipeline state
│   ├── setup/
│   │   └── SKILL.md               # Phase 0: verify TaskMaster, init project, configure
│   ├── discover/
│   │   └── SKILL.md               # Phase 1: adaptive brainstorming, constraints, scale
│   ├── generate/
│   │   └── SKILL.md               # Phase 2: spec, validate, parse, expand
│   ├── handoff/
│   │   └── SKILL.md               # Phase 3: capabilities, mode pick, writing-plans
│   ├── execute-task/
│   │   └── SKILL.md               # Phase 4: CDD-native task lifecycle loop
│   ├── expand-tasks/
│   │   └── SKILL.md               # Companion: parallel research per task
│   └── customise-workflow/
│       └── SKILL.md               # Companion: user preference Q&A
├── hooks/
│   ├── hooks.json                 # Hook registration (matchers + commands)
│   ├── gate_enforcer.py           # PreToolUse: hard-blocks advance_phase without evidence
│   ├── mode_d_blocker.py          # PreToolUse: hard-blocks Mode D execution
│   └── evidence_gate.py           # Stop: blocks session end with incomplete CDD evidence
├── agents/
│   └── research-expander.md       # Subagent for expand-tasks parallel research
├── mcp-server/
│   ├── requirements.txt           # Python deps (mcp, etc.)
│   ├── server.py                  # FastMCP entry point, 18+ tools
│   ├── lib.py                     # atomic_write(), locked_update(), helpers
│   ├── pipeline.py                # State machine: current_phase, advance_phase, check_gate
│   ├── validation.py              # validate_prd (13 checks), placeholder detection
│   ├── capabilities.py            # detect_capabilities, detect_taskmaster, validate_setup
│   ├── taskmaster.py              # TaskMaster CLI wrapper
│   └── templates.py               # load_template
├── templates/
│   ├── prd-comprehensive.md
│   └── prd-minimal.md
├── reference/
│   ├── validation-checklist.md
│   └── taskmaster-integration-guide.md
└── tests/
    ├── conftest.py                # Real temp dirs, real files — NO MOCKING
    ├── test_mcp_tools.py          # Fast: import + call, assert JSON shapes (~100)
    ├── test_pipeline_state.py     # State machine transitions, CAS, crash recovery
    ├── test_validation.py         # PRD 13 checks, placeholders, grading
    ├── test_capabilities.py       # detect_capabilities, detect_taskmaster
    ├── test_atomic_ops.py         # atomic_write, locked_update, race simulation
    ├── test_hooks.py              # Hook JSON input/output, gate enforcement
    └── test_integration.py        # Slow: full MCP tool surface via subprocess (~50)
```

---

## 5. MCP Server — Tool Surface

### Architecture

The monolithic `script.py` is split into focused modules. ALL functions return dicts (no `sys.exit()`). `server.py` wraps them as MCP tools.

### Tool Inventory (18 tools)

| Tool | Module | Purpose |
|---|---|---|
| `preflight` | pipeline.py | Detect environment state, recommended_action |
| `current_phase` | pipeline.py | Read pipeline.json, return current phase |
| `advance_phase` | pipeline.py | CAS transition: expected_current → target (atomic) |
| `check_gate` | pipeline.py | Validate phase-specific evidence before advance |
| `detect_taskmaster` | taskmaster.py | Find MCP or CLI taskmaster |
| `init_taskmaster` | taskmaster.py | Initialize taskmaster project |
| `validate_setup` | capabilities.py | 6 structured checks with per-failure fix commands |
| `detect_capabilities` | capabilities.py | Scan for skills/tools/plugins, return tier + flags |
| `load_template` | templates.py | Load comprehensive or minimal PRD template |
| `validate_prd` | validation.py | 13 quality checks + optional AI review (`ai` param) |
| `calc_tasks` | pipeline.py | Context-aware task count (team_size, scope_phase, thematic_groups) |
| `gen_test_tasks` | pipeline.py | Generate USER-TEST task specs |
| `backup_prd` | lib.py | Timestamped PRD backup |
| `append_workflow` | lib.py | Idempotent CLAUDE.md append with sentinels |
| `debrief` | lib.py | Scaffold dogfood debrief from artifacts |
| `log_progress` | lib.py | Append to progress.md |
| `read_state` | pipeline.py | Read crash recovery state |
| `gen_scripts` | lib.py | Create tracking scripts |

### Atomic Operations (M2)

```python
# lib.py
def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(f'.tmp.{os.getpid()}')
    tmp.write_text(content)
    os.replace(tmp, path)  # Atomic on POSIX

def locked_update(path: Path, transform: Callable[[str], str]) -> str:
    lock = path.with_suffix('.lock')
    with open(lock, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        content = path.read_text() if path.exists() else ''
        new_content = transform(content)
        atomic_write(path, new_content)
    return new_content
```

### Pipeline State Machine (M3)

```python
# pipeline.py
PHASES = ['SETUP', 'DISCOVER', 'GENERATE', 'HANDOFF', 'EXECUTE']
LEGAL_TRANSITIONS = {
    None: ['SETUP'],
    'SETUP': ['DISCOVER'],
    'DISCOVER': ['GENERATE'],
    'GENERATE': ['HANDOFF'],
    'HANDOFF': ['EXECUTE'],
    'EXECUTE': [],  # terminal — individual tasks track their own status
}

def advance_phase(expected_current: str, target: str, evidence: dict) -> dict:
    """Compare-and-swap: fails if current != expected_current."""
    # Held under flock for entire read-validate-write cycle
```

### Default Provider

```python
DEFAULT_PROVIDER = "claude-code"
DEFAULT_MODEL_MAIN = "opus"
DEFAULT_MODEL_RESEARCH = "opus"
DEFAULT_MODEL_FALLBACK = "sonnet"
```

claude-code is the canonical default everywhere. Gemini CLI documented as "optimal alternative for token efficiency" (requires Google auth).

---

## 6. Hooks

All hooks are Python scripts. Registered via `hooks/hooks.json`.

### gate_enforcer.py (PreToolUse — hard block)

**Matches**: `mcp__prd-taskmaster__advance_phase`

**Behavior**: Reads `.taskmaster/state/pipeline.json`, extracts the target phase from tool input. Checks that `check_gate` was called for the current phase and returned `gate_passed: true`. If not, returns `permissionDecision: "deny"` with a message explaining which gate evidence is missing.

### mode_d_blocker.py (PreToolUse — hard block)

**Matches**: Tool calls that would execute Mode D patterns (atlas-loop, atlas-cdd invocations after HANDOFF selected Mode D).

**Behavior**: Returns `permissionDecision: "deny"` with the waitlist message.

### evidence_gate.py (Stop hook)

**Matches**: Session stop/exit.

**Behavior**: If pipeline phase is EXECUTE and there are tasks with `in-progress` status, warns that incomplete work exists. If CDD evidence count doesn't match testing_plan count for any active task, blocks exit.

---

## 7. Skills Detail

### prd-taskmaster (orchestrator)

```yaml
name: prd-taskmaster
description: >-
  Zero-config goal-to-tasks engine. Takes any goal, runs adaptive discovery,
  generates a validated spec, parses into TaskMaster tasks, creates an
  implementation plan, and executes with built-in verification.
user-invocable: true
```

~30 lines. Calls `preflight()` and `current_phase()`. Routes to the correct phase skill via `Skill` tool. Each phase skill reads `current_phase` on entry to survive context loss.

### Phase skills (setup, discover, generate, handoff)

NOT user-invocable. Each owns its procedure, its `allowed-tools` list, and its gate call. HANDOFF skill uses `AskUserQuestion` as its user-facing gate (Plan Mode dropped per 2026-04-16 audit — see Section 3 workflow diagram and Section 14 design revisions).

### execute-task (user-invocable)

```yaml
name: execute-task
description: >-
  Execute the next TaskMaster task using the implementation plan with CDD
  verification. Picks next ready task, matches to plan step, implements,
  verifies subtasks with evidence, marks done. Loop until complete.
user-invocable: true
```

The execution loop (see Section 3 diagram). CDD verification is native:
- **Card** = TaskMaster task (title, description, acceptance criteria)
- **testing_plan** = task subtasks (each subtask is a verifiable check)
- **Evidence** = captured per subtask during verification
- **GREEN** = all subtasks verified → task marked done
- **RED** = subtask failed → BLUE phase (plan fix, implement, re-verify)

Mode-dependent verification layers:
- Mode A: Manual — user confirms
- Mode B: GREEN only — run checks, capture evidence
- Mode C: GREEN + doubt agents + research if <80% confidence
- Mode D: Full CDD cycle with Tier S evidence (coming soon)

### expand-tasks, customise-workflow (user-invocable companions)

Work independently of the phase pipeline. Unchanged from current design.

---

## 8. Execution Modes — All Through writing-plans (A-D)

| Mode | writing-plans prompt | Verification layer | Task lifecycle |
|---|---|---|---|
| **A (Manual)** | Standard plan, references task IDs, clear done-when per step | User confirms subtasks | User calls execute-task manually |
| **B (TaskMaster Auto)** | Plan optimized for sequential pickup: each step = one task | GREEN: run subtask checks, evidence | execute-task loops automatically |
| **C (Ralph Loop)** | Plan with research gates: confidence thresholds per step | GREEN + doubt agents, research if <80% | ralph-loop wraps execute-task |
| **D (Atlas-Auto)** | Plan with CDD cards: Tier S evidence requirements | Full CDD GREEN/RED/BLUE cycle | Coming soon (hook-blocked) |
| **E-J (External)** | SKIP writing-plans. Direct task export in tool-native format. | External tool drives. execute-task available for status sync. | Manual or hybrid |

---

## 9. npm Packaging

### package.json

```json
{
  "name": "@atlas-ai/prd-taskmaster",
  "version": "5.0.0",
  "description": "Zero-config goal-to-tasks engine for Claude Code",
  "peerDependencies": {
    "task-master-ai": ">=0.43.0"
  },
  "scripts": {
    "postinstall": "pip install -r mcp-server/requirements.txt 2>/dev/null || echo 'Python MCP deps not installed — MCP tools will fall back to CLI'",
    "test": "pytest tests/",
    "test:fast": "pytest tests/ -k 'not integration'",
    "test:integration": "pytest tests/test_integration.py"
  }
}
```

### .mcp.json

```json
{
  "prd-taskmaster": {
    "command": "python3",
    "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-server/server.py"]
  }
}
```

### peerDependency rationale

task-master-ai is a peerDependency (not bundled) because:
- Users must have it globally for `task-master` CLI commands
- Bundling creates version conflicts with global install
- `shutil.which("task-master")` finds the global binary — no path resolution issues
- Minimum version declared, fail fast in validate-setup if unmet

---

## 9b. User Customization Layer

A first-class layer between plugin behavior and user preferences. Plugin defines the engine; user customizes the voice. No bolt-ons.

### Structure

```
.atlas-ai/customizations/
├── system-prompt-template.md       # Prepended to EVERY subagent spawn
├── task-enrichment-rules.md        # Pattern-matched onto each task before execute-task
├── verification-preferences.md     # User's preferred evidence patterns (affects GREEN gate)
├── domain-vocabulary.md            # Domain-specific term mappings (pentest/business/learning)
└── README.md                       # Self-documenting — tells user what each file does
```

### Task enrichment sweep (new Phase 3.5, between GENERATE and HANDOFF)

For each task in tasks.json:
1. Read task title + description + subtasks
2. Match against patterns in `task-enrichment-rules.md`
3. If rule matches: prepend/append user's custom rules to `task.description`
4. Write back with `enrichment_applied: true` flag (idempotent — prevents double-application)

### Subagent system-prompt injection

Every time `execute-task` spawns a subagent, it reads `system-prompt-template.md` and prepends it to the subagent's prompt. This is how "every subagent always has my text block" gets implemented.

### customise-workflow companion skill enhancement

The existing `customise-workflow` skill now:
1. Writes preferences to `.atlas-ai/config/atlas.json` (moved from `.taskmaster/config/user-workflow.json`)
2. **Points the user to the customization files above** — explicitly tells them "if you want X, edit this file"
3. Does NOT override plugin behavior — the files are layer-on-top additions
4. Before first HANDOFF, shows the user: "These customization files exist and will be applied. Edit them now or accept defaults."

### Why this layer matters

- **User sovereignty**: the plugin has opinions but users override them for their context
- **Repeatable across sessions**: edit once, all future sessions in this project use it
- **Plugin upgrades safe**: customization files are user content, not overwritten on plugin update
- **Dogfoodable**: we use this layer ourselves when building the plugin — our own atlas-ai preferences go in these files

---

## 9c. Namespace Consolidation — `.atlas-ai/` as Single Home

### The problem

Current design scatters state across the user's project:
- `.taskmaster/` (TaskMaster's directory)
- `CLAUDE.md` appended with workflow section
- `.taskmaster/rules/claude/` (if TaskMaster's rules flag used)
- `docs/superpowers/specs/` and `docs/superpowers/plans/` (from superpowers skills)

Three+ owners, three+ lifecycles. Users can't tell what's Atlas, what's TaskMaster, what's superpowers. Plugin upgrades can't cleanly reset state. Gitignore becomes a mess.

### The structure

```
project-root/
├── .atlas-ai/                          # Single plugin namespace
│   ├── taskmaster/                     # moved from .taskmaster/ (symlinked for compat)
│   │   ├── docs/prd.md
│   │   ├── tasks/tasks.json
│   │   ├── reports/
│   │   └── state/pipeline.json
│   ├── customizations/                 # from Section 9b
│   ├── references/                     # from references-ingest hook
│   ├── debrief/                        # dogfood debriefs
│   ├── config/
│   │   └── atlas.json                  # user-workflow.json + plugin config merged
│   └── README.md                       # user-facing plugin overview
├── # NO symlink needed — TASK_MASTER_PROJECT_ROOT env var handles it
├── CLAUDE.md                           # clean — 3-line pointer to .atlas-ai/
└── docs/superpowers/                   # superpowers skills own this (writing-plans/brainstorming)
    ├── specs/
    └── plans/
```

### TaskMaster compatibility — three-layer strategy (REVISED 2026-04-16 after empirical test)

**Empirical test finding (precision agent, 2026-04-16)**: `TASK_MASTER_PROJECT_ROOT` env var is **BROKEN for TaskMaster CLI invocation**. Real test with env var set + different CWD → `.taskmaster/` landed at CWD, NOT at env-var path. The env var ONLY works inside TaskMaster's MCP server (via function `Z` in dist/mcp-server.js), not for `task-master init` or other CLI commands.

Original design assumed env var controlled CLI behavior — it doesn't. Fixing the design (per Jobs Lens: fix don't cut) with a layered strategy:

**Layer 1 — MCP-first (preferred path when available)**:
If `mcp__task-master-ai__*` MCP tools are registered and healthy, invoke them exclusively with explicit `projectRoot` parameter. The MCP server DOES honor the project-root override. No CWD hacks, no symlink, no env var needed.

```python
# In our MCP server, when calling TaskMaster:
result = call_mcp_tool(
    "mcp__task-master-ai__parse_prd",
    input=prd_path,
    project_root=ATLAS_AI_DIR / "taskmaster",  # absolute path
)
```

**Layer 2 — CLI wrapper with explicit cwd (guaranteed-works fallback)**:
When task-master CLI must be invoked (init, analyze-complexity, expand --all), wrap every call with explicit `cwd=`:

```python
subprocess.run(
    ["task-master", "init", "--yes", "--store-tasks-in-git"],
    cwd=str(ATLAS_AI_DIR / "taskmaster"),  # NOT via env var — via cwd
    env=os.environ,  # no TASK_MASTER_PROJECT_ROOT needed
    timeout=60,
)
```

This is source-proof correct: TaskMaster reads `.taskmaster/` relative to CWD when the env var path doesn't fire.

**Layer 3 — Symlink defense-in-depth**:
`plugin-install`/`preflight` creates `.taskmaster -> .atlas-ai/taskmaster` symlink at project root. Any third-party tool, user script, or bare `task-master` invocation from project root lands at the correct location. Zero-config compatibility safety net.

If the symlink target is missing (fresh project), the layer-1 or layer-2 path creates `.atlas-ai/taskmaster/` first, THEN establishes the symlink. Order matters — don't point a symlink at nothing.

**All three layers enforce the same truth**: TaskMaster state lives under `.atlas-ai/taskmaster/`. The MCP-first, CLI-wrapper, and symlink paths just agree on where to find it.

### Why this won against the single-env-var design

The original §9c said "set `TASK_MASTER_PROJECT_ROOT` everywhere and call it a day." Empirical test proved that assumption wrong. The Jobs Lens (fix don't demolish) says: don't abandon the single-home goal — repair the mechanism. MCP-first + CLI cwd + symlink is more code but strictly more reliable. Each layer has a different failure mode and they converge on the same filesystem state.

### CLAUDE.md stays clean

Instead of appending a workflow section, append a pointer:

```markdown
<!-- BEGIN atlas-ai plugin workflow -->
This project uses @atlas-ai/prd-taskmaster. Plugin state lives in `.atlas-ai/`.

- Workflow: see `.atlas-ai/README.md`
- Tasks: `.atlas-ai/taskmaster/tasks/tasks.json` (or run `task-master list`)
- Execute: invoke `/prd-taskmaster:execute-task`
- Customize: see `.atlas-ai/customizations/README.md`
<!-- END atlas-ai plugin workflow -->
```

The real instructions live in `.atlas-ai/README.md` — git-tracked, user-editable, one source of truth.

### Migration path

`preflight` detects legacy `.taskmaster/` at project root (not symlink):

1. Offers to migrate: `mv .taskmaster .atlas-ai/taskmaster && ln -s .atlas-ai/taskmaster .taskmaster`
2. If user declines, falls back to legacy mode — works but warns on every run
3. After migration, existing tasks.json/prd.md unchanged, just relocated

### Benefits

- **One namespace, one ecosystem** — users see `.atlas-ai/` and know it's ours
- **TaskMaster is a backbone, not a peer** — we use its engine, we own the surface
- **Plugin upgrades atomic** — delete `.atlas-ai/` to reset; impossible with scattered state today
- **Gitignore clarity** — one `.atlas-ai/` entry excludes everything ephemeral (user can opt-in specific subdirs to git)
- **Dogfoodable** — the plugin's own development uses this structure

### Risks + mitigations

| Risk | Mitigation |
|---|---|
| TaskMaster tests hardcode `.taskmaster/` | Symlink handles it — `.taskmaster/` still resolves |
| `task-master rules add claude` writes to wrong place | With symlink, writes land in `.atlas-ai/taskmaster/rules/` transparently |
| Existing users have `.taskmaster/` already | preflight migration with user consent |
| Third-party tools expect `.taskmaster/` at root | Symlink preserves backward compat |

---

## 10. Testing Strategy

### Two tiers

| Tier | Count | Speed | Runs |
|---|---|---|---|
| Fast (import + call) | ~150 | <10s | Every push |
| Integration (full MCP surface) | ~50 | ~60s | PR merge |

### Preserved convention

NO MOCKING. Real files in temp directories. Real JSON contracts. Functions return dicts (no sys.exit).

### Test files

| File | Tests |
|---|---|
| `test_mcp_tools.py` | All 18 MCP tool JSON contracts |
| `test_pipeline_state.py` | Legal/illegal transitions, CAS, crash recovery, concurrent sessions |
| `test_validation.py` | 13 PRD checks, placeholders, grading, code-fence handling |
| `test_capabilities.py` | detect_capabilities, detect_taskmaster, validate_setup |
| `test_atomic_ops.py` | atomic_write, locked_update, race condition simulation |
| `test_hooks.py` | Hook JSON I/O, gate enforcement, Mode D blocking, evidence gate |
| `test_integration.py` | Full MCP tool invocation via subprocess |

### MCP parity by construction (M6)

No separate CLI exists. All operations are MCP tools. Parity gap is structurally impossible.

---

## 11. Dogfood Validation Plan

### 11.1 Philosophy

The plugin's design has **inevitability mechanisms** for production use (hooks, state machine, atomic writes). The dogfood is not more enforcement — it's **guided narrative validation**: .md files describe what should happen, the AI follows them, the human watches for failures.

Separation of concerns: "design is correct" (enforced by production mechanisms) vs "design is executable" (validated by dogfood).

**Build order**: Foundational pieces inevitable-by-construction first, narrative-guided pieces after. The foundation makes the upper layers' dogfood execution smoother.

### 11.2 Foundational-First Build Order

| # | Layer | Mode | Verification |
|---|---|---|---|
| F1 | Repo skeleton (.claude-plugin/plugin.json, .mcp.json, empty dirs) | INEVITABLE | `claude plugin list` shows it |
| F2 | MCP server stub (all 18 tools return stub JSON) | INEVITABLE | `mcp__plugin_prd_taskmaster_prd_taskmaster__preflight()` returns stub |
| F3 | Atomic ops + pipeline state machine | INEVITABLE | Unit tests pass; concurrent CAS survives |
| F4 | Hooks (gate_enforcer, mode_d_blocker, evidence_gate) | INEVITABLE | Fire-test with mock JSON |
| N5 | Skills (orchestrator + phase skills + companions) | NARRATIVE | SKILL.md instructions guide AI |
| N6 | Execute-task loop | NARRATIVE + TRIPLE-VALIDATED | see §11.6 |

### 11.3 The Mirror Problem — Triage Matrix

When the plugin runs on its own repo, a single action emits three distinct signals. Without triage, all failures look the same ("GENERATE failed"). With it, failures are specifically attributable.

```
              ┌──────────────────────────────┐
              │  SINGLE GENERATE INVOCATION  │
              │  on the plugin's own repo    │
              └────────────────┬─────────────┘
                               │ emits 3 signals
                  ┌────────────┼────────────┐
                  ▼            ▼            ▼
           ┌──────────┐ ┌──────────┐ ┌──────────┐
           │ BEHAVIOR │ │  OUTPUT  │ │ROBUSTNESS│
           │          │ │          │ │          │
           │ Pipeline │ │ Is PRD   │ │ Did it   │
           │ produces │ │ valid &  │ │ survive  │
           │ valid    │ │ accurate │ │ self-ref?│
           │ JSON?    │ │ about    │ │ No state │
           │ Gates    │ │ plugin?  │ │ corrupt? │
           │ fire in  │ │ GOOD+    │ │ No       │
           │ order?   │ │ grade?   │ │ loops?   │
           └────┬─────┘ └────┬─────┘ └────┬─────┘
                │            │            │
                ▼            ▼            ▼
              [B?]         [O?]         [R?]
```

**Triage Matrix:**

| B | O | R | Diagnosis |
|---|---|---|---|
| ✓ | ✓ | ✓ | Plugin works + correct + stable (ship) |
| ✓ | ✓ | ✗ | Mirror instability — self-reference corrupts state |
| ✓ | ✗ | ✓ | Behavior right, output weak — PRD template needs work |
| ✗ | ✓ | ✓ | Lucky guess — investigate, likely flaky |
| ✓ | ✗ | ✗ | Plugin runs but loses coherence on self-reference |
| ✗ | ✗ | ✓ | Stable but wrong — WORST CASE, blocks ship |
| ✗ | ✓ | ✗ | Impossible combination — log for review |
| ✗ | ✗ | ✗ | Fundamental broken — stop, restart from foundation |

### 11.4 Triple Verification at Gates

At every dogfood gate, run THREE independent validators:

1. **Plugin's own validation** (`validate_prd`, `check_gate`, etc.)
2. **`/doubt` skill** (hateful-senior-dev style)
3. **`/validate` skill** (doubt-driven validation loop)
4. **External Opus subagent** (unbiased second opinion)

**3+ agree → gate passes.** Any disagreement → surface immediately, don't proceed. The dogfood's customization file can inject per-gate verification preferences (e.g., "for security-relevant gates, add a security-focused doubt agent").

### 11.5 Execute-Task Loop Patterns (from working loops)

Patterns extracted from `pentest-loop`, `pentest-wtf`, `phoenix-loop` (working in production) — adopted verbatim for `execute-task`:

| Pattern | Source | Applied to execute-task |
|---|---|---|
| Phase-based iteration, not task queues | pentest-wtf, phoenix-loop | Each task: pick → plan-step → implement → verify → mark-done (phase gates between) |
| Evidence BEFORE points | pentest-loop | No `set_task_status("done")` until all subtask evidence captured |
| Recon escalation ladder (2 failures → stepback → /research-before-coding → /question → pivot) | pentest-loop | 2 failures on same class mandates ladder, no exceptions |
| Atomic 3-write transactions | phoenix-loop | Task status + evidence file + pipeline.json update together or not at all |
| Wall-clock timer (CronCreate heartbeat) | atlas-loop docs + pentest-loop | 15-min no-progress = force escalation, independent of iteration count |
| DIRECTION RULE (parent→child in-band, child→parent durable) | atlas-loop | execute-task subagent invocations follow same rule |

### 11.6 Loop Wrapper Failure Modes to Test in Dogfood

| Mode | Source | Dogfood test |
|---|---|---|
| 11.6.a Promise token false positive | ralph-loop docs | Does loop emit success while tasks pending? Mitigate via deterministic ship-check.py (§11.8) |
| 11.6.b Orchestrator self-ash blocking | phoenix-loop | Does any skill try to kill its own session? Forbid in skill design |
| 11.6.c Missing heartbeat silent stall | atlas-loop | Is CronCreate timer running? Verify on loop-start |
| 11.6.d Pane-state regex lies | phoenix-loop | Known limitation; surface as caveat for child-session-watching loops |
| 11.6.e Shell escaping in args | atlas-loop | Keep invocations short, write detail to files (§11.9) |

### 11.7 Customizable Instructions Dogfood

Write a dogfood-specific customization file at `.atlas-ai/customizations/system-prompt-template.md` saying: *"All implementation code must include a `# DOGFOOD:` comment at top."*

Then verify every task the execute-task loop ships has that comment. If not → customization layer is broken. This meta-tests the customization feature by using it during the dogfood.

### 11.8 Ralph-Loop Completion Promise — Checklist Style

**Bad promises (to avoid):**
```
--completion-promise "DONE"                  ← unfalsifiable
--completion-promise "All tasks complete"    ← keyword match, AI can fake
```

**Good promise (checklist-backed):**

Use the token `SHIP_CHECK_OK`, emitted ONLY when a deterministic script passes:

```bash
# .atlas-ai/ship-check.py — pseudo-code
def check() -> bool:
    assert pipeline_json["current_phase"] == "EXECUTE"
    assert pipeline_json["state"] == "complete"
    assert all(t["status"] == "done" for t in tasks_json)
    assert all(len(t["evidence_files"]) >= 1 for t in tasks_json)
    assert validate_setup()["ready"] is True
    assert validate_prd(prd_path)["grade"] in {"EXCELLENT", "GOOD"}
    assert cdd_gate_coverage() == 1.0
    assert doubt_agent_result() == "VERIFIED"
    assert validate_skill_result() == "PASS"
    assert external_opus_audit() == "AGREE"
    assert triage_matrix() == (True, True, True)  # B, O, R all pass
    assert no_recent_blockers(minutes=15)
    return True

# Invocation: python3 .atlas-ai/ship-check.py && echo SHIP_CHECK_OK
```

Ralph-loop prompt instructs the AI: *"At end of each iteration, run `python3 .atlas-ai/ship-check.py`. If it outputs `SHIP_CHECK_OK`, emit the promise. Otherwise continue."*

**Why this wins**: the promise becomes a truth test, not a keyword match. The AI can't fake it by writing "done" — it has to make the script return the token. The script inspects actual filesystem + DB state.

**Pattern origin**: same mechanism used by `skill-forge` and other forge skills — deterministic checklist, machine-readable success token.

### 11.9 Shell-Escaping Mitigation

The ralph-loop invocation CANNOT contain `()`, `!`, `$`, em-dash, smart quotes, or unicode. These break `eval` inside the plugin's setup shell script. The patched fork `atlas-ralph-loop` tightens some of these cases but the shape of the invocation must still be ASCII-only and flags-outside-quoted-prompt. Treat ASCII-only as the contract, not the implementation detail of any one plugin version.

**Pattern:**
```bash
# Invocation (short, ASCII-only):
/atlas-ralph-loop:ralph-loop \
  --max-iterations 100 \
  --completion-promise SHIP_CHECK_OK \
  "See .atlas-ai/ralph-loop-prompt.md"

# NOTE: /atlas-ralph-loop is Hayden's patched+improved fork of /ralph-loop
# (better eval safety, richer completion-promise matching, cleaner stop-hook
# handshake). Prefer /atlas-ralph-loop:ralph-loop everywhere in the plugin —
# the legacy /ralph-loop:ralph-loop remains a fallback only.

# All detail lives in the file:
.atlas-ai/ralph-loop-prompt.md
```

The prompt file contains full task description, gates, escalation rules. Fail-fast: `ship-check.py` first step verifies the file exists; abort with clear error if missing. Prevents "ralph ran with empty prompt" silent failure.

### 11.10 Dogfood-the-Dogfood Meta Validation

The dogfood uses the plugin to generate a PRD for building the plugin. Every dogfood gate is simultaneously:
- A **plugin feature test** (did the phase behave correctly?)
- An **output quality test** (is the PRD actually right?)
- A **robustness test** (did it survive self-reference?)

These three signals are the Triage Matrix in §11.3. Run at every phase transition. Failures in any dimension get their own remediation path — don't conflate "plugin broke" with "plugin output was bad".

### 11.11 TDD + Test Cadence

- **TDD from task 1**: every task gets a failing test first → implementation → passing test
- **Plugin's subtask evidence requirement forces this**: no task ships without at least one passing test
- **`/validate` cadence**: after every phase gate, after every 5 tasks in execute-task, before emitting any completion promise

### 11.12 Dogfood Phase Sequence

| Phase | What happens | Verification |
|---|---|---|
| F0 | Install skeleton via `npm link` or `claude plugin install ./` | `claude plugin list` shows plugin |
| F1 | Run `/prd-taskmaster:prd-taskmaster` in plugin's own repo | preflight returns sensible state; SETUP succeeds |
| F2 | DISCOVER with goal: "ship @atlas-ai/prd-taskmaster to npm" | constraints extracted, scale=Enterprise (20-30 tasks) |
| F3 | GENERATE on the plugin's own requirements | PRD grade ≥ GOOD, tasks parsed, expand --all completes serially |
| F4 | HANDOFF recommends Mode C (superpowers+ralph-loop) | AskUserQuestion fires, Mode C selected, writing-plans invoked |
| F5 | writing-plans produces `docs/superpowers/plans/...md` | Plan file exists, passes /doubt + /validate + external opus |
| F6 | execute-task loop runs through 3+ real tasks | DONE.md per task + evidence captured + set_task_status("done") fires |
| F7 | `python3 .atlas-ai/ship-check.py` returns SHIP_CHECK_OK | Promise emitted, ralph-loop exits cleanly |

Each phase triggers the triage matrix. Each gate triggers the triple verification.

---

## 12. Inevitability Audit Findings Addressed

| Finding | Tier | Fix in this design |
|---|---|---|
| plugin.json schema wrong | Inevitable | `.claude-plugin/plugin.json` metadata only |
| Hooks can't be .md files | Inevitable | `.py` scripts + `hooks.json` |
| Python deps not installed by npm | Inevitable | `postinstall` pip install with graceful fallback |
| MCP path resolution | Strongly-likely | `${CLAUDE_PLUGIN_ROOT}` in .mcp.json args |
| Concurrent session state | Strongly-likely | Compare-and-swap in advance_phase |
| Binary conflict (bundled task-master) | Strongly-likely | peerDependency, not bundled |
| Advisory hook won't prevent | Strongly-likely | Hard-blocking `permissionDecision: "deny"` |
| PostToolUse can't verify both tools | Strongly-likely | Moved to check_gate file-based evidence |
| Cross-skill contract unspecified | Likely | Plan in superpowers/plans/, execute-task reads it |
| sys.exit() pattern | Likely | All functions return dicts |
| Skills can't compose | Likely | State machine survives context loss |
| Test speed | Likely | Two-tier split (fast + integration) |

---

## 13. Adopted Patterns from Superpowers Skills

Patterns extracted from `using-superpowers`, `writing-plans`, `brainstorming`, `executing-plans`, and `subagent-driven-development` — proven in production across hundreds of sessions.

### Orchestrator patterns

- **Red Flags table** (from using-superpowers): Named rationalisation excuses with rebuttals. "This is too simple for a PRD" → "Simple projects are where unexamined assumptions cause the most wasted work."
- **SUBAGENT-STOP guard**: Prevent the plugin activating inside its own subagents.
- **DOT-graph flow**: Compact pipeline diagram in the orchestrator skill.
- **Downstream consumer declaration** (from writing-plans): Explicitly name what consumes `tasks.json` — atlas-plan, expand-tasks, execute-task, Modes E-J.

### DISCOVER phase patterns

- **Early scope detection gate** (from brainstorming): Before first question, detect multi-subsystem goals and decompose. Don't spend questions on unscoped projects.
- **One-question-at-a-time rule**: Never batch questions. If a topic needs depth, sequence messages.
- **Multiple choice preference**: Reduce cognitive load. Open-ended only when answer space is genuinely unconstrained.
- **2-3 approaches with lead recommendation** (from brainstorming): After discovery, propose 2-3 directions with trade-offs. Lead with recommendation.
- **Spec self-review (4-point check)** (from brainstorming): Before evidence gate — placeholders, contradictions, scope, ambiguity. Fix inline.
- **Section-by-section confirmation**: Present discovery in named sections (Goal/Audience/Approach/Constraints/Scale), confirm each.

### DISCOVER autonomous mode — goal classification (from writing-plans CLASSIFY)

Autonomous mode must classify the goal before self-approving, mirroring how writing-plans classifies blast radius:

| Goal Class | Signal | Autonomous Action |
|---|---|---|
| **CLEAR** | Explicit constraints, audience, scope, success criteria | Self-brainstorm, self-approve, document assumptions. Proceed. |
| **VAGUE** | A phrase with no constraints ("build a task manager") | Dispatch research agent first (/question 3-5 queries). Self-approve only if research fills gaps. |
| **AMBIGUOUS** | Could mean multiple things, contradicts project context | Do NOT self-approve. Write handoff note with ambiguity surfaced. Park for human review. |

`check_gate(DISCOVER)` evidence requires either `user_approved: true` (interactive) or `auto_classification: "CLEAR"` with documented assumptions (autonomous). VAGUE goals need research output as evidence. AMBIGUOUS goals cannot pass the gate autonomously.

### GENERATE phase patterns

- **Evidence gate per task** (from writing-plans): Reject any parsed task without a `testStrategy` or verification field. Add as validate-prd check #14.
- **Pre-execution task graph review** (from executing-plans): After expansion, check for dependency cycles, empty subtasks, ambiguous criteria. Surface before HANDOFF.
- **Type consistency check** (from writing-plans): Verify function/type names referenced across tasks are consistent.

### EXECUTE-TASK patterns (biggest haul)

- **Controller provides full task text** (from subagent-driven): Never tell subagent "read tasks.json" — pass task body, subtasks, deps directly in prompt. Saves context budget.
- **Two-stage review per task** (from subagent-driven): Spec compliance first (do subtasks pass?), then code quality. Order is load-bearing.
- **Four-status routing** (from subagent-driven):

| Subagent reports | Action |
|---|---|
| DONE | Run spec gate → quality gate → mark done |
| DONE_WITH_CONCERNS | Address concerns before spec gate |
| NEEDS_CONTEXT | Provide context, re-dispatch same subagent |
| BLOCKED | Try model upgrade → break task smaller → set TaskMaster `blocked` → ntfy → halt |

- **Stop-and-ask over force-through** (from executing-plans): Failed twice = blocked + ntfy + halt. Silent skip = invisible failure.
- **TodoWrite two-write rule**: Mark `in_progress` before dispatch, `completed` after verification. Cannot proceed without updating.
- **Fresh subagent per task** (from subagent-driven): No context bleed between tasks. Ralph-loop is outer controller, implementation subagents are isolated.
- **Model tiering by complexity score** (from subagent-driven): TaskMaster complexity 1-4 → fast model, 5-7 → standard, 8-10 → most capable.

---

## 13. Post-Design Revisions from Reverse-Engineering + Audits

These changes were identified after the initial spec, from reverse-engineering the Claude Code CLI source and running final audits.

### 13.1 Plugin MCP tool naming correction

Plugin MCP servers are namespaced `plugin:pluginName:serverName`. Tools become `mcp__plugin_prd_taskmaster_prd_taskmaster__toolName` (with `:` → `_` normalization), NOT `mcp__prd-taskmaster__toolName`. Source: `services/mcp/mcpStringUtils.ts`.

Hook matchers in `gate_enforcer.py` must use the full namespaced form. All `mcp__prd-taskmaster__*` references in the spec are shorthand — implementation uses the actual resolved names.

### 13.2 Plugin skill naming correction

Skills auto-discovered from `skills/*/SKILL.md` get slash-command names `/pluginName:skillDir`. So the orchestrator becomes `/prd-taskmaster:prd-taskmaster`, setup becomes `/prd-taskmaster:setup`. When one skill invokes another via the Skill tool, use these qualified names.

### 13.3 Stdio MCP no auto-reconnect

Stdio MCP servers do NOT reconnect on crash (source: `services/mcp/useManageMCPConnections.ts`). If the FastMCP server crashes, tools go `failed` until session restart. Implementation must be robust — no `sys.exit()` paths, no unhandled exceptions in tool handlers, graceful error responses.

### 13.4 MCP tools are deferred by default

All MCP tools are deferred — users must `ToolSearch` to load schemas before invocation. Exception: tools with `_meta['anthropic/alwaysLoad'] = true` load immediately. The plugin should set this on the orchestrator's critical tools (`preflight`, `current_phase`) so first-turn execution doesn't require a ToolSearch round-trip.

### 13.5 Plan Mode dropped from HANDOFF (2026-04-16 audit)

The original design proposed a dual-tool-call gate (`EnterPlanMode` + `AskUserQuestion`) in HANDOFF Step 5. An unbiased opus audit concluded this was **strictly worse** than `AskUserQuestion` alone:

- Plan Mode's "read-only" guarantee contradicts writing-plans' own file writes (it's *supposed* to write plan.md)
- Plan Mode's durable plan artifact is redundant with `docs/superpowers/plans/*.md`
- Three approval surfaces (ExitPlanMode + AskUserQuestion + writing-plans' own "which approach" prompt) create user confusion about what's being approved
- Plan Mode was designed for Claude-initiated exploratory planning, not deterministic mode recommendation from `detect_capabilities`

Decision: drop `EnterPlanMode` and `ExitPlanMode` from HANDOFF skill's `allowed-tools`. `AskUserQuestion` is the single user-facing gate. writing-plans' graduated ceremony handles any internal "which approach" prompt it needs.

### 13.6 NEEDS_CONTEXT retry cap

Subagent four-status routing: cap NEEDS_CONTEXT retries at 2 before escalating to BLOCKED. Prevents infinite loops where the subagent keeps asking for context.

### 13.7 Assumptions documented universally

`check_gate(DISCOVER)` evidence requires `assumptions_documented: true` for ALL autonomous classifications (CLEAR, VAGUE, AMBIGUOUS), not just CLEAR. No autonomous run advances without explicit assumption documentation.

### 13.8 Cross-tool context reality

Codex CLI has NO nested context file support (source: reverse-engineering). Implications:

- If the precision agent (Codex-based) needs the manuscript as context, inject it via initial prompt at spawn time — don't rely on nested AGENTS.md auto-loading
- Claude Code nested CLAUDE.md works as expected (overlay merge up the tree)
- Gemini CLI uses both GEMINI.md + AGENTS.md at two levels
- Unified cross-tool AGENTS.md is NOT currently viable

---

## 14b. Post-Audit Revisions (2026-04-16)

Revisions after a full audit combining: inevitability audit, dual-agent research pass (dangling contrarian + deep Context7/GitHub), 10 WebSearch queries, RAG insight-scout over prior fleet sessions, and empirical precision-agent testing.

The §9c namespace pivot (three-layer MCP-first + CLI-cwd + symlink) is already folded in above. The remaining 8 updates land here.

### 14b.1 Core Question subtle reframe

**Original** (§0): *"How do I know what I built is what I actually wanted?"*
**Refined**: *"How do I know what I built — at each moment of action — is what I actually wanted?"*

The "at each moment of action" clause forces verification-first thinking over phase-gated thinking. DORA 2025 + SO 2025 data shows the dominant developer pain is "AI gave me almost-right code" at the point of action, not misalignment at the planning level. The original framing is correct but insufficiently action-oriented. The inline clause sharpens it.

This is a word-level change in spec §0 — no architectural impact. Downstream implication: execute-task verification and CDD evidence must capture per-action truth, not just per-task.

### 14b.2 Inline evidence surfacing (Jobs Detail reinforcement)

**Gap**: Evidence files live in `.atlas-ai/taskmaster/.../evidence/` but users don't naturally SEE them. Cursor's differentiator is "accept or reject individual hunks inline" — visible proof at point of action.

**Fix** (three options for implementation phase): 
- (a) When `execute-task` marks done, terminal output includes inline summary: `✓ Task 5 done — evidence: test_auth.py (7/7 pass) [view]`
- (b) Open evidence file in Claude Code editor pane on task-completion (if editor-pane hook available)
- (c) Generate a one-page "task receipt" markdown per task with evidence summary + file links

Pick (a) for v5.0 (lowest friction). (b) and (c) candidates for v5.1.

### 14b.3 `prd-taskmaster migrate` command (200-star existing user support)

Existing Claude Code skill users (200+ stargazers) have `.taskmaster/` directories in their projects. When they upgrade from skill to plugin, nothing should break.

Add: `prd-taskmaster migrate` CLI command that:
1. Detects existing `.taskmaster/` at project root
2. Creates `.atlas-ai/` alongside it
3. Moves `.taskmaster/` → `.atlas-ai/taskmaster/`
4. Creates symlink `.taskmaster -> .atlas-ai/taskmaster` (layer 3 from §9c)
5. Creates `.atlas-ai/customizations/` with defaults from any existing `user-workflow.json`
6. Git-stages the changes with a clear commit message users can review before pushing

Documented in README under "Upgrading from the skill".

### 14b.4 `prd-taskmaster doctor` CLI

Windows users + corporate-proxy users will hit postinstall-pip failures. The "silent fallback" in §9 is too quiet.

Add: `prd-taskmaster doctor` that checks:
- Python 3.11+ on PATH
- `pip install -r mcp-server/requirements.txt` success (re-runs if needed)
- `mcp` Python package importable
- `task-master-ai` peer dep installed + version >= 0.43.0
- `.mcp.json` registration present
- hook scripts executable (`+x` bit set)

Returns actionable diagnostic output with exact commands to fix each failure. First-run fix-it tool.

### 14b.5 Mode D: preview-alpha, not hard-blocked

**Jobs Lens violation caught**: §8 hard-blocks Mode D execution via `mode_d_blocker.py`. That's cut-don't-fix. Repair instead:

Revise to: **Mode D preview-alpha** with the hook returning `additionalContext` (advisory) not `deny`:
- User selects Mode D → plugin prints "Mode D Atlas-Auto is alpha. Full CDD+Tier S+browser-verify+atlas-cdd integration is incomplete. You can preview what it WOULD do without executing. Opt-in via `--force-alpha` if you want to try the partial path."
- Waitlist URL still shown for those who don't want to experiment
- `atlas-phoenix` timeline commitment added to spec §15 Pipeline Context (even if date is "Q3 2026 target")

This satisfies the Jobs Lens rule (repair, surface, don't demolish) without pretending Mode D is production-ready.

### 14b.6 Customization layer visibility

**Gap**: `.atlas-ai/customizations/*.md` is user-editable but invisible after edit. Hidden state bites users on upgrade.

Add to every plugin skill invocation (orchestrator skill runs this as its first line):

```
> Active customizations: system-prompt-template.md (loaded, 23 lines), 
  task-enrichment-rules.md (not present, using defaults),
  verification-preferences.md (loaded, 2 rules active).
  Edit at .atlas-ai/customizations/ — see .atlas-ai/customizations/README.md.
```

Users always know what's loaded. No hidden state. `customise-workflow` skill enhanced to DIFF current customizations against defaults.

### 14b.7 Unfakable completion criterion (language reframe)

Fleet insight [score 0.672, 2026-04-16]: *"The strongest thing about this plan is that the completion criterion is a SQL query, not a judgment call. SELECT COUNT(*) = 0 is unfakable."*

§11.8 currently calls `SHIP_CHECK_OK` a "deterministic completion token". Stronger language: **"unfakable completion criterion"**. The AI can't fake it by writing "done" — it has to make the script return the token by actually making reality match the checks.

This is language-only. Spec §11.8 updated. The user-facing docs should lean into "unfakable" as the trust anchor — it's the answer to DORA 2025's 46% distrust finding. You trust what you can't fake.

### 14b.8 Evidence-Driven Development framing

Fleet insight [score 0.618, 2026-04-08]: *"The real insight in CDD isn't 'test-driven' — it's 'evidence-driven.' TDD is just one evidence strategy. The card is a claim. The evidence is the proof. The phase flow is a proof lifecycle."*

Our spec repeatedly says "CDD-native verification". For non-software domains (pentest, business, learning), "test-driven" is the wrong metaphor. Rename internally and in documentation:

- **Internal**: call the pattern "Evidence-Driven Development" (EDD). CDD is the software subset.
- **User-facing**: frame by domain. Software: TDD evidence. Pentest: HTTP/screenshot evidence. Business: metric evidence. Learning: demonstration evidence.
- `execute-task` skill docs: "captures evidence appropriate to the domain" — task subtasks define what counts as evidence.

This is a framing change, not an implementation change. Makes the plugin's domain-agnostic claim actually hold.

### 14b.9 atlas-ralph-loop (patched fork) is canonical — not base ralph-loop

**Caught mid-build**: initial spec §11.9 quoted the base `/ralph-loop:ralph-loop` slash command. During execution Hayden confirmed the patched fork `/atlas-ralph-loop:ralph-loop` is the canonical invocation for this project. The fork adds (a) eval-safer arg parsing, (b) richer completion-promise matching including `.claude/ralph-done` file fallback and `<promise>...</promise>` last-line discipline, (c) cleaner stop-hook handshake that avoids re-feeding prompts after explicit cancel.

**Fix applied**: §11.9 updated in-place to show the `/atlas-ralph-loop:ralph-loop` invocation and name the fork; the plan's ship-check.py docstring updated to reference it by name; base `/ralph-loop:ralph-loop` remains documented as the fallback only.

**Downstream docs to align on next touch**: the user-facing README and the `.atlas-ai/README.md` skeleton should say "Install the atlas-ralph-loop plugin for Mode C" and not "Install ralph-loop". Filenames stay put — `.atlas-ai/ralph-loop-prompt.md` is a file path inside our plugin's namespace and does not refer to the fork by name.

**Jobs-lens read**: this is a fix-don't-cut repair of an outdated reference. No feature was removed; the pattern (loop wrapper with deterministic promise token) is unchanged, only the preferred plugin-level implementation is clarified.

### 14b.10 (Reserved) — Additional updates discovered during implementation land here.

---

- **Custom complexity scoring** — TaskMaster's `analyze-complexity` is used natively
- **Custom provider detection** — `detect-capabilities` scans, doesn't reinvent
- **Custom enrichment** — TaskMaster's `expand_task` / `expand --all` is used
- **Atlas pipeline as default** — Atlas references present but not privileged
- **Mode D execution** — Hook-blocked. Teaser only until atlas-phoenix ships.
- **Markdown AST validator** — Deferred to patch release (validation uses regex for v5, AST for v5.1)

---

## 15. Pipeline Context

```
                    ┌───────────────────────────────────┐
                    │    @atlas-ai/prd-taskmaster        │
                    │                                   │
atlas-start ──────▶ │  SETUP → DISCOVER → GENERATE     │
                    │      → HANDOFF → EXECUTE          │ ──────▶ atlas-sync
                    │                                   │
                    │  Also works standalone.            │
                    │  Input: any goal                   │
                    │  Output: prd.md + tasks.json       │
                    │        + plan + executed tasks     │
                    └───────────────────────────────────┘
                              │
                              │ Future extension
                              ▼
                    ┌───────────────────────┐
                    │  atlas-phoenix        │
                    │  (Mode D, CDD Tier S, │
                    │   browser verify)     │
                    └───────────────────────┘
```
