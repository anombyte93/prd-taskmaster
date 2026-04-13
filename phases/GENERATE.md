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

**MCP (preferred)**: `mcp__prd-taskmaster__load_template(type="comprehensive")`
**CLI fallback**: `python3 script.py load-template --type comprehensive`

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

Key rule: Every `[placeholder]`, `{{variable}}`, `[TBD]`, `[TODO]` must be either (a) replaced with real content, (b) removed, or (c) **paired with a `reason:` explanation** on the same line or the next line documenting why the decision is deferred.

**Deferred decisions** (per the v4 spec): placeholders with `reason:` attribution are allowed and surfaced in the validation output as `deferred_decisions`. A bare placeholder is a validation failure; an attributed one is a known deferred decision with accountability.

Examples:

```
# BAD — bare placeholder, fails check 14:
Target latency: {{TBD}}

# GOOD — attributed, passes check 14 and appears in deferred_decisions:
Target latency: {{TBD}} reason: awaiting load-test results scheduled 2026-04-20
```

## Step 3: Validate Spec Quality

**MCP (preferred)**: `mcp__prd-taskmaster__validate_prd(input_path=".taskmaster/docs/prd.md")`
**CLI fallback**: `python3 script.py validate-prd --input .taskmaster/docs/prd.md`

Returns: `score`, `grade`, `checks`, `warnings`, `placeholders_found`.

**Optional AI-augmented review** (opt-in): pass `--ai` (CLI) or `ai=True` (MCP) to additionally invoke TaskMaster's configured main model for a holistic quality review. The deterministic regex checks always run first — AI review is additive, never a replacement. If task-master is unavailable, the AI path falls back silently with a warning.

**Grading**: EXCELLENT (91%+), GOOD (83-90%), ACCEPTABLE (75-82%), NEEDS_WORK (<75%).

**If placeholders found**: Fix before proceeding.
**If NEEDS_WORK**: Offer auto-fix or proceed-with-risk.
**If GOOD+**: Proceed to task parsing.

## Step 4: Parse Tasks via TaskMaster

Calculate task count:
**MCP**: `mcp__prd-taskmaster__calc_tasks(requirements_count=<count>)`
**CLI**: `python3 script.py calc-tasks --requirements <count>`

Parse (detect method from preflight):

**MCP (preferred)**: `mcp__task-master-ai__parse_prd(input=".taskmaster/docs/prd.md", numTasks=<recommended>)`
**MCP fallback**: `mcp__prd-taskmaster__tm_parse_prd(input_path=".taskmaster/docs/prd.md", num_tasks=<recommended>)` (wraps the CLI)
**CLI**: `task-master parse-prd --input .taskmaster/docs/prd.md --num-tasks <recommended>`

## Step 5: Analyze Complexity via TaskMaster

Use TaskMaster's native complexity analysis instead of custom classification:

**MCP (preferred)**: `mcp__task-master-ai__analyze_complexity` (analyzes all tasks)
**MCP fallback**: `mcp__prd-taskmaster__tm_analyze_complexity` (wraps the CLI)
**CLI**: `task-master analyze-complexity`

**Important — output location**: `analyze-complexity` does NOT emit JSON to stdout. It writes structured analysis to `.taskmaster/reports/task-complexity-report.json` and prints a human-readable table to stdout. To read the structured result, read the report file:

```bash
cat .taskmaster/reports/task-complexity-report.json | jq .
```

Do not try to parse the stdout table — it's colour-coded ASCII and will break. This replaces the old `enrich-tasks` command. TaskMaster's built-in analysis is more accurate because it has full context of the task graph and dependencies.

## Step 6: Expand Tasks into Subtasks (MANDATORY)

Every task MUST be expanded into subtasks before execution begins. Subtasks are verifiable checkpoints --- without them, tasks are black boxes that either pass or fail with no intermediate proof.

### Use `task-master expand --all`, not per-id parallel calls

Per-id parallel calls (e.g. `task-master expand --id=1 & task-master expand --id=2 &`) hit a non-atomic **read-modify-write race** on `.taskmaster/tasks/tasks.json`: every parallel writer reads the same starting snapshot, adds its own subtasks, and writes the whole file back. The last writer wins and earlier writes are silently lost — the AI call reports success, the subtasks were generated, but they never landed on disk. Detected in the v4 Shade dogfood 2026-04-13 (LEARNING #8).

`task-master expand --all` is the correct path. It is internally serial (one task at a time, one file write at a time) and therefore atomic across the whole batch.

**Invocation:**

**CLI (required path)**:
```bash
# Preferred: research-enriched expansion (when a research provider is configured)
task-master expand --all --research

# Fallback: structural-only (still valuable; always available)
task-master expand --all
```

**MCP**: task-master's MCP currently exposes `expand_task(id=...)` per-task only. Do **not** call it in parallel. Either call it serially for every task, or shell out to `task-master expand --all` via Bash. If a future task-master MCP version adds a batch tool, prefer that.

### Patience under slow providers

Under `claude-code` (Claude Max rate-limited) or local `ollama`, `--all` can run for 5-15 minutes on a 12-task project. Do **not** time out aggressively. Use `.taskmaster/tasks/tasks.json` mtime as the liveness signal:

- **mtime updated within last 60s** → work is landing, keep waiting
- **mtime stale for 120s+** → investigate (rate limit, provider crash, network)
- **Never conclude STUCK from a single capture** — always compare two snapshots 30-60s apart

### Verify coverage (read tasks.json DIRECTLY, not `task-master list`)

`task-master list --format json` has been observed to return a different top-level schema from `tasks.json`, causing a consumer to report 0/N coverage even when all tasks have subtasks on disk (LEARNING #15, v4 dogfood). Always read the canonical file directly:

```bash
python3 -c "
import json
d = json.load(open('.taskmaster/tasks/tasks.json'))
# tasks.json is tag-grouped (master, defaults, feature branches) — walk all tags
all_tasks = []
if 'master' in d and isinstance(d['master'], dict):
    all_tasks = d['master'].get('tasks', [])
elif 'tasks' in d:
    all_tasks = d['tasks']
else:
    for v in d.values():
        if isinstance(v, dict) and 'tasks' in v:
            all_tasks.extend(v['tasks'])

counts = [len(t.get('subtasks', [])) for t in all_tasks]
covered = sum(1 for c in counts if c > 0)
total = len(all_tasks)
no_subs = [t['id'] for t in all_tasks if not t.get('subtasks')]

if no_subs:
    print(f'WARNING: {covered}/{total} tasks expanded. Missing: {no_subs}. Re-run task-master expand --all.')
else:
    print(f'OK: All {total} tasks expanded ({sum(counts)} subtasks total).')
"
```

### Idempotent recovery

If any task still shows 0 subtasks after `--all` completes (rate-limit hiccup, provider timeout, partial run), **re-run the same command**:

```bash
task-master expand --all --research
```

`--all` only re-expands tasks that are still in `pending` state with 0 subtasks, so a second invocation is safe and recovers gracefully. Do **not** work around it with parallel per-id calls — that is the exact pattern that causes silent data loss.

**DO NOT skip this step.** A task with 0 subtasks cannot be verified incrementally. The execution loop relies on subtasks as checkpoints.

## Evidence Gate

**Gate: Spec validation grade is GOOD+ AND tasks parsed AND complexity analyzed AND all tasks have subtasks. Proceed to HANDOFF.**
