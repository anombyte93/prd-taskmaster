# Phase: Handoff --- Smart Mode Selection

## The One Rule

**Detect what the user has. Recommend ONE mode. Present alternatives only if asked.**

## Checklist

Copy into your response:
```
HANDOFF CHECKLIST:
- [ ] Capabilities detected
- [ ] Recommended mode: ___ (reason: ___)
- [ ] Summary displayed (spec location, task count, capabilities)
- [ ] CLAUDE.md updated with task workflow
- [ ] User confirmed mode
- [ ] Handoff complete
```

## Step 1: Detect Capabilities

**MCP**: `mcp__prd-taskmaster__detect_capabilities()`
**CLI**: `python3 script.py detect-capabilities`

Returns a `tier` field (`"free"` or `"premium"`) plus per-capability flags. Key signals:

| Capability | What It Enables |
|------------|----------------|
| superpowers plugin | Modes A, C (brainstorm, plans, subagents) |
| TaskMaster CLI/MCP | Mode B (native auto-execute) |
| ralph-loop plugin | Mode C (iterative execution loop) |
| atlas-loop skill | (pre-release seed for Mode D — still coming-soon) |
| atlas-cdd skill | (pre-release seed for Mode D — still coming-soon) |
| Research model (task-master or MCP) | Deep research per task |
| Playwright MCP | Tier S browser verification |

**Mode D ★ Atlas-Auto is always coming-soon.** Even if `atlas-loop` and `atlas-cdd` are detected locally, the skill must NOT execute Mode D — see Step 2 decision logic and the Mode D block in Step 2.

## Step 2: Recommend ONE Mode

**Decision logic** (first match wins): superpowers + ralph-loop → **Mode C** | superpowers only → **Mode A** | taskmaster-only → **Mode B** | fallback → **Mode A**. External-tool modes E-J are offered as alternatives, not primary recommendations. **Mode D ★ Atlas-Auto is never the recommended mode — it is always a coming-soon teaser only,** regardless of which local plugins are installed.

### Mode A: Plan Only (Manual)
```
Recommended: Plan Only
  /writing-plans creates your implementation plan
  Plan references TaskMaster task IDs
  You drive execution manually
```

### Mode B: TaskMaster Auto-Execute
```
Recommended: TaskMaster Auto-Execute
  MCP:  mcp__task-master-ai__next_task -> implement -> set_task_status(id, "done")
  CLI:  task-master next -> implement -> task-master set-status --id N --status done
  Native TaskMaster execution loop (no external orchestrator)
```

### Mode C: Plan + Ralph Loop (Recommended Free)
```
Recommended: Plan + Ralph Loop
  /writing-plans → implementation plan
  ralph-loop wraps each task:
    next_task → set_task_status("in-progress") → research if <80% confident
    → subagent-driven-development → execution gate (Tier A+ evidence)
    → post-doubt check → log to .claude/verification-log.md
    → set_task_status("done") → TodoWrite → repeat
  Completion: doubt agent reviews verification log before promise.
```

### Mode D: ★ Atlas-Auto (Premium — COMING SOON, NOT SELECTABLE)
```
★ Atlas-Auto (premium — coming soon)
  Same as Mode C but with:
    atlas-cdd acceptance cards per task
    Tier S browser verification (Playwright)
    /question deep research per task
    /stepback on 2 failures
    atlas-gamify scoring with evidence hierarchy
    Walk away, come back to proof

  Status: NOT YET AVAILABLE. Watch anombyte93/prd-taskmaster for release.
```

**Do NOT execute Atlas-Auto even if requested.** It appears in the mode list as a teaser (so users see the roadmap) but `detect-capabilities` returns `atlas_auto: false` regardless of local flags until the feature ships. If the user selects Mode D, respond with:


Then **re-invoke the mode picker with Mode D removed from the options.**

### Alternative modes E-J (external AI tools)

`detect-capabilities` returns `alternative_modes` when these tools are installed. Users can pick any of them instead of Modes A-D. All are tool-agnostic wrappers around the same `tasks.json`.

| Mode | Tool | Invocation |
|---|---|---|
| **E** | Cursor Composer | `cursor --open .taskmaster/tasks/tasks.json`, @-ref in Composer |
| **F** | RooCode | VS Code command palette → `RooCode: Run tasks.json` |
| **G** | Codex CLI | `task-master next --format json \| codex implement` (free via ChatGPT) |
| **H** | Gemini CLI | `gemini --file .taskmaster/tasks/tasks.json implement next` (free via Google) |
| **I** | CodeRabbit | Implement via A-H, open PR, CodeRabbit reviews per task. Combines with other modes. |
| **J** | Aider | `aider --read .taskmaster/tasks/tasks.json` — pair-programming style |

## Step 3: Append Task Workflow to CLAUDE.md

Use the deterministic subcommand — do **not** do raw Read+Edit. This path is idempotent, takes a timestamped backup when modifying an existing file, and uses HTML-comment sentinels so re-runs are no-ops.

1. Write the workflow content to a tempfile (it is the same content every run):

   ```markdown
   ## Task Execution Workflow (prd-taskmaster-v2)

   When implementing tasks, prefer task-master-ai MCP tools over the CLI:
   1. `mcp__task-master-ai__next_task()` or `task-master next` -- get next ready task
   2. `set_task_status(id, "in-progress")` -- note hyphen; underscore is rejected
   3. Implement the task (follow the plan step linked to this task)
   4. `set_task_status(id, "done")` -- mark complete
   5. Update TodoWrite with progress
   6. Repeat from step 1

   Valid statuses: `pending`, `in-progress`, `done`, `review`, `blocked`, `deferred`, `cancelled`.

   ### Progress Tracking
   - Update TodoWrite BEFORE and AFTER each task
   - Cannot proceed to next task without updating TodoWrite
   - TodoWrite = user visibility. TaskMaster = source of truth.
   ```

2. **Preview first** with `--dry-run` so the user (in plan mode) can see what would be written:

   ```bash
   python3 $SKILL_DIR/script.py append-workflow \
     --target ./CLAUDE.md \
     --content-file /tmp/pdtm-workflow-section.md \
     --dry-run
   ```

3. After `ExitPlanMode` approval in Step 5, run the real write (same command without `--dry-run`). The JSON response reports one of:
   - `action: "created"` — no prior CLAUDE.md, fresh file with markers
   - `action: "skipped"` (reason: `markers_present`) — already wired, no-op
   - `action: "appended"` — existing CLAUDE.md untouched except for the appended marker block; `backup_path` points at `CLAUDE.md.prd-taskmaster-backup-<ts>`

## Step 4: Display Summary

```
Spec Generated: .taskmaster/docs/prd.md
Validation: [GRADE] ([score]/[max])
Tasks: [count] tasks parsed with dependencies
Complexity: analyzed via TaskMaster
Research: [expanded|skipped]

Capabilities:
  [check] TaskMaster (MCP|CLI)
  [check|circle] Playwright (browser verification)
  [check|circle] Research provider
  [check|circle] Ralph-loop plugin
  [check|circle] Atlas-loop (premium)
```

## Step 5: Mandatory Dual-Tool-Call — `EnterPlanMode` + `AskUserQuestion`

HANDOFF is the moment of user agency. Prose recommendations are skippable; tool calls are not. You **MUST** invoke BOTH tools in this step. This is hard-enforced — prose-only fallback is a bug, not a shortcut.

### Why both, not one

- **`AskUserQuestion`** surfaces a structured multi-option picker the user answers programmatically. It creates a stable, machine-readable choice (A/B/C/D) that downstream steps can dispatch on.
- **`EnterPlanMode`** makes the handoff decision durable. The plan file IS the handoff record: it captures the PRD path, task count, recommended mode with reason, and Atlas-Auto waitlist notice. On `ExitPlanMode` the user either approves (and execution proceeds) or rejects (and the skill safely idles with nothing committed).

Dual-call gives you BOTH an explicit user choice (AskUserQuestion) AND an explicit user approval (ExitPlanMode). Either one alone leaves a gap.

### Sequence

1. **Write the handoff plan to `.taskmaster/handoff-plan.md`** summarising:
   - PRD path + validation grade
   - Task count + complexity breakdown
   - Recommended mode (A/B/C) + one-line reason
   - Alternative modes available
   - Mode D ★ Atlas-Auto teaser with "coming soon" notice and waitlist URL
   - A "next step" section scoped to the recommended mode (e.g. for Mode B: "run `task-master next`" with the first ready task ID)

2. **Call `EnterPlanMode`** — makes the plan durable and surfaces the user-approval dialog. The plan is `.taskmaster/handoff-plan.md`.

3. **Call `AskUserQuestion`** with a multi-option question listing each available execution mode. Options include **★ Atlas-Auto (coming soon)** as Mode D, but selecting it returns the waitlist response (see Step 2, Mode D section) and re-prompts with only A/B/C.

4. **On `ExitPlanMode` approval**, dispatch the chosen mode:
   - **Mode A handoff**: invoke `superpowers:writing-plans` with spec path
   - **Mode B handoff**: show `task-master next` command + the first ready task ID
   - **Mode C handoff**: write `.claude/ralph-loop-prompt.md` and invoke `/ralph-loop:ralph-loop`
   - **Mode D handoff**: not executable — waitlist response only

### Hook-blocked fallback (graceful degradation)

If `PreToolUse:AskUserQuestion` is hook-blocked (automated / orchestrator / fleet session), fall back to a prose option table preserving the same semantics — labels, descriptions, Mode D teaser. **Surface the hook block as an `[AI]` insight block** so the parent orchestrator can detect the fallback:

> `[AI] Hook blocked AskUserQuestion — a PreToolUse hook disables interactive questions for this session (automated mode). Surfacing the mode picker in prose instead. A parent orchestrator should either lift the hook for skills with requires_user_agency:true or supply the mode selection as part of the spawn directive.`

`EnterPlanMode` is gated by a different hook (or not gated at all in most configurations) — still fire it even when `AskUserQuestion` is blocked, because the plan file remains the durable record of the handoff decision.

### Hard-coded programmatic path (for tests and fleet orchestrators)

The skill's deterministic layer exposes `python3 script.py handoff-gate --recommended <A|B|C>` (when implemented). This emits the full mode option set as structured JSON on stdout, enabling tests and external orchestrators to drive the handoff without the LLM layer. Use this when you need deterministic, LLM-skippable handoff enforcement.

### Anti-pattern: prose-only prompt

**DO NOT** say "Ready to proceed with Mode X? (or type 'options')" as your only gate. That is a prose prompt the model can skip or satisfy with a fake affirmative. The v4 dogfood (LEARNING #16 → #20) surfaced this exact pattern as a user-agency hole. The dual-tool-call is the fix.

## Step 6: Auto-scaffold dogfood debrief (closes the authorship asymmetry)

Successful runs used to leave only artifacts (PRD, tasks.json, complexity report) and no debrief — see `docs/v4-release/dogfood-shade-20260413.md §6` for why that was a real problem. Every successful HANDOFF now calls the deterministic debrief scaffolder as its final act.

```bash
SLUG="$(basename "$PWD")"
python3 "$SKILL_DIR/script.py" debrief \
  --slug "$SLUG" \
  --grade "$VALIDATION_GRADE" \
  --output-dir docs/v4-release 2>/dev/null || true
```

- Uses the project's directory name as slug (stable, matches human convention).
- Embeds the validation grade captured in Step 4's summary (`EXCELLENT 56/57`, etc.).
- Defaults to `.taskmaster/{tasks/tasks.json, reports/task-complexity-report.json, docs/prd.md}` — no path flags needed from the common case.
- Silently tolerates failure (`|| true`) — a missing complexity report or gitignored `docs/v4-release/` must never block a handoff that otherwise succeeded.
- Output path is returned as `output_path` in the JSON response; surface it to the user as "Debrief scaffolded at: <path>. Judgment sections (worked / broke / meta) left as TODO — fill them in before the memory fades."

If `docs/v4-release/` doesn't exist in the target project (most projects won't have it — this is a prd-taskmaster convention), skip the call or let it fail silently. The scaffold is only useful for projects that retain it.

## Evidence Gate

**Gate: User chose a mode, CLAUDE.md updated, handoff instructions delivered, debrief scaffolded. Skill complete.**
