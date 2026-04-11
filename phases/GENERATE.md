# Phase: Generate & Validate --- Spec Creation and Task Parsing

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
- [ ] Tasks parsed: ___ tasks created
- [ ] Complexity analyzed via TaskMaster: Y/N
- [ ] All tasks expanded into subtasks: Y/N
```

## Step 1: Choose and Load Template

Decide based on discovery depth:
- **Comprehensive**: 4+ detailed answers, complex project
- **Minimal**: Quick project, thin answers, user wants speed

```bash
python3 ~/.claude/skills/prd-taskmaster-v2/script.py load-template --type comprehensive
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

```bash
python3 ~/.claude/skills/prd-taskmaster-v2/script.py validate-prd --input .taskmaster/docs/prd.md
```

Returns: `score`, `grade`, `checks`, `warnings`, `placeholders_found`.

**Grading**: EXCELLENT (91%+), GOOD (83-90%), ACCEPTABLE (75-82%), NEEDS_WORK (<75%).

**If placeholders found**: Fix before proceeding.
**If NEEDS_WORK**: Offer auto-fix or proceed-with-risk.
**If GOOD+**: Proceed to task parsing.

## Step 4: Parse Tasks via TaskMaster

Calculate task count:
```bash
python3 ~/.claude/skills/prd-taskmaster-v2/script.py calc-tasks --requirements <count>
```

Parse (detect method from preflight):

**MCP**: `parse_prd` tool with input=".taskmaster/docs/prd.md", numTasks=<recommended>
**CLI**: `task-master parse-prd --input .taskmaster/docs/prd.md --num-tasks <recommended>`

## Step 5: Analyze Complexity via TaskMaster

Use TaskMaster's native complexity analysis instead of custom classification:

**MCP**: `analyze_complexity` (analyzes all tasks)
**CLI**: `task-master analyze-complexity`

This replaces the old `enrich-tasks` command. TaskMaster's built-in analysis is more accurate because it has full context of the task graph and dependencies.

## Step 6: Expand Tasks into Subtasks (MANDATORY)

Every task MUST be expanded into subtasks before execution begins. Subtasks are verifiable checkpoints --- without them, tasks are black boxes that either pass or fail with no intermediate proof.

**For each task:**
**MCP**: `expand_task` with id=<task_id>
**CLI**: `task-master expand --id=<task_id>`

If research provider is available, add `--research` flag for richer expansion.
If no research provider, expand WITHOUT research --- structural decomposition alone is valuable.

**DO NOT skip this step.** A task with 0 subtasks cannot be verified incrementally. The execution loop relies on subtasks as checkpoints.

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

**Gate: Spec validation grade is GOOD+ AND tasks parsed AND complexity analyzed AND all tasks have subtasks. Proceed to HANDOFF.**
