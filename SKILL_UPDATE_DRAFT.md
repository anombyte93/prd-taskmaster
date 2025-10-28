# PRD-Taskmaster Skill - Major Update Draft

## Critical Requirements

1. **MANDATORY MCP/CLI Usage**: Never create .taskmaster/ manually - ONLY via taskmaster MCP/CLI
2. **User Testing Tasks**: Insert testing task every 5 tasks for user validation
3. **Autonomous Execution Prompts**: 4 options for running tasks without user input
4. **Strict Git Policies**: Branch per task, sub-branch per subtask, commit checkpoints
5. **Progress Logging**: Document all work in progress.md
6. **Interactive Selection**: User types "1", "2", "3", or "4" to select execution mode
7. **Plan Mode**: Enable at start and end for AskUserQuestion compatibility

---

## Updated Workflow

### STEP 0: Enable Plan Mode & Prerequisites

**FIRST ACTION** when skill activates:

```
1. Check if plan mode is enabled
2. If NOT enabled: Inform user "Enabling plan mode for interactive prompts..."
3. Enable plan mode (if possible via system)
4. This ensures AskUserQuestion tool works properly
```

---

### STEP 1: Detect Taskmaster (BEFORE Discovery)

**CRITICAL**: Must detect taskmaster BEFORE generating PRD to ensure we can proceed.

```
Detection Priority:
1. Check for MCP: Attempt mcp__task-master-ai__get_tasks
   → If successful: TASKMASTER_METHOD="MCP" ✅

2. If MCP fails, check CLI: `which taskmaster`
   → If found: TASKMASTER_METHOD="CLI" ✅

3. If neither found: TASKMASTER_METHOD="NONE" ❌
   → STOP and prompt user to install:

   "⚠️ Taskmaster Required

   This skill REQUIRES taskmaster (MCP or CLI) to function properly.

   Option 1 (RECOMMENDED): Install MCP Task-Master-AI
     • Add to Claude Code MCP settings
     • See: https://github.com/cyanheads/task-master-ai

   Option 2: Install CLI
     • npm install -g task-master-ai

   Please install taskmaster and re-run this skill.
   Type 'done' when ready."

   → Wait for user confirmation
   → Re-detect after user confirms
```

**NO PROCEEDING WITHOUT TASKMASTER DETECTED**

---

### STEP 2: Discovery (same as before)

Ask 12+ detailed questions...

---

### STEP 3: Initialize Taskmaster Project (BEFORE PRD Generation)

**WHY HERE**: We need .taskmaster/ structure to exist before writing PRD.

#### If TASKMASTER_METHOD="MCP":

```
Use mcp__task-master-ai__initialize_project:
  - projectRoot: ${PWD} (absolute path)
  - yes: true
  - storeTasksInGit: true
  - initGit: false (if git already exists)
  - skipInstall: false
  - rules: ["claude"] (or user's preference)
```

#### If TASKMASTER_METHOD="CLI":

```bash
taskmaster init --yes --store-tasks-in-git --rules=claude
```

**Result**: .taskmaster/ structure created by taskmaster (NOT manually)

---

### STEP 4: Generate Comprehensive PRD

(Same as current Step 4, but now .taskmaster/docs/ exists from Step 3)

Write PRD to `.taskmaster/docs/prd.md`

---

### STEP 5: Validate PRD Quality

**The 13 Automated Validation Checks:**

#### Required Elements (5 checks):
1. ✅ Executive summary exists (2-3 sentences)
2. ✅ Problem statement includes user AND business impact
3. ✅ All goals have SMART metrics (Specific, Measurable, Achievable, Relevant, Time-bound)
4. ✅ User stories have acceptance criteria (minimum 3 per story)
5. ✅ Out of scope explicitly defined

#### Functional Requirements (3 checks):
6. ✅ All functional requirements are testable (not vague)
7. ✅ Each requirement has priority (Must/Should/Could)
8. ✅ Requirements are numbered (REQ-001, REQ-002, etc.)

#### Technical Considerations (2 checks):
9. ✅ Technical considerations address architecture
10. ✅ Non-functional requirements include specific targets (not "fast" but "< 200ms p95")

#### Taskmaster-Specific (3 checks):
11. ✅ Requirements have task breakdown hints
12. ✅ Dependencies identified for task sequencing
13. ✅ Acceptance criteria are concrete (can become task completion checks)

**Validation Output Format:**
```
✅ PRD Quality Validation: 13/13 PASSED

OR

⚠️ PRD Quality Validation: 11/13 (2 warnings)
  - REQ-007: "should be performant" is vague
    Suggestion: Replace with "< 200ms response time for 95th percentile"
  - User Story 2: Only 2 acceptance criteria (minimum 3 recommended)
    Suggestion: Add edge case criterion
```

---

### STEP 6: Parse PRD & Expand Tasks (SINGLE OPERATION)

**IMPORTANT**: Combine parse-prd + expand-all with research into ONE operation.

#### If TASKMASTER_METHOD="MCP":

```
# Single combined operation:
1. Parse PRD with research:
   Use mcp__task-master-ai__parse_prd:
     - projectRoot: ${PWD}
     - input: ".taskmaster/docs/prd.md"
     - numTasks: Auto-calculate based on PRD complexity
       • Count functional requirements
       • Simple formula: numTasks = (num_requirements * 1.5) rounded
       • Min: 10, Max: 40
     - research: true (ALWAYS use research)
     - append: false

2. Immediately expand ALL tasks with research:
   Use mcp__task-master-ai__expand_all:
     - projectRoot: ${PWD}
     - research: true (ALWAYS use research)
     - force: false
```

#### If TASKMASTER_METHOD="CLI":

```bash
# Combined operation:
taskmaster parse-prd --input .taskmaster/docs/prd.md --research --num-tasks auto && \
taskmaster expand-all --research
```

**Result**: Tasks generated and expanded in ONE workflow step.

---

### STEP 7: Insert User Testing Tasks (Every 5 Tasks)

**CRITICAL NEW REQUIREMENT**: After tasks are expanded, insert user-facing testing tasks.

**Logic:**
```
For every 5 tasks:
  - Insert a new task: "USER-TEST-{N}"
  - Title: "User Validation Checkpoint {N}"
  - Description: "Manually test functionality from Tasks {start} to {end}"

Example:
  - TASK-001 to TASK-005 → Insert USER-TEST-1 after TASK-005
  - TASK-006 to TASK-010 → Insert USER-TEST-2 after TASK-010
  - etc.
```

**User Testing Task Template:**

```markdown
# USER-TEST-{N}: User Validation Checkpoint {N}

## Purpose
Manual testing of functionality implemented in Tasks {start}-{end}

## Prerequisites
All subtasks in Tasks {start}-{end} must be completed and merged to main branch.

## Testing Checklist

### Functionality Tests
- [ ] Test Requirement REQ-{X}: [Description]
  - Expected: [What should happen]
  - Actual: [User fills in]

- [ ] Test Requirement REQ-{Y}: [Description]
  - Expected: [What should happen]
  - Actual: [User fills in]

[... one test per requirement covered in these 5 tasks]

### Integration Tests
- [ ] Test integration between [Feature A] and [Feature B]
- [ ] Verify no regressions in existing features

### Performance Tests
- [ ] Measure response time (should be < [target])
- [ ] Test under load (if applicable)

## Acceptance Criteria
- ✅ All functionality tests pass
- ✅ No critical bugs found
- ✅ Performance meets targets

## If Tests Fail
1. Document issue in .taskmaster/docs/progress.md
2. Create new task to fix issue
3. Do NOT proceed to next tasks until fixed
4. Re-run this testing checkpoint

## When Complete
Mark this task as complete in taskmaster:
- MCP: mcp__task-master-ai__set_task_status --id=USER-TEST-{N} --status=done
- CLI: taskmaster set-task-status --id=USER-TEST-{N} --status=done
```

**Implementation:**

#### If TASKMASTER_METHOD="MCP":
```
Use mcp__task-master-ai__add_task:
  - projectRoot: ${PWD}
  - title: "User Validation Checkpoint {N}"
  - description: "Manually test functionality from Tasks {start} to {end}"
  - details: [Full testing checklist template above]
  - dependencies: "{end}" (depends on last task in group)
  - priority: "high"
```

#### If TASKMASTER_METHOD="CLI":
```bash
taskmaster add-task \
  --title="User Validation Checkpoint {N}" \
  --description="Manually test functionality from Tasks {start} to {end}" \
  --dependencies="{end}" \
  --priority=high
```

**Parallel Execution Consideration:**

USER-TEST tasks are BLOCKING - they prevent parallel execution of subsequent tasks until user validates. This is intentional for quality control.

---

### STEP 8: Generate Autonomous Execution Prompts

**CRITICAL NEW REQUIREMENT**: Generate 4 execution prompts for user to choose from.

These prompts MUST:
1. ✅ Run autonomously without user input
2. ✅ Enforce strict git branching policies
3. ✅ Log all progress to .taskmaster/docs/progress.md
4. ✅ Stop at appropriate checkpoints

---

#### PROMPT 1: Sequential Until Next User Test

**Name**: "Sequential Execution to Checkpoint"

**When to Use**: User wants to step away and let AI work until next validation checkpoint

**Stops At**: Next USER-TEST task

**Prompt Template**:
```
Execute tasks sequentially from current task until USER-TEST-{N}.

STRICT GIT POLICY:
1. When starting a task:
   - Create feature branch: git checkout -b task-{id}-{slug}

2. For each subtask:
   - Create sub-branch: git checkout -b task-{id}-subtask-{n}
   - Complete subtask implementation
   - Run tests
   - Commit: git commit -m "Complete task-{id} subtask-{n}: [description]"
   - Merge to task branch: git checkout task-{id}-{slug} && git merge task-{id}-subtask-{n}
   - Delete sub-branch: git branch -d task-{id}-subtask-{n}

3. When task complete:
   - Verify ALL subtasks merged
   - Merge to main: git checkout main && git merge task-{id}-{slug}
   - Create checkpoint tag: git tag -a checkpoint-task-{id} -m "Completed task {id}"
   - Delete feature branch: git branch -d task-{id}-{slug}

PROGRESS LOGGING:
- After EVERY task completion, append to .taskmaster/docs/progress.md:

  ## Task {id}: {title} - COMPLETED
  **Completed**: {timestamp}
  **Subtasks**: {n} completed
  **Tests**: {pass/fail}
  **Issues**: [any issues encountered]
  **Git**: Merged to main, tagged as checkpoint-task-{id}

AUTONOMOUS EXECUTION RULES:
- Do NOT ask user for input unless critical error
- If task fails tests: retry once, then log and skip
- If dependency missing: log and skip
- Continue until USER-TEST-{N} reached

WHEN COMPLETE:
Stop and report:
"✅ Tasks {start} to {end} completed.
📋 Next: USER-TEST-{N} - User validation required
📝 Progress logged: .taskmaster/docs/progress.md
🌳 Git: All tasks merged to main with checkpoint tags"
```

---

#### PROMPT 2: Parallel Until Next User Test

**Name**: "Parallel Execution to Checkpoint"

**When to Use**: User wants maximum speed, tasks are independent

**Stops At**: Next USER-TEST task

**Prompt Template**:
```
Execute tasks IN PARALLEL from current task until USER-TEST-{N}.

TASK SELECTION:
1. Identify all tasks from current to USER-TEST-{N}
2. Build dependency graph
3. Execute tasks in parallel where no dependencies exist
4. Wait for dependencies before starting dependent tasks

STRICT GIT POLICY (Per Task):
1. When starting a task:
   - Create feature branch from main: git checkout main && git checkout -b task-{id}-{slug}

2. For each subtask (PARALLEL where possible):
   - Create sub-branch: git checkout -b task-{id}-subtask-{n}
   - Complete subtask implementation
   - Run tests
   - Commit: git commit -m "Complete task-{id} subtask-{n}: [description]"
   - Merge to task branch: git checkout task-{id}-{slug} && git merge task-{id}-subtask-{n}
   - Delete sub-branch: git branch -d task-{id}-subtask-{n}

3. When task complete:
   - Verify ALL subtasks merged
   - WAIT for main branch to be available (if other tasks merging)
   - Merge to main: git checkout main && git merge task-{id}-{slug}
   - Create checkpoint tag: git tag -a checkpoint-task-{id} -m "Completed task {id}"
   - Delete feature branch: git branch -d task-{id}-{slug}

PROGRESS LOGGING:
- Each parallel task logs independently to .taskmaster/docs/progress.md
- Use file locking or append-only writes to prevent conflicts

AUTONOMOUS EXECUTION RULES:
- Launch multiple tasks simultaneously (up to 3 concurrent)
- Do NOT ask user for input unless critical error
- If task fails tests: retry once, then log and continue
- Handle merge conflicts automatically where possible

WHEN COMPLETE:
Stop and report:
"✅ Tasks {start} to {end} completed IN PARALLEL
⏱️ Time saved: Estimated {X} hours
📋 Next: USER-TEST-{N} - User validation required
📝 Progress logged: .taskmaster/docs/progress.md
🌳 Git: All tasks merged to main with checkpoint tags"
```

---

#### PROMPT 3: Full Autonomous (No Stops)

**Name**: "Full Autonomous Execution"

**When to Use**: User trusts AI completely, wants everything done

**Stops At**: NEVER (runs until all tasks complete)

**Prompt Template**:
```
Execute ALL TASKS in parallel without stopping for user validation.

⚠️ WARNING: This will complete ALL tasks including USER-TEST checkpoints automatically.
User-facing testing will be SKIPPED. Use only if you trust the implementation completely.

TASK SELECTION:
1. Identify ALL tasks (including USER-TEST tasks)
2. Build complete dependency graph
3. Execute tasks in parallel where no dependencies exist

STRICT GIT POLICY (Same as Prompt 2):
[... same git policy as Prompt 2 ...]

USER-TEST TASK HANDLING:
When encountering USER-TEST-{N}:
1. Generate automated test script based on testing checklist
2. Run automated tests
3. Log results to .taskmaster/docs/progress.md
4. If tests pass: Mark complete and continue
5. If tests fail: Log issue, create fix task, continue

AUTONOMOUS EXECUTION RULES:
- MAXIMUM parallelization (up to 5 concurrent tasks)
- NEVER ask user for input
- Auto-fix test failures where possible
- If unable to fix: log and continue

WHEN COMPLETE:
Stop and report:
"✅ ALL TASKS COMPLETED
📊 Summary:
  - Total tasks: {n}
  - Successful: {n}
  - Failed: {n}
  - Time taken: {X} hours
📋 USER-TEST tasks completed automatically (see progress.md)
📝 Full progress log: .taskmaster/docs/progress.md
🌳 Git: All tasks merged to main with checkpoint tags

⚠️ RECOMMENDED: Review .taskmaster/docs/progress.md for any issues
🧪 RECOMMENDED: Run manual tests to verify all functionality"
```

---

#### PROMPT 4: User Decides (Manual)

**Name**: "Manual Task Selection"

**When to Use**: User wants full control

**Prompt Template**:
```
Awaiting user instructions for task execution.

Available commands:
- "next task" - Get next task to work on
- "task {id}" - Work on specific task
- "status" - Show current progress
- "parallel {id1,id2,id3}" - Run specific tasks in parallel

Git policies will still be enforced for each task.
Progress will still be logged to .taskmaster/docs/progress.md.
```

---

### STEP 9: Interactive Prompt Selection (AskUserQuestion)

**CRITICAL**: Use AskUserQuestion tool to let user choose execution mode.

**Implementation**:

```
Use AskUserQuestion tool:

questions:
  - question: "How would you like to execute these tasks?"
    header: "Execution Mode"
    multiSelect: false
    options:
      - label: "Sequential to Checkpoint"
        description: "Work autonomously until next user test (USER-TEST-{N}). Stops for your validation. RECOMMENDED for quality control."

      - label: "Parallel to Checkpoint"
        description: "Run independent tasks in parallel until next user test. Faster execution, stops for validation."

      - label: "Full Autonomous"
        description: "Run ALL tasks in parallel without stopping. ⚠️ Skips user validation checkpoints. Use only if highly confident."

      - label: "Manual Control"
        description: "You decide which tasks to run and when. Full control over execution."

After user selects, store their answer and prepare corresponding prompt.
```

**After Selection**:

```
User selected option {N}.

NEXT STEP: Copy and paste this prompt to begin execution:

[Output the full prompt template for their selected option]

---

💡 TIP: Simply type the number (1, 2, 3, or 4) to select that option.
```

**IMPORTANT**: The skill should recognize if user types just "1", "2", "3", or "4" in their next message and automatically proceed with that option's prompt.

---

### STEP 10: Re-Enable Plan Mode (If Disabled)

**FINAL ACTION** before skill completes:

```
1. Check if plan mode is still enabled
2. If disabled: Re-enable plan mode
3. Inform user: "Plan mode re-enabled for future interactive prompts"
```

---

## Summary of Changes

✅ **Step 0**: Enable plan mode at start
✅ **Step 1**: Detect taskmaster FIRST (block if not found)
✅ **Step 3**: Use taskmaster MCP/CLI to initialize (never manual mkdir)
✅ **Step 5**: Document all 13 validation checks
✅ **Step 6**: Combine parse-prd + expand-all with research
✅ **Step 7**: Insert USER-TEST tasks every 5 tasks
✅ **Step 8**: Generate 4 autonomous execution prompts with git policies
✅ **Step 9**: Use AskUserQuestion for interactive selection
✅ **Step 10**: Re-enable plan mode at end

**All prompts enforce**:
- Strict git branching (branch per task, sub-branch per subtask)
- Commit checkpoints after every task
- Progress logging to .taskmaster/docs/progress.md
- Autonomous execution without user input
