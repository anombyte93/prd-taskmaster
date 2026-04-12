# PRD-Taskmaster Skill - User Experience Example

## Complete Conversation Flow (User's Perspective)

---

### 1. User Activates Skill

**USER:**
```
I want a PRD for adding user authentication with OAuth and 2FA to my app
```

---

### 2. Skill Activates & Enables Plan Mode

**CLAUDE:**
```
I'll help you create a comprehensive PRD for user authentication with OAuth and 2FA.

🔧 Enabling plan mode for interactive prompts...

Let me start by checking for taskmaster integration...
```

---

### 3. Taskmaster Detection

**CLAUDE:**
```
✅ Detected: MCP Task-Master-AI

Great! I'll use MCP for seamless taskmaster integration. This means:
- Automatic project initialization
- Automatic task generation from PRD
- Direct integration with Claude Code

Now, let me ask some detailed questions to create a comprehensive PRD...
```

**Alternative (if not detected):**
```
⚠️ Taskmaster Required

This skill REQUIRES taskmaster (MCP or CLI) to function properly.

I didn't detect taskmaster in your environment. You have two options:

**Option 1 (RECOMMENDED): Install MCP Task-Master-AI**
  • Add to your Claude Code MCP settings
  • Provides seamless integration
  • See: https://github.com/cyanheads/task-master-ai

**Option 2: Install CLI**
  • Run: npm install -g task-master-ai
  • Use command-line interface

Please install taskmaster and type 'done' when ready, or I can wait while you install it.
```

---

### 4. Discovery Questions (Interactive)

**CLAUDE:**
```
Let me ask you some detailed questions to ensure the PRD is comprehensive:

**1. What problem does this solve?**
Tell me about the user pain point and business impact.
```

**USER:**
```
Users currently can't use their existing Google/GitHub accounts to log in,
and we're seeing security concerns from enterprise customers who require 2FA.
We're losing 3 enterprise deals per month because of this.
```

**CLAUDE:**
```
**2. Who is the target user/audience?**
```

**USER:**
```
B2B enterprise customers, particularly IT departments and security-conscious teams
```

**CLAUDE:**
```
**3. What tech stack are you using?**
```

**USER:**
```
Node.js backend (Express), React frontend, PostgreSQL database
```

**CLAUDE:**
```
**4. What are your key success metrics?**
How will we measure if this is successful?
```

**USER:**
```
- 80% of new users choose OAuth over password
- Reduce account takeover incidents by 90%
- Close at least 5 enterprise deals within 2 months
- 2FA adoption rate of 60% among enterprise users
```

**CLAUDE:**
```
**5. Any constraints or timeline expectations?**
```

**USER:**
```
Need to launch in 6 weeks, must be SOC2 compliant
```

**CLAUDE:**
```
**6. Any integration requirements?**
Third-party services, internal systems, etc.
```

**USER:**
```
Google OAuth, GitHub OAuth, Twilio for SMS 2FA
```

**CLAUDE:**
```
**7. Performance/scale requirements?**
```

**USER:**
```
Support 10,000 concurrent users, auth flow should complete in < 2 seconds
```

**CLAUDE:**
```
**8. Have you used taskmaster before?**
This helps me calibrate the detail level.
```

**USER:**
```
Yes, I've used it on 2 previous projects
```

**CLAUDE:**
```
**9. Estimated complexity for this feature?**
Simple feature, typical project, or complex system?
```

**USER:**
```
Typical project with moderate complexity
```

**CLAUDE:**
```
**10. Anything else I should know?**
Edge cases, constraints, context...
```

**USER:**
```
Must work on mobile web, need to support fallback for SMS 2FA if
authenticator app doesn't work
```

**CLAUDE:**
```
Perfect! I have everything I need. Let me create your comprehensive PRD...
```

---

### 5. PRD Generation & Taskmaster Initialization

**CLAUDE:**
```
🔄 Initializing taskmaster project structure...

Using: mcp__task-master-ai__initialize_project
✅ Created .taskmaster/docs/
✅ Created .taskmaster/tasks/
✅ Created .taskmaster/reports/
✅ Updated .gitignore

📝 Generating comprehensive PRD...

Sections included:
  ✅ Executive Summary
  ✅ Problem Statement (with business impact)
  ✅ Goals & Success Metrics (SMART format)
  ✅ User Stories (with acceptance criteria)
  ✅ Functional Requirements (17 requirements)
  ✅ Non-Functional Requirements (performance, security)
  ✅ Technical Considerations (architecture, API specs, database)
  ✅ Implementation Roadmap
  ✅ Out of Scope
  ✅ Open Questions & Risks
  ✅ Validation Checkpoints

✅ PRD saved to: .taskmaster/docs/prd.md
```

---

### 6. PRD Validation

**CLAUDE:**
```
🔍 Running automated quality validation...

✅ PRD Quality Validation: 13/13 PASSED

  ✅ Executive summary exists (2-3 sentences)
  ✅ Problem statement includes user AND business impact
  ✅ All goals have SMART metrics
  ✅ User stories have acceptance criteria (3+ per story)
  ✅ Out of scope explicitly defined
  ✅ All functional requirements are testable
  ✅ Each requirement has priority (Must/Should/Could)
  ✅ Requirements are numbered (REQ-001 through REQ-017)
  ✅ Technical considerations address architecture
  ✅ Non-functional requirements include specific targets
  ✅ Requirements have task breakdown hints
  ✅ Dependencies identified for task sequencing
  ✅ Acceptance criteria are concrete

📊 Quality Score: 60/60 (EXCELLENT)
```

---

### 7. Task Generation & Expansion

**CLAUDE:**
```
🤖 Parsing PRD to generate tasks...

Using: mcp__task-master-ai__parse_prd
  - Analyzing 17 functional requirements
  - Calculating optimal task count: 22 tasks
  - Using research mode for better quality

✅ Generated 22 tasks from PRD

🔄 Expanding all tasks into subtasks...

Using: mcp__task-master-ai__expand_all
  - Using research mode for detailed subtasks
  - Generating implementation steps
  - Adding acceptance criteria

✅ Expanded 22 tasks into 94 subtasks

📋 Task Summary:
  - Phase 1 (Foundation): 5 tasks, 18 subtasks
  - Phase 2 (OAuth Integration): 6 tasks, 28 subtasks
  - Phase 3 (2FA Implementation): 5 tasks, 22 subtasks
  - Phase 4 (Testing & Security): 4 tasks, 18 subtasks
  - Phase 5 (Deployment): 2 tasks, 8 subtasks
```

---

### 8. User Testing Tasks Insertion

**CLAUDE:**
```
✨ Inserting user validation checkpoints...

Every 5 tasks, I'm adding a USER-TEST checkpoint where you'll manually
test the functionality to ensure everything works before continuing.

✅ Inserted: USER-TEST-1 (after Task 5)
   Tests: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005

✅ Inserted: USER-TEST-2 (after Task 10)
   Tests: REQ-006, REQ-007, REQ-008, REQ-009, REQ-010

✅ Inserted: USER-TEST-3 (after Task 15)
   Tests: REQ-011, REQ-012, REQ-013, REQ-014, REQ-015

✅ Inserted: USER-TEST-4 (after Task 20)
   Tests: REQ-016, REQ-017, integration testing

📊 Updated task count: 26 tasks total (22 implementation + 4 user tests)
```

---

### 9. CLAUDE.md Generation

**CLAUDE:**
```
📝 Generating CLAUDE.md workflow guide...

This file will guide me (Claude) to:
  - Follow TDD approach (write tests first)
  - Use blind-validator before marking tasks complete
  - Execute tasks in parallel where possible
  - Maintain quality through validation gates
  - Follow taskmaster best practices

✅ CLAUDE.md created in project root
```

---

### 10. Interactive Execution Mode Selection

**CLAUDE:**
```
📄 PRD Created: .taskmaster/docs/prd.md
✅ Taskmaster Initialized: Using MCP (seamless integration)
📋 Tasks Generated: 26 tasks (22 implementation + 4 user tests)
🔄 Tasks Expanded: 94 subtasks with detailed implementation steps
🤖 CLAUDE.md Generated: Project root (TDD workflow guide)

📊 Overview:
  - Feature: User Authentication with OAuth + 2FA
  - Complexity: Medium
  - Estimated Effort: 26 tasks, ~118 hours
  - Timeline: 6 weeks (feasible with team of 2-3)
  - Key Goal: 80% OAuth adoption, 90% reduction in account takeovers

🎯 Key Requirements:
  1. REQ-001: OAuth 2.0 integration (Google, GitHub)
  2. REQ-002: TOTP-based 2FA
  3. REQ-003: SMS fallback for 2FA
  4. REQ-004: Session management with Redis
  5. REQ-005: SOC2 compliance logging

🔧 Technical Highlights:
  - Architecture: Passport.js for OAuth, speakeasy for TOTP
  - Integration: Google OAuth, GitHub OAuth, Twilio SMS
  - Database: 3 new tables (oauth_providers, totp_secrets, backup_codes)
  - Performance: Redis for session caching, < 2s auth flow

⚠️ Quality Validation:
  ✅ All required elements present
  ✅ All 13 validation checks passed
  ✅ Ready for task execution

📋 Task Breakdown:
  - Phase 1: 5 tasks (database, models, middleware)
  - Phase 2: 6 tasks (OAuth providers, callback handlers)
  - Phase 3: 5 tasks (TOTP, SMS, backup codes)
  - Phase 4: 4 tasks (testing, security audit)
  - Phase 5: 2 tasks (deployment, monitoring)

👤 User Testing Checkpoints:
  - USER-TEST-1: After Task 5 (test foundation)
  - USER-TEST-2: After Task 10 (test OAuth)
  - USER-TEST-3: After Task 15 (test 2FA)
  - USER-TEST-4: After Task 20 (integration tests)
```

**Now the interactive selection appears:**

---

### 11. AskUserQuestion - Interactive Prompt Selection

**CLAUDE displays an interactive question UI:**

```
┌─────────────────────────────────────────────────────────────────┐
│ How would you like to execute these tasks?                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ○ 1. Sequential to Checkpoint                                   │
│   Work autonomously until next user test (USER-TEST-1).         │
│   Stops for your validation. RECOMMENDED for quality control.   │
│                                                                  │
│ ○ 2. Parallel to Checkpoint                                     │
│   Run independent tasks in parallel until next user test.       │
│   Faster execution, stops for validation.                       │
│                                                                  │
│ ○ 3. Full Autonomous                                            │
│   Run ALL tasks in parallel without stopping.                   │
│   ⚠️ Skips user validation checkpoints.                         │
│   Use only if highly confident.                                 │
│                                                                  │
│ ○ 4. Manual Control                                             │
│   You decide which tasks to run and when.                       │
│   Full control over execution.                                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ ⭐ Claude Recommends: Option 1 - Sequential to Checkpoint       │
│                                                                  │
│ This is your first time with this feature, and quality control  │
│ is critical for authentication. Sequential execution with user  │
│ testing checkpoints will catch issues early.                    │
└─────────────────────────────────────────────────────────────────┘

💡 TIP: Just type the number (1, 2, 3, or 4) to select that option.
```

---

### 12. User Makes Selection

**USER:**
```
1
```

---

### 13. Claude Outputs Execution Prompt

**CLAUDE:**
```
✅ Selected: Sequential to Checkpoint

I'll work autonomously until USER-TEST-1, stopping only for your validation.

Here's what will happen:

📋 Tasks to Execute:
  - TASK-001: Setup database schema for auth
  - TASK-002: Create User model with OAuth fields
  - TASK-003: Setup Passport.js middleware
  - TASK-004: Create session management with Redis
  - TASK-005: Setup API endpoints structure

⏸️ Stop Point: USER-TEST-1 (you'll test foundation)

🌳 Git Policy:
  - Feature branch per task
  - Sub-branch per subtask
  - Merge to main after each task completes
  - Checkpoint tag after every task

📝 Progress Logging:
  - All work logged to: .taskmaster/docs/progress.md
  - You can monitor progress in real-time

─────────────────────────────────────────────────────────────

🚀 READY TO BEGIN

Copy and paste this prompt to start autonomous execution:

─────────────────────────────────────────────────────────────

Execute tasks sequentially from TASK-001 until USER-TEST-1.

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
After EVERY task completion, append to .taskmaster/docs/progress.md:

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
- Continue until USER-TEST-1 reached

WHEN COMPLETE:
Stop and report:
"✅ Tasks 1-5 completed.
📋 Next: USER-TEST-1 - User validation required
📝 Progress logged: .taskmaster/docs/progress.md
🌳 Git: All tasks merged to main with checkpoint tags"

─────────────────────────────────────────────────────────────

💡 SHORTCUT: Just say "begin" or "start" and I'll execute automatically!
```

---

### 14. User Starts Execution

**USER:**
```
begin
```

---

### 15. Autonomous Execution (Claude Working)

**CLAUDE:**
```
🚀 Starting autonomous execution...

──────────────────────────────────────────────────────────────
TASK-001: Setup database schema for auth
──────────────────────────────────────────────────────────────

📌 Creating feature branch: task-001-setup-database-schema

Subtask 1/4: Create migration file for oauth_providers table
  🌿 Branch: task-001-subtask-1
  📝 Creating migration: migrations/001_create_oauth_providers.sql
  ✅ Migration created with columns: id, user_id, provider, provider_user_id, access_token
  🧪 Testing: Migration syntax valid
  ✅ Committed: "Complete task-001 subtask-1: Create oauth_providers migration"
  🔀 Merged to task-001-setup-database-schema
  🗑️ Deleted branch: task-001-subtask-1

Subtask 2/4: Create migration file for totp_secrets table
  🌿 Branch: task-001-subtask-2
  📝 Creating migration: migrations/002_create_totp_secrets.sql
  ✅ Migration created with columns: id, user_id, secret, backup_codes, created_at
  🧪 Testing: Migration syntax valid
  ✅ Committed: "Complete task-001 subtask-2: Create totp_secrets migration"
  🔀 Merged to task-001-setup-database-schema
  🗑️ Deleted branch: task-001-subtask-2

Subtask 3/4: Create migration file for sessions table
  🌿 Branch: task-001-subtask-3
  📝 Creating migration: migrations/003_create_sessions_table.sql
  ✅ Migration created for Redis-backed sessions
  🧪 Testing: Migration syntax valid
  ✅ Committed: "Complete task-001 subtask-3: Create sessions migration"
  🔀 Merged to task-001-setup-database-schema
  🗑️ Deleted branch: task-001-subtask-3

Subtask 4/4: Run migrations in development environment
  🌿 Branch: task-001-subtask-4
  🔄 Running: npm run migrate
  ✅ All migrations applied successfully
  🧪 Testing: Tables exist in database
  ✅ Committed: "Complete task-001 subtask-4: Apply migrations"
  🔀 Merged to task-001-setup-database-schema
  🗑️ Deleted branch: task-001-subtask-4

All subtasks completed! Merging to main...
  🔀 Merged: task-001-setup-database-schema → main
  🏷️ Tagged: checkpoint-task-001
  🗑️ Deleted branch: task-001-setup-database-schema

📝 Logged to progress.md:
────────────────────────────────────────────────────────────
## Task 001: Setup database schema for auth - COMPLETED
**Completed**: 2025-01-29 14:23:15
**Subtasks**: 4 completed
**Tests**: All passed
**Issues**: None
**Git**: Merged to main, tagged as checkpoint-task-001
────────────────────────────────────────────────────────────

✅ TASK-001 COMPLETE (18 minutes)

──────────────────────────────────────────────────────────────
TASK-002: Create User model with OAuth fields
──────────────────────────────────────────────────────────────

📌 Creating feature branch: task-002-create-user-model

Subtask 1/5: Create User model class...
[... continues similarly ...]

```

[Claude continues working through all 5 tasks autonomously...]

```
──────────────────────────────────────────────────────────────

✅ TASKS 1-5 COMPLETED

📊 Summary:
  - Task 001: Setup database schema - ✅ DONE (18 min)
  - Task 002: Create User model - ✅ DONE (25 min)
  - Task 003: Setup Passport.js - ✅ DONE (32 min)
  - Task 004: Session management - ✅ DONE (28 min)
  - Task 005: API endpoints structure - ✅ DONE (22 min)

⏱️ Total Time: 2 hours 5 minutes

📝 Progress Log: .taskmaster/docs/progress.md

🌳 Git Status:
  - All tasks merged to main
  - 5 checkpoint tags created
  - Clean working directory

──────────────────────────────────────────────────────────────
📋 NEXT: USER-TEST-1 - Your Validation Required
──────────────────────────────────────────────────────────────

Please test the following functionality:

**Foundation Testing Checklist:**

1. Database Schema:
   - [ ] Verify oauth_providers table exists
   - [ ] Verify totp_secrets table exists
   - [ ] Verify sessions table exists
   - [ ] Check all columns and indexes

2. User Model:
   - [ ] Create a test user with OAuth fields
   - [ ] Verify relationships work
   - [ ] Test validation rules

3. Passport.js Setup:
   - [ ] Check middleware is loaded
   - [ ] Verify Google strategy configured
   - [ ] Verify GitHub strategy configured

4. Session Management:
   - [ ] Test Redis connection
   - [ ] Create a session
   - [ ] Retrieve a session
   - [ ] Verify session expiration

5. API Endpoints:
   - [ ] GET /auth/google - returns redirect
   - [ ] GET /auth/github - returns redirect
   - [ ] POST /auth/logout - clears session

**How to Test:**

```bash
# Start the dev server
npm run dev

# Run test suite
npm test

# Manual API testing (use Postman or curl)
curl http://localhost:3000/auth/google
```

**Expected Results:**
- All database tables created successfully
- User model CRUD operations work
- Passport strategies initialize without errors
- Redis connection established
- API endpoints respond with correct status codes

**If Everything Passes:**
- Type "passed" to continue to Tasks 6-10

**If You Find Issues:**
- Document them in .taskmaster/docs/progress.md
- Type "issues" and describe what failed
- I'll create fix tasks before proceeding

──────────────────────────────────────────────────────────────

Ready for your validation! 🧪
```

---

### 16. User Tests & Responds

**USER tests the app, runs commands, checks functionality...**

**USER:**
```
passed
```

---

### 17. Claude Continues

**CLAUDE:**
```
✅ USER-TEST-1 PASSED!

Excellent! The foundation is solid. Moving to Phase 2: OAuth Integration

Updating task status...
  ✅ Set: USER-TEST-1 status = done

─────────────────────────────────────────────────────────────

Would you like me to:
1. Continue with sequential execution (Tasks 6-10 → USER-TEST-2)
2. Switch to parallel execution (faster, same stopping point)
3. You take manual control from here

Just type 1, 2, or 3
```

---

### 18. Alternative - If User Found Issues

**USER:**
```
issues - the Redis connection keeps timing out
```

**CLAUDE:**
```
⚠️ Issue Detected: Redis connection timeout

Let me investigate and create a fix task...

🔍 Analyzing issue:
  - Location: Task 004 (Session management)
  - Symptom: Redis connection timeout
  - Possible causes:
    1. Redis not running
    2. Incorrect connection config
    3. Firewall blocking connection

Creating fix task...

✅ Created: TASK-005.1: Fix Redis connection timeout
   Priority: Critical (blocking)
   Subtasks:
     - Verify Redis is running (docker ps or systemctl status redis)
     - Check connection string in .env file
     - Test connection with redis-cli
     - Update timeout configuration if needed
     - Verify Redis is accessible from Node.js

📝 Logged issue to: .taskmaster/docs/progress.md

─────────────────────────────────────────────────────────────

I'll work on this fix now. Give me a moment...

[Claude works on fix autonomously...]

✅ FIXED! The issue was: Redis connection timeout set to 1000ms, increased to 5000ms

Please re-run USER-TEST-1 to verify the fix.

Type "retest" when ready.
```

---

## Summary of User Experience

**The user sees:**

1. ✅ **Clear activation** - Skill recognizes intent
2. ✅ **Plan mode enabled** - Interactive prompts work
3. ✅ **Taskmaster detection** - Auto-detects MCP/CLI
4. ✅ **Guided discovery** - Asks smart questions
5. ✅ **Transparent progress** - Shows each step
6. ✅ **Quality validation** - 13 checks run automatically
7. ✅ **Interactive selection** - Just type "1", "2", "3", or "4"
8. ✅ **Autonomous execution** - Claude works without interruption
9. ✅ **Clear git history** - Every task has checkpoint
10. ✅ **User testing checkpoints** - Validate every 5 tasks
11. ✅ **Progress logging** - Real-time progress.md updates
12. ✅ **Error handling** - Auto-fixes or creates fix tasks

**The user types minimal input:**
- Answers to discovery questions
- "1" to select execution mode
- "begin" to start
- "passed" or "issues" at checkpoints

**Everything else is automated!**
