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

Check for existing taskmaster setup:

```bash
# Check if .taskmaster/ exists
if [ -d ".taskmaster" ]; then
  # Check for existing PRD
  if [ -f ".taskmaster/docs/prd.md" ]; then
    Ask: "Found existing prd.md. Update it or create new version?"
  fi
fi

# Check if taskmaster CLI installed (optional, for later integration)
which taskmaster
```

**Actions**:
- If `.taskmaster/` exists → Respect existing structure, ask before overwriting
- If no `.taskmaster/` → Will create it in Step 5
- If taskmaster CLI not installed → Note for user (non-blocking)

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

### Step 8: Present to User

Show comprehensive summary with actionable next steps:

**Summary Format**:
```
📄 PRD Created: .taskmaster/docs/prd.md

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
  ⚠️ 2 minor improvements suggested (see validation section in PRD)

📋 Suggested Task Breakdown:
  - Phase 1: [X tasks] (foundation)
  - Phase 2: [Y tasks] (core features)
  - Phase 3: [Z tasks] (testing & polish)

🚀 Next Steps:
  1. Review PRD: .taskmaster/docs/prd.md
  2. Install taskmaster CLI: npm install -g task-master-ai (if not installed)
  3. Initialize taskmaster: taskmaster init
  4. Generate tasks: taskmaster generate
  5. Start implementation: taskmaster start

📝 Open Questions ([X] remaining):
  1. [Question 1] - needs decision from [owner]
  2. [Question 2] - needs research on [topic]

Would you like me to:
  - Refine any section?
  - Add more detail to specific requirements?
  - Adjust complexity estimates?
  - Initialize taskmaster now? (if CLI available)
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

**Remember**: A comprehensive PRD is the foundation of successful implementation. Planning is 95% of the work. Take time to get it right, and taskmaster will generate high-quality actionable tasks.
