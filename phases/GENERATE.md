# Phase: Generate & Validate — Spec Creation and Task Parsing

## Backend mode (applies to every step below)

Backend mode was resolved in SKILL.md Phase 0. If you have NOT resolved it (e.g. this
phase file was entered directly), run the Phase 0 procedure now — in Claude Code that
means `ToolSearch(query="select:mcp__atlas-engine__engine_preflight")` (keyword fallback
`ToolSearch(query="+engine preflight atlas", max_results=10)`) BEFORE any bash. Tool ids
look like `mcp__atlas-engine__<name>` (user-scoped server) or
`mcp__plugin_prd_go__<name>` (plugin install). **In MCP-mode, using script.py
for an MCP-covered op is a compliance failure.** The script.py commands below are the
CLI-mode path (zero-dependency installs, codex/gemini harnesses).


## The One Rule

**Generate the spec, validate it catches placeholders, parse it into tasks. Quality over speed.**

## Checklist

Copy into your response:
```
GENERATE CHECKLIST:
- [ ] Template loaded (comprehensive|minimal)
- [ ] Spec written with discovery answers (no placeholders remaining)
- [ ] Validation score: ___ / ___ (grade: ___)
- [ ] Placeholder check: ___ placeholders found
- [ ] Warnings addressed or acknowledged
- [ ] Task creation mode: TaskMaster parse | manual flag
- [ ] Tasks created: ___ tasks
- [ ] Task validation: pass/fail
- [ ] Tasks enriched with metadata: Y/N
```

## Step 1: Choose and Load Template

Decide based on discovery depth:
- **Comprehensive**: 4+ detailed answers, complex project
- **Minimal**: Quick project, thin answers, user wants speed

**MCP-mode**: `<prefix>load_template(type="comprehensive")`
**CLI-mode**:
```bash
python3 ~/.claude/skills/prd-taskmaster/script.py load-template --type comprehensive
```

## Step 2: Generate Spec

Fill the template with discovery answers. AI judgment required:
- Replace ALL placeholders with actual content
- Expand with project-specific details
- Add technical depth proportional to what user provided
- Generate domain-appropriate sections (pentest = threat model, app = user stories, business = success metrics, learning = assessment criteria)
- Document assumptions where discovery was thin
- **CONSTRAINT CHECK**: Verify EVERY constraint from the DISCOVER phase constraint list appears in the spec. If "must use Python" was a constraint, the spec must reference Python. Missing constraints = spec bug.
- **SCOPE CHECK**: Use the scale classification from DISCOVER to set task count range. Solo = 8-12, Team = 12-20, Enterprise = 20-30.

Write to `.taskmaster/docs/prd.md`.

### Domain-Neutral Vocabulary

When writing the spec, use domain-neutral terms unless the domain is known:

| Software term | Neutral equivalent | When to use neutral |
|--------------|-------------------|-------------------|
| tests | verification criteria | pentest, business, learning |
| code | deliverable | business, learning |
| deploy | execute / deliver | business, learning |
| repo | workspace | non-software |
| PR / pull request | output / submission | non-software |
| user stories | success scenarios | all domains |
| API endpoints | capabilities | non-software |
| CI/CD | delivery pipeline | non-software |

If the domain IS software, use software terms. The neutral terms are for non-software goals.

Key rule: Every `[placeholder]`, `{{variable}}`, `[TBD]`, `[TODO]` must be replaced or removed.

## Step 3: Validate Spec Quality

**MCP-mode**: `<prefix>validate_prd(input_path=".taskmaster/docs/prd.md")`
**CLI-mode**:
```bash
python3 ~/.claude/skills/prd-taskmaster/script.py validate-prd --input .taskmaster/docs/prd.md
```

Returns: `score`, `grade`, `checks`, `warnings`, `placeholders_found`.

**Grading**: EXCELLENT (91%+), GOOD (83-90%), ACCEPTABLE (75-82%), NEEDS_WORK (<75%).

**If placeholders found**: Fix before proceeding.
**If NEEDS_WORK**: Offer auto-fix or proceed-with-risk.
**If GOOD+**: Proceed to task parsing.

## Step 4: Parse Tasks via Backend

Calculate task count:

**MCP-mode**: `<prefix>calc_tasks(requirements_count=<count>)`
**CLI-mode**:
```bash
python3 ~/.claude/skills/prd-taskmaster/script.py calc-tasks --requirements <count>
```

Parse through the normative backend operation:

**backend op parse-prd**:

**MCP-mode**: `<prefix>parse_prd(prd_path=".taskmaster/docs/prd.md", num_tasks=<recommended>)`
**CLI-mode**:
```bash
python3 ~/.claude/skills/prd-taskmaster/script.py parse-prd --input .taskmaster/docs/prd.md --num-tasks <recommended>
```

**TaskMaster backend direct methods** (only when explicitly operating that backend):
- **MCP**: `mcp__task-master-ai__parse_prd(input=".taskmaster/docs/prd.md", numTasks=<recommended>)`
- **CLI**: `task-master parse-prd --input .taskmaster/docs/prd.md --num-tasks <recommended>`

### Native Mode Path (manual flag / no TaskMaster)

If the user passed `--manual`, `manual=true`, or explicitly asked to "do what TaskMaster does manually", skip MCP/CLI parsing and write `.taskmaster/tasks/tasks.json` yourself.

Required shape:

```json
{
  "tasks": [
    {
      "id": 1,
      "title": "Concrete task title",
      "description": "One-sentence outcome",
      "details": "Implementation notes, files, constraints, and acceptance expectations.",
      "testStrategy": "Exact verification command or evidence requirement.",
      "status": "pending",
      "dependencies": [],
      "priority": "high",
      "subtasks": [
        {
          "id": 1,
          "title": "Concrete checkpoint",
          "description": "Verifiable subtask outcome",
          "status": "pending",
          "dependencies": []
        }
      ]
    }
  ]
}
```

Rules:
- Generate the same task count recommended by `calc-tasks`, unless the PRD is intentionally smaller.
- Every task must have at least 2 subtasks before execution begins.
- Dependencies must point only to existing task IDs.
- Do not include placeholders, generic "implement feature" tasks, or empty `testStrategy` fields.

Validate the manually-authored file:

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks
```

## Step 5: Enrich Tasks

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py enrich-tasks
```

Adds complexity classification (SIMPLE/MEDIUM/COMPLEX/RESEARCH/VALIDATION) and lifecycle phases.

In the Native Mode Path, immediately verify enrichment:

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py validate-tasks --require-phase-config
```

## Step 6: Expand Tasks into Subtasks (MANDATORY)

Every task MUST be expanded into subtasks before execution begins. Subtasks are verifiable checkpoints — without them, tasks are black boxes that either pass or fail with no intermediate proof.

**Pick the expansion path by this tree (token-economy aware):**

```
Manual flag                      → subtasks written by hand, validate-tasks passed (skip expansion)
pending tasks ≤ 3                → TaskMasterBackend.expand internal: SERIAL NATIVE
                                     in the main dir:
                                     rate --research   (once)
                                     expand --id=<id> --research     (per task)
task-master ≥ 0.43 AND research
  role is a REAL structured API  → TaskMasterBackend.expand internal:
                                     NATIVE-PARALLEL (DEFAULT):
                                     python3 script.py tm-parallel
                                   (serial analyze-complexity → N isolated workdirs, each running
                                    native expand --research on an economy-tier model → ONE atomic
                                    harvest merge. Failed packets fall back to agent-parallel.)
free local proxy / no API key /
  TM errors / TM < 0.43          → native/agent path: AGENT-PARALLEL (fallback):
                                     parallel-plan → N research subagents → parallel-apply
```

In MCP-mode, the NATIVE-PARALLEL path is `<prefix>tm_parallel_expand` (instead of
`script.py tm-parallel`) and serial expansion uses `<prefix>rate_tasks` / `<prefix>expand_tasks`.

This keeps TaskMaster's model-agnostic AI (any configured API does the expansion/research) while
parallelizing it externally. Never run multiple `expand --id` concurrently in ONE directory — the
10s lock-stale window vs 30–120s AI calls is a real race; isolation dirs (tm-parallel) exist for
exactly this.

If no research provider at all, expand WITHOUT research — structural decomposition alone is valuable.

**DO NOT skip this step.** A task with 0 subtasks cannot be verified incrementally. The execution loop (Mode C/D) relies on subtasks as checkpoints.

After expansion, verify:
```bash
task-master list --format json | python3 -c "
import sys, json
data = json.load(sys.stdin)
tasks = data.get('tasks', data) if isinstance(data, dict) else data
no_subtasks = [t['id'] for t in tasks if not t.get('subtasks')]
if no_subtasks:
    print(f'WARNING: Tasks {no_subtasks} have no subtasks. Expand them.')
else:
    print(f'OK: All {len(tasks)} tasks have subtasks.')
"
```

## Evidence Gate

**Gate: Spec validation grade is GOOD+ AND tasks created via TaskMaster parse or manual flag AND `validate-tasks` passes AND all tasks have subtasks AND `enrich-tasks` has run. In the Native Mode Path, `validate-tasks --require-phase-config` must also pass. Proceed to HANDOFF.**
