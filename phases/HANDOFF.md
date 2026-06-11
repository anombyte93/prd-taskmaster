# Phase: Handoff — Smart Mode Selection

## The One Rule

**Detect what the user has. Recommend ONE mode. Present alternatives only if asked.**

## Checklist

Copy into your response:
```
HANDOFF CHECKLIST:
- [ ] Capabilities detected
- [ ] Task source: TaskMaster CLI/MCP | manual flag
- [ ] Recommended mode: ___ (reason: ___)
- [ ] Summary displayed (spec location, task count, capabilities)
- [ ] CLAUDE.md updated with task workflow
- [ ] User confirmed mode
- [ ] Handoff complete
```

## Step 1: Detect Capabilities

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py detect-capabilities
```

Key signals:

| Capability | What It Enables |
|------------|----------------|
| superpowers plugin | Modes A, C (brainstorm, plans, subagents) |
| TaskMaster CLI/MCP | Mode B (native auto-execute) |
| ralph-loop plugin | Mode C (iterative execution loop) |
| atlas-loop skill | Mode D (premium gamified execution) |
| Perplexity MCP/API | Deep research per task |
| Playwright MCP | Tier S browser verification |

## Step 2: Recommend ONE Mode

**Decision logic:**
1. If manual flag was used -> Recommend **Mode M** (manual tasks + selected execution skill)
2. If atlas-loop + atlas-cdd detected -> Recommend **Mode D** (premium, most capable)
3. If superpowers + ralph-loop detected -> Recommend **Mode C** (recommended free)
4. If superpowers detected (no ralph-loop) -> Recommend **Mode A** (plan only)
5. If TaskMaster CLI only -> Recommend **Mode B** (native auto-execute)
6. Fallback -> Recommend **Mode A** (always works)

### Mode M: Manual Task JSON
```
Recommended: Manual Task JSON
  .taskmaster/docs/prd.md and .taskmaster/tasks/tasks.json already exist
  validate-tasks + enrich-tasks are the gate
  Execute the validated tasks with the user's requested execution skill
  Update TodoWrite from tasks.json and mark task statuses manually or via task-master if available
```

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
  task-master next -> implement -> task-master set-status done -> repeat
  Native TaskMaster execution loop
```

### Mode C: Plan + Ralph Loop (Recommended Free)
```
Recommended: Plan + Ralph Loop
  /writing-plans creates implementation plan
  Ralph-loop wraps execution:
    next_task -> expand subtasks if missing
    -> set_task_status("in_progress")
    -> pre-task doubt: "Do I understand this? Research if <80% confident"
    -> superpowers:subagent-driven-development executes
    -> EXECUTION GATE: run it, capture output, cold-start check
    -> Evidence must be Tier A+ (captured execution output minimum)
    -> Post-execution doubt: "Would user see this working?"
    -> Log evidence to .claude/verification-log.md
    -> set_task_status("done") -> update TodoWrite
    -> repeat
  At completion: doubt agent reviews verification log before promise
  Research via WebSearch (or your configured provider)
```

### Mode D: Atlas Loop (Premium)
```
Recommended: Atlas Loop (Premium)
  Same as Mode C but with:
    atlas-cdd acceptance cards per task
    Tier S browser verification (Playwright)
    /question deep research per task
    /stepback on 2 failures
    atlas-gamify scoring with evidence hierarchy
    Walk away, come back to proof
```

## Step 3: Append Task Workflow to CLAUDE.md

Read the project's `./CLAUDE.md`. Append the TaskMaster workflow section if normal TaskMaster parse was used. If the Native Mode Path was used, append the manual workflow variant instead.

```markdown
## Task Execution Workflow (prd-taskmaster)

When implementing tasks, use TaskMaster MCP/CLI tools:
1. `next_task` / `task-master next` -- get next dependency-ready task
2. `set_task_status(id, "in_progress")` -- mark started
3. Implement the task (follow the plan step linked to this task)
4. `set_task_status(id, "done")` -- mark complete
5. Update TodoWrite with progress
6. Repeat from step 1

### Progress Tracking
- Update TodoWrite BEFORE and AFTER each task
- Cannot proceed to next task without updating TodoWrite
- TodoWrite = user visibility. TaskMaster = source of truth.
```

Native Mode Path variant:

```markdown
## Task Execution Workflow (prd-taskmaster manual mode)

When implementing manually-authored prd-taskmaster tasks:
1. Read `.taskmaster/tasks/tasks.json` as the task source of truth.
2. Confirm `validate-tasks`, `enrich-tasks`, and `validate-tasks --require-phase-config` have passed.
3. Create TodoWrite entries from the validated tasks.
4. Mark a task `in-progress` in `tasks.json` before implementation.
5. Implement and verify the task using the selected execution skill.
6. Mark the task `done` in `tasks.json` only after verification evidence is captured.
7. Update TodoWrite before moving to the next task.
```

## Step 4: Display Summary

```
Spec Generated: .taskmaster/docs/prd.md
Validation: [GRADE] ([score]/[max])
Tasks: [count] tasks parsed with dependencies
Task source: [TaskMaster parse | manual tasks.json]
Research: [expanded|skipped]

Capabilities:
  [check] TaskMaster (MCP|CLI)
  [check|circle] Playwright (browser verification)
  [check|circle] Research provider
  [check|circle] Ralph-loop plugin
  [check|circle] Atlas-loop (premium)
```

## Step 5: Confirm and Hand Off

Ask: "Ready to proceed with [recommended mode]? (or type 'options' to see alternatives)"

If confirmed -> execute handoff for that mode.
If asks options -> show all 5 modes with one-line descriptions.
If picks different -> execute that handoff instead.

**Mode A handoff**: Invoke /writing-plans with spec path.
**Mode B handoff**: Show `task-master next` command.
**Mode C handoff**: Write .claude/ralph-loop-prompt.md and invoke ralph-loop.
**Mode D handoff**: Invoke /atlas-loop with goal and task context.
**Mode M handoff**: Load `.taskmaster/tasks/tasks.json`, create TodoWrite from it, and invoke the requested execution skill directly.

## Evidence Gate

**Gate: User chose a mode, CLAUDE.md updated, handoff instructions delivered. Skill complete.**
