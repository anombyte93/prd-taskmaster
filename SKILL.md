---
name: Taskmaster-Integrated PRD System
description: Comprehensive PRD generation with full taskmaster integration. Generates detailed technical PRDs optimized for task breakdown, sets up .taskmaster/ directory structure, validates against taskmaster requirements. Use when user requests "PRD", "product requirements", "create requirements", or mentions task-driven development. Optimized for engineer-driven, AI-assisted development workflows.
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
---

# Taskmaster-Integrated PRD System

Complete PRD generation system optimized for taskmaster AI task generation. Creates comprehensive, engineer-focused product requirements documents that enable effective task breakdown and implementation planning.

## When to Use This Skill

Activate when user:
- Requests a PRD or product requirements document
- Says "I want a PRD", "create requirements", "write requirements"
- Mentions taskmaster or task-driven development
- Asks to document product/feature requirements for engineering

Do NOT activate for:
- Code documentation (API docs, technical reference)
- Test specifications or QA documentation
- Project management timelines without product context
- PDF document creation

## Core Principles

**Quality Over Speed**: Planning is 95% of the work. Take time to create comprehensive PRDs that enable successful implementation.

**Taskmaster Optimization**: PRDs must have sufficient detail for taskmaster to generate actionable tasks. Every requirement needs acceptance criteria, technical specs, and clear task boundaries.

**Engineer-Focused**: Primary audience is engineering teams. Include technical depth, code examples, architecture considerations, and implementation details.

**Validation-Driven**: Automated checks ensure PRD quality before delivery. Warn if requirements are vague or missing critical information.

**Complete Integration**: Don't just generate PRD - set up proper taskmaster directory structure, validate quality, suggest task breakdowns.

## Workflow

### Step 1: Discovery (Comprehensive Requirements Gathering)

Ask detailed questions to ensure comprehensive PRD:

**Essential Questions**:
1. What problem does this solve? (user pain point, business impact)
2. Who is the target user/audience?
3. What is the proposed solution or feature?
4. What are the key success metrics? (how we measure success)
5. What constraints exist? (technical, timeline, resources)

**Technical Context**:
6. Is this for an existing codebase or greenfield project?
7. What tech stack? (if known)
8. Any integration requirements? (third-party services, internal systems)
9. Performance/scale requirements? (users, data volume, latency)

**Taskmaster Specific**:
10. Have you used taskmaster before? (helps calibrate detail level)
11. What's the estimated complexity? (simple feature, typical project, complex system)
12. Timeline expectations? (helps with phasing and task breakdown)

**Open-Ended**:
13. Anything else I should know? (edge cases, constraints, context)

**Smart Defaults**:
- If user provides minimal answers, use best guesses and document assumptions
- Default to comprehensive detail (user's stated preference)
- Assume engineer audience unless specified otherwise

### Step 2: Environment Check

Check for existing taskmaster setup and available tools:

```bash
# Check if .taskmaster/ exists
if [ -d ".taskmaster" ]; then
  # Check for existing PRD
  if [ -f ".taskmaster/docs/prd.md" ]; then
    Ask: "Found existing prd.md. Update it or create new version?"
  fi
fi
```

**Detect Taskmaster Integration Method** (prioritize MCP over CLI):

1. **Check for MCP Task-Master-AI** (PREFERRED):
   - Attempt to use `mcp__task-master-ai__get_tasks` tool
   - If available: MCP is installed and functional
   - Set `TASKMASTER_METHOD="MCP"`
   - Note: MCP provides superior integration (direct function calls, no shell dependency)

2. **Fallback to CLI**:
   - Run: `which taskmaster` or `taskmaster --version`
   - If found: CLI is available
   - Set `TASKMASTER_METHOD="CLI"`

3. **Neither Available**:
   - Set `TASKMASTER_METHOD="NONE"`
   - Will provide installation instructions

**Actions**:
- If `.taskmaster/` exists → Respect existing structure, ask before overwriting
- If no `.taskmaster/` → Will create it in Step 5
- MCP detected → Use MCP tools for all taskmaster operations (preferred)
- CLI detected → Use CLI commands for taskmaster operations
- Neither detected → Suggest installation options (non-blocking)

### Step 3: Codebase Analysis (if applicable)

If working in existing codebase, analyze to ground PRD in technical reality:

**Search for Related Code**:
```
Use Grep to find:
- Relevant features/modules (e.g., for "2FA", search "auth", "login", "security")
- Existing patterns (API structure, data models, services)
- Integration points (where new feature connects)
```

**Document Findings**:
- Current architecture patterns (MVC, service-repository, etc.)
- Existing API conventions (RESTful endpoints, naming)
- Database schema structure
- File organization and naming conventions

**Reference in PRD**:
- Specific file paths (e.g., `src/auth/login.ts:45`)
- Existing endpoints, models, services to integrate with
- Technical constraints from current implementation

If greenfield project, focus on proposed architecture instead.

### Step 4: Generate Comprehensive PRD

Use template from `templates/taskmaster-prd-comprehensive.md`

**Key Sections**:

1. **Executive Summary** (2-3 sentences: problem + solution + impact)

2. **Problem Statement**
   - Current situation and pain points
   - User impact (who's affected, how)
   - Business impact (cost, opportunity)
   - Why solve this now

3. **Goals & Success Metrics** (SMART format)
   - 3-5 specific goals
   - Each with: metric, baseline, target, timeframe
   - Example: "Increase user activation from 45% to 65% within 3 months"

4. **User Stories** (Agile format with taskmaster focus)
   - As a [user], I want to [action] so that I can [benefit]
   - Detailed acceptance criteria (becomes task completion criteria)
   - Each story suggests 1-3 implementation tasks

5. **Functional Requirements**
   - Numbered (REQ-001, REQ-002, etc.)
   - Prioritized (Must/Should/Could have)
   - Each requirement is atomic and testable
   - Includes implementation hints for task breakdown

6. **Non-Functional Requirements**
   - Performance (with specific targets: "< 200ms p95")
   - Security (authentication, encryption, compliance)
   - Scalability (user load, data volume)
   - Reliability (uptime, error rates)
   - Accessibility (WCAG standards)
   - Compatibility (browsers, devices, OS)

7. **Technical Considerations**
   - Architecture implications
   - API specifications (with request/response examples)
   - Database schema changes (with SQL/schema examples)
   - Dependencies (internal and external)
   - Migration strategy (for existing systems)
   - Testing strategy (unit, integration, e2e)

8. **Implementation Roadmap** (Taskmaster Optimization)
   - Phase breakdown (Phase 1, 2, 3...)
   - Task sequencing (what depends on what)
   - Complexity estimates (for taskmaster scheduling)
   - Suggested task breakdown per requirement

9. **Out of Scope**
   - Explicitly list what will NOT be included
   - Prevents scope creep
   - Note future considerations

10. **Open Questions & Risks**
    - Unresolved decisions with owners
    - Known risks with mitigation strategies
    - Areas needing further research

11. **Validation Checkpoints**
    - Milestones where we verify progress
    - Quality gates for task completion

**Adaptation Rules**:

For **engineer audience** (default):
- Maximum technical detail
- Code examples, API schemas, database models
- Architecture diagrams or descriptions
- File references from codebase analysis

For **mixed audience**:
- Technical appendix for deep details
- Executive summary for high-level view
- Balance business and technical language

For **greenfield projects**:
- Proposed architecture (not existing)
- Technology stack recommendations
- Initial file structure suggestions

### Step 5: Setup Taskmaster Structure

Use script from `scripts/setup-taskmaster.sh` to create/update directory structure:

```bash
# Create .taskmaster/ structure if doesn't exist
mkdir -p .taskmaster/docs
mkdir -p .taskmaster/tasks
mkdir -p .taskmaster/reports

# Update .gitignore to exclude taskmaster state
if ! grep -q ".taskmaster/state.json" .gitignore 2>/dev/null; then
  echo ".taskmaster/state.json" >> .gitignore
  echo ".taskmaster/tasks/" >> .gitignore
fi
```

**Output PRD**:
- Write to `.taskmaster/docs/prd.md`
- Use proper markdown formatting
- Include table of contents for easy navigation

**Generate CLAUDE.md (and optionally codex.md) for TDD Workflow**:
- Use template from `templates/CLAUDE.md.template`
- Replace placeholders with project-specific information:
  - `{{PROJECT_NAME}}` - From PRD title
  - `{{TECH_STACK}}` - From discovery questions
  - `{{ARCHITECTURE_OVERVIEW}}` - From technical considerations
  - `{{KEY_DEPENDENCIES}}` - From PRD dependencies section
  - `{{TESTING_FRAMEWORK}}` - From tech stack or ask user
  - `{{DEV_ENVIRONMENT}}` - From tech stack
  - `{{TEST_COMMAND}}` - Inferred from tech stack (npm test, pytest, etc.)
- Write to project root: `CLAUDE.md`
- **Ask user:** "Are you using Codex? If yes, I'll also create codex.md (same content as CLAUDE.md)"
  - If yes: Copy `CLAUDE.md` to `codex.md` in project root
  - If no: Skip codex.md creation
- This file guides Claude Code/Codex to:
  - Follow TDD approach by default (write tests first)
  - Use blind-validator agent before marking tasks complete
  - Execute parallel tasks when possible
  - Leverage agents for validation and exploration
  - Maintain quality through automated validation gates
  - Follow taskmaster workflow best practices
- The template includes instructions for keeping CLAUDE.md and codex.md in sync if using both tools

### Step 6: Validate PRD Quality

Run automated validation checks (see `reference/validation-checklist.md`):

**Required Elements**:
- [ ] Executive summary exists (2-3 sentences)
- [ ] Problem statement includes user and business impact
- [ ] All goals have SMART metrics (specific, measurable, achievable, relevant, time-bound)
- [ ] User stories have acceptance criteria (minimum 3 per story)
- [ ] All functional requirements are testable
- [ ] Non-functional requirements include specific targets (not "fast" but "< 200ms")
- [ ] Technical considerations address architecture
- [ ] Out of scope is explicitly defined

**Taskmaster-Specific Checks**:
- [ ] Requirements have task breakdown hints
- [ ] Complexity estimates provided
- [ ] Dependencies identified for task sequencing
- [ ] Acceptance criteria are concrete (can become task completion checks)

**Quality Warnings**:
- ⚠️ If requirement has vague acceptance criteria (e.g., "should be fast")
  - Suggest: "Replace with measurable target: '< 200ms p95 response time'"
- ⚠️ If technical specs missing concrete examples
  - Suggest: "Add API request/response example or database schema"
- ⚠️ If no task breakdown hints for complex requirements
  - Suggest: "Break REQ-005 into smaller sub-tasks"

**Validation Output**:
```
✅ PRD Quality Validation

Required Elements: 8/8 ✅
Taskmaster Optimization: 4/4 ✅

⚠️ Warnings (3):
  - REQ-007: "should be performant" is vague
    Suggestion: Replace with "< 200ms response time for 95th percentile"

  - User Story 2: Only 2 acceptance criteria (minimum 3 recommended)
    Suggestion: Add edge case criterion

  - No complexity estimates for Phase 2 tasks
    Suggestion: Add estimates (Small: 2-4h, Medium: 4-8h, Large: 8-16h)

Overall Quality: GOOD (minor improvements suggested)
Safe to proceed with taskmaster task generation.
```

### Step 7: Generate Task Breakdown Hints

Based on PRD, suggest how taskmaster might break down work:

**Task Categorization**:
```
1. Setup & Infrastructure (X tasks, ~Y hours)
   - Task 1.1: [Description] (depends on: none)
   - Task 1.2: [Description] (depends on: 1.1)

2. Core Features (X tasks, ~Y hours)
   - Task 2.1: [Description] (depends on: 1.2)
   - Task 2.2: [Description] (depends on: 2.1)

3. Testing & Validation (X tasks, ~Y hours)
   - Task 3.1: Unit tests for [component]
   - Task 3.2: Integration tests for [feature]

4. Documentation & Deployment (X tasks, ~Y hours)
   - Task 4.1: API documentation
   - Task 4.2: Deployment setup
```

**Complexity Estimates**:
- Small: 2-4 hours (clear requirements, no dependencies)
- Medium: 4-8 hours (some complexity, few dependencies)
- Large: 8-16 hours (complex, multiple dependencies)
- Extra Large: 16+ hours (suggest breaking down further)

**Dependencies Map**:
```
Task Dependencies:
  1.1 (DB Schema) → 2.1 (User Model)
  2.1 (User Model) → 2.3 (User API)
  1.2 (Auth Middleware) → 2.3 (User API)

Critical Path: 1.1 → 2.1 → 2.3 → 3.2
Parallelizable: [1.2, 2.2], [3.1, 4.1]
```

Add this section to PRD as appendix or separate file (`.taskmaster/docs/task-hints.md`)

### Step 8: Initialize Taskmaster Project (MCP/CLI Integration)

**NEW STEP**: After generating the PRD, initialize taskmaster and optionally parse the PRD to generate tasks.

**Method Selection** (based on Step 2 detection):

#### Option A: MCP Integration (PREFERRED if available)

If `TASKMASTER_METHOD="MCP"`:

1. **Initialize Taskmaster Project**:
   ```
   Use mcp__task-master-ai__initialize_project with:
   - projectRoot: Current directory (absolute path)
   - yes: true (skip prompts)
   - storeTasksInGit: true
   - initGit: false (if git already initialized)
   ```

2. **Parse PRD to Generate Tasks**:
   ```
   Use mcp__task-master-ai__parse_prd with:
   - projectRoot: Current directory (absolute path)
   - input: ".taskmaster/docs/prd.md" (or prd.txt if using plain text)
   - numTasks: Estimated based on PRD complexity (10-30 for typical projects)
   - research: true (for better task generation)
   ```

3. **Expand All Tasks** (optional, ask user first):
   ```
   Use mcp__task-master-ai__expand_all with:
   - projectRoot: Current directory (absolute path)
   - research: true
   - force: false
   ```

#### Option B: CLI Integration (Fallback)

If `TASKMASTER_METHOD="CLI"`:

1. **Initialize Taskmaster Project**:
   ```bash
   taskmaster init --yes --store-tasks-in-git
   ```

2. **Parse PRD to Generate Tasks**:
   ```bash
   taskmaster parse-prd --input .taskmaster/docs/prd.md --num-tasks 15 --research
   ```

3. **Expand All Tasks** (optional, ask user first):
   ```bash
   taskmaster expand-all --research
   ```

#### Option C: Manual Instructions

If `TASKMASTER_METHOD="NONE"`:

Provide installation instructions:
```
📦 Taskmaster Not Detected

To use taskmaster AI for automated task generation:

Option 1 (RECOMMENDED): Install MCP Task-Master-AI
  - Add to Claude Code MCP settings
  - Provides seamless integration with direct function calls
  - See: https://github.com/cyanheads/task-master-ai

Option 2: Install CLI
  - npm install -g task-master-ai
  - Use command-line interface
  - See: https://github.com/cyanheads/task-master-ai

After installation, you can:
  1. Initialize: taskmaster init
  2. Parse PRD: taskmaster parse-prd --input .taskmaster/docs/prd.md
  3. Start work: taskmaster next-task
```

**User Confirmation Before Execution**:

Before running taskmaster initialization/parsing, ask:
```
"I've detected [MCP/CLI/no] taskmaster installation.

Would you like me to:
  1. Initialize taskmaster project structure
  2. Parse the PRD to auto-generate tasks
  3. Expand all tasks into subtasks (recommended)

Note: Using [MCP/CLI] method for seamless integration."
```

### Step 9: Expand High-Level Tasks into Actionable Sub-Tasks (Manual Method)

**ALTERNATIVE TO STEP 8**: If user declines automated taskmaster integration, manually expand high-level tasks into detailed, actionable sub-tasks.

**Task Expansion Process**:

For each task in the roadmap, create expanded task files in `.taskmaster/tasks/` with:

1. **Task Header**:
   ```markdown
   # TASK-001: Setup Electron + React + TypeScript Project

   **Epic:** Phase 1 - Core Infrastructure
   **Complexity:** Small (4 hours)
   **Dependencies:** None
   **Assignee:** Frontend Dev
   **Status:** Ready
   ```

2. **Detailed Sub-Tasks** (Checkbox format):
   ```markdown
   ## Sub-Tasks

   - [ ] 1. Initialize project with electron-vite
     - Command: `npm create @quick-start/electron -- screentext-pro`
     - Verify: Project folder created with src/main and src/renderer

   - [ ] 2. Configure TypeScript with strict mode
     - Create tsconfig.json with strict: true
     - Add @/ path aliases for imports
     - Test: `npm run type-check` passes

   - [ ] 3. Set up ESLint and Prettier
     - Install: @typescript-eslint/eslint-plugin, eslint-plugin-react
     - Create .eslintrc.json and .prettierrc
     - Test: `npm run lint` passes with 0 errors

   - [ ] 4. Configure hot reload
     - Verify electron main process watch mode works
     - Verify React Fast Refresh works
     - Test: Edit file, see changes without restart
   ```

3. **Implementation Guide**:
   ```markdown
   ## Implementation Guide

   ### Step 1: Initialize Project
   \`\`\`bash
   npm create @quick-start/electron -- screentext-pro
   cd screentext-pro
   npm install
   \`\`\`

   ### Step 2: Configure TypeScript
   Create `tsconfig.json`:
   \`\`\`json
   {
     "compilerOptions": {
       "target": "ES2020",
       "strict": true,
       "noImplicitAny": true,
       "paths": {
         "@/*": ["./src/*"]
       }
     }
   }
   \`\`\`

   [Continue with detailed steps...]
   ```

4. **Acceptance Criteria** (testable):
   ```markdown
   ## Acceptance Criteria

   - [x] `npm run dev` launches app successfully
   - [x] Hot reload works for both main and renderer processes
   - [x] ESLint passes with 0 warnings
   - [x] TypeScript compiles with strict mode (no errors)
   - [x] All tests pass (if applicable)
   ```

5. **Test Cases**:
   ```markdown
   ## Test Cases

   1. **Test Hot Reload**:
      - Start app with `npm run dev`
      - Edit src/renderer/App.tsx
      - Verify changes appear without manual restart

   2. **Test TypeScript Strict Mode**:
      - Add variable without type: `let x = 5;`
      - Run `npm run type-check`
      - Should error if reassigned wrong type

   3. **Test ESLint**:
      - Add unused variable
      - Run `npm run lint`
      - Should show warning
   ```

**Naming Convention**:
- File: `.taskmaster/tasks/TASK-001-setup-project.md`
- Format: `TASK-{number}-{short-slug}.md`

**Create Expanded Tasks For**:
- ALL MVP tasks (TASK-001 through TASK-039)
- At minimum, expand first sprint (TASK-001 to TASK-005)
- Include code snippets, commands, and file examples

**Why This Matters**:
- Developer can start coding immediately without additional research
- Each sub-task is completable in <1 hour (atomic)
- Clear acceptance criteria prevent misunderstandings
- Test cases ensure quality

### Step 10: Present to User

Show comprehensive summary with actionable next steps (adapt based on integration method):

**Summary Format** (adapt based on method):

#### If MCP Integration Used:
```
📄 PRD Created: .taskmaster/docs/prd.md
✅ Taskmaster Initialized: Using MCP (seamless integration)
📋 Tasks Generated: [X] tasks from PRD parsing
🔄 Tasks Expanded: All [X] tasks expanded into subtasks
🤖 CLAUDE.md Generated: Project root (TDD workflow guide)
   [+ codex.md if user requested]

📊 Overview:
  - Feature: [Name]
  - Complexity: [Simple/Medium/Complex]
  - Estimated Effort: [X tasks, ~Y hours]
  - Key Goal: [Primary success metric]

🎯 Key Requirements:
  1. [Top functional requirement]
  2. [Second functional requirement]
  3. [Third functional requirement]

🔧 Technical Highlights:
  - Architecture: [Key architectural decision]
  - Integration: [Main integration point]
  - Database: [Schema changes]

⚠️ Quality Validation:
  ✅ All required elements present
  ✅ All tasks expanded with sub-tasks
  ⚠️ 2 minor improvements suggested (see validation section in PRD)

📋 Task Breakdown:
  - Phase 1: 10 tasks expanded (TASK-001 to TASK-010)
  - Phase 2: 6 tasks expanded (TASK-011 to TASK-016)
  - Phase 3: 9 tasks expanded (TASK-017 to TASK-025)
  - Phase 4: 14 tasks expanded (TASK-026 to TASK-039)

🚀 Next Steps (MCP Method):
  1. Review PRD: .taskmaster/docs/prd.md
  2. Review CLAUDE.md: Project workflow guide (TDD, agents, validation)
  3. View tasks: Use mcp__task-master-ai__get_tasks to see all tasks
  4. Get next task: Use mcp__task-master-ai__next_task
  5. Update progress: Use mcp__task-master-ai__set_task_status
  6. View specific task: Use mcp__task-master-ai__get_task --id=[X]

📝 Open Questions ([X] remaining):
  1. [Question 1] - needs decision from [owner]
  2. [Question 2] - needs research on [topic]

🎯 Ready to Start Coding:
  ✅ Taskmaster fully initialized and integrated via MCP
  ✅ All tasks generated and expanded automatically
  ✅ Can query tasks using MCP tools
  ✅ No blockers - can start immediately
```

#### If CLI Integration Used:
```
📄 PRD Created: .taskmaster/docs/prd.md
✅ Taskmaster Initialized: Using CLI
📋 Tasks Generated: [X] tasks from PRD parsing
🔄 Tasks Expanded: All [X] tasks expanded into subtasks
🤖 CLAUDE.md Generated: Project root (TDD workflow guide)
   [+ codex.md if user requested]

📊 Overview:
  - Feature: [Name]
  - Complexity: [Simple/Medium/Complex]
  - Estimated Effort: [X tasks, ~Y hours]
  - Key Goal: [Primary success metric]

🎯 Key Requirements:
  1. [Top functional requirement]
  2. [Second functional requirement]
  3. [Third functional requirement]

🔧 Technical Highlights:
  - Architecture: [Key architectural decision]
  - Integration: [Main integration point]
  - Database: [Schema changes]

⚠️ Quality Validation:
  ✅ All required elements present
  ✅ All tasks expanded via CLI
  ⚠️ 2 minor improvements suggested (see validation section in PRD)

📋 Task Breakdown:
  - Phase 1: [X] tasks generated
  - Phase 2: [X] tasks generated
  - Phase 3: [X] tasks generated
  - Phase 4: [X] tasks generated

🚀 Next Steps (CLI Method):
  1. Review PRD: .taskmaster/docs/prd.md
  2. Review CLAUDE.md: Project workflow guide (TDD, agents, validation)
  3. View tasks: taskmaster get-tasks
  4. Get next task: taskmaster next-task
  5. Update progress: taskmaster set-task-status --id=[X] --status=in-progress
  6. View specific task: taskmaster get-task --id=[X]

📝 Open Questions ([X] remaining):
  1. [Question 1] - needs decision from [owner]
  2. [Question 2] - needs research on [topic]

🎯 Ready to Start Coding:
  ✅ Taskmaster CLI initialized and tasks generated
  ✅ Can manage tasks using CLI commands
  ✅ No blockers - can start immediately
```

#### If Manual Method Used (No Taskmaster):
```
📄 PRD Created: .taskmaster/docs/prd.md
📋 Tasks Expanded: .taskmaster/tasks/ (39 task files - manually created)
🤖 CLAUDE.md Generated: Project root (TDD workflow guide)
   [+ codex.md if user requested]

📊 Overview:
  - Feature: [Name]
  - Complexity: [Simple/Medium/Complex]
  - Estimated Effort: [X tasks, ~Y hours]
  - Key Goal: [Primary success metric]

🎯 Key Requirements:
  1. [Top functional requirement]
  2. [Second functional requirement]
  3. [Third functional requirement]

🔧 Technical Highlights:
  - Architecture: [Key architectural decision]
  - Integration: [Main integration point]
  - Database: [Schema changes]

⚠️ Quality Validation:
  ✅ All required elements present
  ✅ All tasks expanded with sub-tasks manually
  ⚠️ 2 minor improvements suggested (see validation section in PRD)

📋 Task Breakdown:
  - Phase 1: 10 tasks expanded (TASK-001 to TASK-010)
  - Phase 2: 6 tasks expanded (TASK-011 to TASK-016)
  - Phase 3: 9 tasks expanded (TASK-017 to TASK-025)
  - Phase 4: 14 tasks expanded (TASK-026 to TASK-039)

🚀 Next Steps (Manual Method):
  1. Review PRD: .taskmaster/docs/prd.md
  2. Review CLAUDE.md: Project workflow guide (TDD, agents, validation)
  3. Review first sprint tasks: .taskmaster/tasks/TASK-001-* through TASK-005-*
  4. Start TASK-001: Follow sub-tasks in .taskmaster/tasks/TASK-001-setup-project.md
  5. Mark sub-tasks complete as you go (checkbox format)
  6. Use /blind-validator before marking tasks complete
  7. When task complete, move to TASK-002

💡 Optional: Install taskmaster for better task management:
  - Option 1 (Recommended): Install MCP - see CLAUDE.md for instructions
  - Option 2: Install CLI - npm install -g task-master-ai

📝 Open Questions ([X] remaining):
  1. [Question 1] - needs decision from [owner]
  2. [Question 2] - needs research on [topic]

🎯 Ready to Start Coding:
  ✅ First task ready: .taskmaster/tasks/TASK-001-setup-project.md
  ✅ All sub-tasks defined with implementation steps
  ✅ Acceptance criteria clear
  ✅ No blockers - can start immediately

Would you like me to:
  - Refine any section?
  - Expand more tasks in detail?
  - Add more code examples?
  - Create a sprint planning document?
```

## Common Patterns

### Pattern: API-Focused PRD

For backend APIs or integration features:

1. **Detailed Endpoint Specifications**
   ```
   POST /api/v1/users

   Request:
   {
     "email": "user@example.com",
     "password": "hashed_value",
     "profile": {
       "name": "Jane Doe"
     }
   }

   Response (201):
   {
     "id": "uuid",
     "email": "user@example.com",
     "createdAt": "2025-01-15T10:30:00Z"
   }

   Error (400):
   {
     "error": "INVALID_EMAIL",
     "message": "Email format is invalid",
     "field": "email"
   }
   ```

2. **Authentication/Authorization**
   - Auth method (JWT, OAuth, API keys)
   - Token expiration and refresh
   - Permission model

3. **Rate Limiting**
   - Requests per time window
   - Throttling behavior
   - Error responses

4. **Versioning Strategy**
   - API version in URL vs header
   - Backward compatibility plan
   - Deprecation timeline

### Pattern: UI/UX-Focused PRD

For frontend features:

1. **User Flows**
   - Step-by-step user journey
   - Decision points and branches
   - Error states and recovery

2. **Component Specifications**
   - Wireframe references or descriptions
   - Interaction details (hover, click, drag)
   - Responsive behavior (mobile/tablet/desktop)

3. **Accessibility Requirements**
   - WCAG level (AA recommended)
   - Screen reader support
   - Keyboard navigation
   - Color contrast ratios

4. **Design System Integration**
   - Existing components to reuse
   - New components to create
   - Style tokens and theming

### Pattern: Data Migration PRD

For features requiring data changes:

1. **Migration Strategy**
   - Downtime required? (zero-downtime preferred)
   - Rollback plan
   - Data validation approach

2. **Schema Changes**
   ```sql
   -- Migration Up
   ALTER TABLE users ADD COLUMN phone VARCHAR(20);
   CREATE INDEX idx_users_phone ON users(phone);

   -- Migration Down
   DROP INDEX idx_users_phone;
   ALTER TABLE users DROP COLUMN phone;
   ```

3. **Data Backfill**
   - How to populate new fields for existing records
   - Batch processing approach
   - Verification queries

4. **Testing in Staging**
   - Copy production data to staging
   - Run migration
   - Validate results
   - Performance testing

### Pattern: Integration PRD

For third-party service integrations:

1. **External Service Details**
   - Service name and version
   - API documentation links
   - Authentication method
   - Rate limits and quotas

2. **Data Flow**
   - What data flows to/from service
   - Frequency (real-time, batch, polling)
   - Data transformation needed

3. **Failure Handling**
   - What if service is down?
   - Retry strategy (exponential backoff)
   - Fallback behavior
   - Circuit breaker pattern

4. **Compliance**
   - Data residency requirements
   - Privacy regulations (GDPR, CCPA)
   - Security certifications needed

## Reference

For detailed taskmaster integration guidance:
- [reference/taskmaster-integration-guide.md](reference/taskmaster-integration-guide.md)

For validation criteria and quality checks:
- [reference/validation-checklist.md](reference/validation-checklist.md)

For template structure:
- [templates/taskmaster-prd-comprehensive.md](templates/taskmaster-prd-comprehensive.md)

## Tips for Best Results

**Provide Context Upfront**:
- More detail in discovery → Better PRD
- Share constraints, dependencies, assumptions
- Mention if there are existing systems to integrate with

**Be Specific About Success**:
- Quantify goals (not "improve UX" but "increase NPS from 45 to 60")
- Define what "done" looks like
- Specify how you'll measure success

**Clarify Audience**:
- Primarily engineers → Maximum technical detail
- Mixed stakeholders → Balance technical and business
- Note if specific teams need to review

**Leverage Codebase Analysis**:
- Let me scan existing code for patterns
- I'll reference specific files and integrate consistently
- Helps with realistic technical estimates

**Iterate if Needed**:
- PRD is a living document
- Can refine sections after initial generation
- Can update as requirements evolve

**Use Validation Feedback**:
- Pay attention to warnings (vague requirements)
- Suggested improvements help taskmaster generate better tasks
- Quality gates prevent downstream problems

---

## Additional Helpful Documents to Generate

After completing the core PRD and task expansion, consider creating these additional documents in `.taskmaster/docs/`:

### 1. **sprint-planning.md**
Sprint-by-sprint breakdown with:
- Sprint goals and deliverables
- Task assignments by role
- Demo preparation checklist
- Retrospective questions

### 2. **architecture-decision-records/** (ADR directory)
Document major technical decisions:
- ADR-001: Why Electron over Tauri
- ADR-002: SQLite vs PostgreSQL for MVP
- ADR-003: DeepSeek-OCR vs Google Vision
- Format: Context, Decision, Consequences

### 3. **api-spec.yaml** (if building API)
OpenAPI/Swagger specification for all endpoints:
- Complete request/response schemas
- Authentication flows
- Error codes
- Examples

### 4. **test-plan.md**
Comprehensive testing strategy:
- Unit test coverage goals
- Integration test scenarios
- E2E test flows
- Performance benchmarks
- Security test checklist

### 5. **deployment-guide.md**
Step-by-step deployment instructions:
- Environment setup
- Build process
- Configuration management
- Rollback procedures
- Monitoring setup

### 6. **onboarding-guide.md**
For new developers joining the project:
- Getting started (clone, install, run)
- Code organization overview
- Development workflow
- Code review guidelines
- Where to ask for help

### 7. **changelog.md**
Track all changes during development:
- Version numbers
- Features added
- Bugs fixed
- Breaking changes

### 8. **metrics-dashboard-spec.md**
Define what metrics to track:
- User analytics events
- Performance metrics
- Business KPIs
- Alerting thresholds

**When to Generate These**:
- ADRs: As you make major technical decisions
- API spec: If building API (before implementation)
- Test plan: Before Sprint 2 (when code starts)
- Deployment guide: Sprint 11-12 (before launch)
- Onboarding: After Sprint 6 (mid-point)
- Changelog: Start from Day 1
- Metrics spec: Before Sprint 12 (analytics integration)

---

## Proactive Suggestions During PRD Creation

While generating the PRD, proactively offer to:

1. **Research competitors** if not provided
   - "I can research top 5 competitors in this space. Should I?"

2. **Generate user personas** from basic user descriptions
   - "Would you like detailed user personas with demographics, pain points, and goals?"

3. **Calculate market sizing** (TAM/SAM/SOM)
   - "Should I estimate the total addressable market for this product?"

4. **Create feature comparison matrix**
   - "Want a feature matrix comparing your solution to competitors?"

5. **Design database schema** from requirements
   - "I can draft the complete database schema with all relationships. Proceed?"

6. **Draft API endpoints** from user stories
   - "Should I generate the full API specification with endpoints?"

7. **Suggest tech stack alternatives**
   - "I've chosen X, but alternatives are Y and Z. Want detailed comparison?"

8. **Estimate pricing strategy**
   - "Based on competitors and value, I can suggest pricing tiers. Interested?"

9. **Identify technical risks**
   - "I see 3 potential technical risks. Want risk mitigation plan?"

10. **Create timeline with milestones**
    - "Should I create a Gantt chart-style timeline in markdown?"

---

**Remember**: A comprehensive PRD is the foundation of successful implementation. Planning is 95% of the work. Take time to get it right, expand all tasks with actionable sub-tasks, and you'll have a clear roadmap from idea to production.
