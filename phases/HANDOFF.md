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
| atlas-loop skill | Mode D (premium gamified execution) |
| Perplexity MCP/API | Deep research per task |
| Playwright MCP | Tier S browser verification |

## Step 2: Recommend ONE Mode

**Decision logic** (first match wins): atlas-loop + atlas-cdd → **Mode D** | superpowers + ralph-loop → **Mode C** | superpowers only → **Mode A** | taskmaster-only → **Mode B** | fallback → **Mode A**. External-tool modes E-J are offered as alternatives, not primary recommendations.

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

Read the project's `./CLAUDE.md`. Append this section (if not already present):

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

## Step 5: Confirm and Hand Off

Ask: "Ready to proceed with [recommended mode]? (or type 'options' to see alternatives)"

If confirmed -> execute handoff for that mode.
If asks options -> show all 4 modes with one-line descriptions.
If picks different -> execute that handoff instead.

**Mode A handoff**: Invoke /writing-plans with spec path.
**Mode B handoff**: Show `task-master next` command.
**Mode C handoff**: Write .claude/ralph-loop-prompt.md and invoke ralph-loop.
**Mode D handoff**: Invoke /atlas-loop with goal and task context.

## Evidence Gate

**Gate: User chose a mode, CLAUDE.md updated, handoff instructions delivered. Skill complete.**
