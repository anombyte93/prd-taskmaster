# Phase: Handoff — Smart Mode Selection

## The One Rule

**Detect what the user has. Recommend one free mode by default. Present Atlas
Fleet only as selectable when licensed, or as a locked Atlas Pro ($29/mo)
teaser.**

## Checklist

Copy into your response:

```text
┌─ atlas ── PHASE 4/4: HANDOFF ──────────────────────────────┐
What happened: Execution options are being prepared.
Evidence:
  ○ Capabilities detected: waiting
  ○ Recommended free mode: waiting
  ○ Summary displayed: waiting
  ○ CLAUDE.md workflow: waiting
  ○ Mode picker: waiting
  ○ Handoff complete: waiting
Next: choose how the verified task graph should be executed.
```

## Step 1: Detect Capabilities

```bash
python3 ~/.claude/skills/prd-taskmaster/script.py detect-capabilities
```

Key signals:

| Capability | What It Enables |
|------------|----------------|
| superpowers plugin | Plan & Drive and Verified Loop |
| TaskMaster CLI/MCP | Auto-Execute |
| loop runner (`ralph-loop` capability key) | Verified Loop |
| atlas-launcher MCP with active license | Atlas Fleet |
| Perplexity MCP/API | Deep research per task |
| Playwright MCP | Browser verification |

## Step 2: Recommend One Mode

Decision logic:

1. If superpowers + `ralph-loop` are detected, recommend **Verified Loop**.
2. If superpowers only are detected, recommend **Plan & Drive**.
3. If TaskMaster CLI only is detected, recommend **Auto-Execute**.
4. Otherwise recommend **Plan & Drive**.
5. Recommend **Atlas Fleet** only when `tier == "premium"` and the task graph has at least two independent dependency chains.

### Plan & Drive (internal A)

```text
Recommended: Plan & Drive
  /writing-plans creates your implementation plan
  Plan references TaskMaster task IDs
  You drive execution manually
```

### Auto-Execute (internal B)

```text
Recommended: Auto-Execute
  task-master next -> implement -> task-master set-status done -> repeat
  Native TaskMaster execution loop
```

### Verified Loop (internal C, recommended free)

```text
Recommended: Verified Loop
  /writing-plans creates implementation plan
  Evidence-gated loop wraps execution:
    next_task -> expand subtasks if missing
    -> set_task_status("in-progress")
    -> research if confidence is low
    -> superpowers:subagent-driven-development executes
    -> execution gate: run it, capture output, cold-start check
    -> log evidence
    -> set_task_status("done") -> update TodoWrite
    -> repeat
```

### Atlas Fleet (internal D; Atlas Pro)

Locked free-tier card:

```text
🔒 Atlas Fleet                                          Atlas Pro · $29/mo
  Parallel multi-session execution across Claude, Codex, and Gemini.
  Estimate from your dependency graph (actual time varies).
  Unlock: https://atlas-ai.au/pro
```

Unlocked card:

```text
▸ Atlas Fleet                     ★ Pro · license active
  <N> waves · estimate from your dependency graph (actual time varies) · walk-away
```

Fleet is never default while locked. The default must be Plan & Drive,
Auto-Execute, or Verified Loop unless tier=premium and the graph parallelizes.

## Step 3: Append Task Workflow to CLAUDE.md

Read the project's `./CLAUDE.md`. Append the TaskMaster workflow section if
normal TaskMaster parse was used.

```markdown
## Task Execution Workflow (prd-taskmaster)

When implementing tasks, use TaskMaster MCP/CLI tools:
1. `next_task` / `task-master next` -- get next dependency-ready task
2. `set_task_status(id, "in-progress")` -- mark started
3. Implement the task (follow the plan step linked to this task)
4. `set_task_status(id, "done")` -- mark complete
5. Update TodoWrite with progress
6. Repeat from step 1
```

## Step 4: Display Summary

```text
┌─ atlas ── PHASE 4/4: HANDOFF ──────────────────────────────┐
What happened: The task graph is ready for execution.
Evidence:
  ✓ Spec: .taskmaster/docs/prd.md
  ✓ Validation: <GRADE> (<score>/<max>)
  ✓ Tasks: <count> parsed with dependencies
  ✓ Recommended free mode: <Plan & Drive|Auto-Execute|Verified Loop>
  ○ Atlas Fleet: locked at Atlas Pro $29/mo, or selectable on tier=premium
Gate passed: handoff options are ready.
Next: choose one execution mode.
```

## Step 5: Confirm and Hand Off

Use `AskUserQuestion` when available. The options must list Plan & Drive,
Auto-Execute, Verified Loop, Atlas Fleet only when selectable or locked, and
"Show me more detail". Selecting locked Fleet returns one informative reply
with the $29/mo price and https://atlas-ai.au/pro, then re-prompts with free
modes only.

## Evidence Gate

**Gate passed: user chose a mode, CLAUDE.md workflow was checked, and handoff
instructions were delivered.**
