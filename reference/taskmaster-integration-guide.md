# Taskmaster Integration Guide

Complete guide for optimizing PRDs for taskmaster AI task generation.

## Table of Contents

1. [What is Taskmaster](#what-is-taskmaster)
2. [Why PRD Quality Matters](#why-prd-quality-matters)
3. [Writing for Task Generation](#writing-for-task-generation)
4. [Task Breakdown Best Practices](#task-breakdown-best-practices)
5. [Common Patterns](#common-patterns)
6. [Troubleshooting](#troubleshooting)

---

## What is Taskmaster

Taskmaster AI is a task management system designed for AI-driven development workflows ("vibe coding").

**Core Concept:**
- You provide a comprehensive PRD
- Taskmaster breaks it into actionable tasks
- AI agents implement tasks one by one
- Better PRD = Better tasks = Better outcomes

**Key Features:**
- Automatic task generation from PRDs
- Dependency tracking
- Progress monitoring
- Integration with AI coding tools

**Why This Matters:**
> "Planning is 95% of the work with vibe coding"

A vague PRD generates vague tasks → Poor implementation
A detailed PRD generates specific tasks → Successful implementation

---

## Why PRD Quality Matters

### The Task Generation Chain

```
PRD Quality → Task Quality → Implementation Quality → Project Success

Good PRD:
  ✅ "API response time must be < 200ms for 95th percentile"
  → Task: "Optimize database queries to achieve < 100ms query time"
  → Implementation: Specific, measurable, achievable

Bad PRD:
  ❌ "API should be fast"
  → Task: "Make API faster"
  → Implementation: Vague, unmeasurable, unclear
```

### What Taskmaster Needs

**To generate good tasks, taskmaster needs:**

1. **Clear Requirements**
   - Each requirement is atomic (one thing)
   - Testable (can verify completion)
   - Specific (no vague language)

2. **Acceptance Criteria**
   - Concrete conditions that must be true
   - Becomes task completion criteria
   - Measurable and verifiable

3. **Technical Details**
   - API specifications with examples
   - Database schemas
   - Integration points
   - Error handling approach

4. **Dependencies**
   - What must be built first
   - What can be parallel
   - External dependencies

5. **Complexity Estimates**
   - Helps taskmaster schedule work
   - Identifies Large tasks to break down
   - Sets realistic expectations

---

## Writing for Task Generation

### Requirement Format

**Best Format for Taskmaster:**

```markdown
#### REQ-001: [Clear, Descriptive Title]

**Description:** [What the system must do, in detail]

**Acceptance Criteria:**
- [ ] [Specific, testable criterion 1]
- [ ] [Specific, testable criterion 2]
- [ ] [Specific, testable criterion 3]
- [ ] [Edge case criterion]
- [ ] [Error handling criterion]

**Technical Specification:**
[Code examples, API schemas, database schemas]

**Task Breakdown:**
- Implement [component]: Small (2-4h)
- Add [feature]: Medium (4-8h)
- Test [functionality]: Small (2-4h)

**Dependencies:** [None | REQ-XXX | External service]
```

**Why This Works:**
- Title → Task name
- Description → Task description
- Acceptance criteria → Completion criteria
- Technical spec → Implementation guidance
- Task breakdown → Subtasks
- Dependencies → Task sequencing

### Acceptance Criteria Best Practices

**Good Acceptance Criteria:**
```
✅ "POST /api/users returns 201 status code with user ID"
✅ "Invalid email returns 400 with error message 'INVALID_EMAIL'"
✅ "Password must be hashed using bcrypt with cost factor 12"
✅ "API response time < 200ms for 95th percentile under 1000 req/s load"
```

**Bad Acceptance Criteria:**
```
❌ "API should work correctly"
❌ "Handle errors properly"
❌ "Be secure"
❌ "Perform well"
```

**Formula:**
```
[Action] [Specific Condition] [Measurable Outcome]

Examples:
- POST /api/users [Action]
- with valid data [Condition]
- returns 201 status [Outcome]

- Password [Action]
- during user registration [Condition]
- must be hashed with bcrypt cost 12 [Outcome]
```

### Technical Specifications

**API Endpoints:**

Always include:
- HTTP method and path
- Request headers
- Request body (JSON example)
- Success response (status + body)
- Error responses (all cases)

```markdown
### Endpoint: Create User

```
POST /api/v1/users

Headers:
  Content-Type: application/json
  Authorization: Bearer {token}

Request:
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "profile": {
    "firstName": "Jane",
    "lastName": "Doe"
  }
}

Response (201 Created):
{
  "id": "uuid-1234",
  "email": "user@example.com",
  "createdAt": "2025-01-15T10:30:00Z"
}

Error (400 Bad Request):
{
  "error": "INVALID_EMAIL",
  "message": "Email format is invalid",
  "field": "email"
}

Error (409 Conflict):
{
  "error": "EMAIL_EXISTS",
  "message": "User with this email already exists"
}
```\
```

**Database Schemas:**

Always include:
- Table name
- All columns with types
- Constraints (NOT NULL, UNIQUE, etc.)
- Indexes
- Foreign keys

```markdown
### Database Schema

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  first_name VARCHAR(100),
  last_name VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);
```\
```

---

## Task Breakdown Best Practices

### Task Sizing

**Small (2-4 hours):**
- Clear requirements
- No external dependencies
- Minimal complexity
- Examples:
  - Add database column
  - Create simple API endpoint
  - Write unit tests for one function

**Medium (4-8 hours):**
- Moderate complexity
- Few dependencies
- Some unknowns
- Examples:
  - Implement authentication middleware
  - Create UI component with state
  - Integration test for feature

**Large (8-16 hours):**
- High complexity
- Multiple dependencies
- Significant unknowns
- Examples:
  - Complete login flow (UI + API + DB)
  - Payment integration
  - Complex algorithm implementation

**Extra Large (16+ hours):**
- Should be broken down further
- Taskmaster will struggle with these
- Split into multiple Medium tasks

### Dependency Mapping

**Format:**
```
Task 1 (Foundation) → Task 2 (Core) → Task 3 (Enhancement)
                   ↘ Task 4 (Alternative) ↗

Dependencies:
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 1
- Task 3 also depends on Task 4

Critical Path: Task 1 → Task 2 → Task 3
Parallelizable: Task 2 and Task 4 (both depend only on Task 1)
```

**Why This Matters:**
- Taskmaster schedules tasks based on dependencies
- Parallel tasks can be worked on simultaneously
- Critical path determines minimum timeline

### Implementation Phases

**Best Practice:** Group related tasks into phases

```markdown
### Phase 1: Foundation (Week 1)
Goal: Database and core services ready

Tasks:
- Task 1.1: Create database schema
- Task 1.2: Implement data models
- Task 1.3: Create base API structure

Validation: Can create/read records from database

---

### Phase 2: Core Features (Week 2-3)
Goal: Main functionality working

Tasks:
- Task 2.1: Implement authentication
- Task 2.2: Build user management APIs
- Task 2.3: Create dashboard UI

Validation: User can login and access dashboard

---

### Phase 3: Enhancements (Week 4)
Goal: Polish and optimization

Tasks:
- Task 3.1: Add error handling
- Task 3.2: Performance optimization
- Task 3.3: Comprehensive testing

Validation: All tests passing, performance targets met
```

**Benefits:**
- Clear milestones
- Validation checkpoints
- Logical progression
- Easier to track progress

---

## Common Patterns

### Pattern 1: CRUD API Feature

**PRD Structure:**
```markdown
## Functional Requirements

### REQ-001: Create [Resource]
- API: POST /api/[resource]
- Input validation
- Database insertion
- Response format

Task Breakdown:
- Create database schema (Small, 2h)
- Implement create endpoint (Medium, 5h)
- Add validation middleware (Small, 3h)
- Write tests (Small, 3h)

Dependencies: None

---

### REQ-002: Read [Resource]
- API: GET /api/[resource]/:id
- Error handling (404 if not found)
- Response format

Task Breakdown:
- Implement get endpoint (Small, 3h)
- Add caching (Small, 2h)
- Write tests (Small, 2h)

Dependencies: REQ-001 (database must exist)

---

### REQ-003: Update [Resource]
Task Breakdown: ...
Dependencies: REQ-001, REQ-002

---

### REQ-004: Delete [Resource]
Task Breakdown: ...
Dependencies: REQ-001, REQ-002
```

**Taskmaster Output:**
```
Phase 1: Create & Read
  - Task 1.1: Database schema
  - Task 1.2: Create endpoint
  - Task 1.3: Validation middleware
  - Task 1.4: Get endpoint
  - Task 1.5: Caching
  - Tasks 1.6-1.7: Tests

Phase 2: Update & Delete
  - Task 2.1: Update endpoint
  - Task 2.2: Delete endpoint
  - Tasks 2.3-2.4: Tests
```

### Pattern 2: UI Component Feature

**PRD Structure:**
```markdown
## User Story

As a user, I want to [action] so that I can [benefit].

Acceptance Criteria:
- [ ] Component renders with correct data
- [ ] User can [interact]
- [ ] Component handles loading state
- [ ] Component handles error state
- [ ] Component is keyboard accessible
- [ ] Component is responsive (mobile/desktop)

## Technical Specification

Component: [ComponentName]
Props: [List props with types]
State: [Internal state if any]
API calls: [Which endpoints]

File structure:
- src/components/[Component]/index.tsx
- src/components/[Component]/[Component].module.css
- src/components/[Component]/[Component].test.tsx

## Task Breakdown

- Create component skeleton (Small, 2h)
- Implement data fetching (Small, 3h)
- Add UI elements (Medium, 6h)
- Implement interactions (Medium, 5h)
- Add loading/error states (Small, 3h)
- Accessibility testing (Small, 2h)
- Responsive design (Small, 3h)
- Write tests (Small, 4h)

Total: ~28 hours across 8 tasks
```

### Pattern 3: Integration Feature

**PRD Structure:**
```markdown
## External Service Integration

Service: [Name]
Purpose: [What it does]
Documentation: [Link]

## Requirements

### REQ-001: Service Authentication
- OAuth 2.0 flow
- Token storage and refresh
- Error handling

Task Breakdown:
- Implement OAuth flow (Large, 10h)
- Add token refresh logic (Medium, 5h)
- Error handling (Small, 3h)

---

### REQ-002: Data Synchronization
- Fetch data from service
- Transform to our format
- Store in database

Task Breakdown:
- Implement fetch logic (Medium, 6h)
- Data transformation (Medium, 5h)
- Database storage (Small, 3h)

---

### REQ-003: Failure Handling
- What if service is down?
- Retry strategy
- Fallback behavior

Task Breakdown:
- Circuit breaker pattern (Medium, 6h)
- Retry logic with exponential backoff (Small, 4h)
- Fallback implementation (Small, 3h)

Dependencies:
- REQ-002 depends on REQ-001 (auth first)
- REQ-003 depends on REQ-002 (failures happen during sync)
```

---

## Troubleshooting

### Issue: Taskmaster Generates Vague Tasks

**Symptom:**
```
Task: "Implement feature X"
Task: "Make API work"
Task: "Fix bugs"
```

**Root Cause:** PRD requirements are too vague

**Solution:** Add specific acceptance criteria and technical details

**Before:**
```
REQ-001: User authentication
Description: Users should be able to login
```

**After:**
```
REQ-001: User Authentication via JWT

Description: System must authenticate users via email/password and return JWT token valid for 24 hours.

Acceptance Criteria:
- [ ] POST /api/auth/login accepts email and password
- [ ] Returns JWT token if credentials valid
- [ ] Token expires after 24 hours
- [ ] Invalid credentials return 401 with error message
- [ ] Successful login tracked in audit log

Technical Specification:
- JWT signed with RS256 algorithm
- Token contains: user_id, email, exp
- Passwords hashed with bcrypt (cost 12)
```

### Issue: Tasks Have Wrong Dependencies

**Symptom:** Taskmaster tries to run Task B before Task A, but B depends on A

**Root Cause:** Dependencies not documented in PRD

**Solution:** Explicitly state dependencies for each requirement

```markdown
### REQ-003: User Dashboard API

**Dependencies:**
- REQ-001: Authentication (users must be authenticated to access dashboard)
- REQ-002: User model (dashboard displays user data)

Task Breakdown:
- Implement dashboard endpoint (Medium, 6h)
  Dependencies: REQ-001, REQ-002
```

### Issue: Tasks Are Too Large

**Symptom:** Taskmaster creates tasks estimated at 20+ hours

**Root Cause:** Requirements are too broad

**Solution:** Break requirements into smaller, atomic pieces

**Before:**
```
REQ-001: Complete user management system
```

**After:**
```
REQ-001: User registration
REQ-002: User login
REQ-003: User profile management
REQ-004: Password reset
REQ-005: Email verification
```

### Issue: Duplicate Tasks Generated

**Symptom:** Taskmaster creates multiple tasks for the same thing

**Root Cause:** Requirements overlap or repeat

**Solution:** Review PRD for duplicate requirements, consolidate

**Check for:**
- Same API endpoint in multiple requirements
- Same database table in multiple places
- Repeated acceptance criteria

---

## Checklist for Taskmaster-Ready PRD

Before generating tasks, verify:

**Requirements:**
- [ ] Each requirement has unique ID (REQ-001, REQ-002, ...)
- [ ] Each requirement is atomic (does one thing)
- [ ] All requirements have acceptance criteria (minimum 3 per requirement)
- [ ] Acceptance criteria are specific and testable
- [ ] No vague language ("fast", "good", "user-friendly")

**Technical Details:**
- [ ] API endpoints have request/response examples
- [ ] Database schemas include all columns, types, constraints
- [ ] Integration points documented with service details
- [ ] Error handling approach specified

**Task Breakdown:**
- [ ] Each requirement suggests task breakdown
- [ ] Tasks are sized (Small/Medium/Large)
- [ ] Task dependencies identified
- [ ] Implementation phases defined

**Validation:**
- [ ] Each phase has validation checkpoint
- [ ] Success criteria defined for each phase
- [ ] Testing strategy included

**If all checked:** Your PRD is ready for taskmaster! ✅

---

## Additional Resources

- Taskmaster Documentation: https://docs.task-master.dev/
- Taskmaster GitHub: https://github.com/eyaltoledano/claude-task-master
- Best Practices: https://docs.task-master.dev/getting-started/best-practices

---

**Remember:** The quality of your PRD directly determines the quality of generated tasks. Invest time in a comprehensive, detailed PRD, and taskmaster will generate high-quality, actionable tasks that lead to successful implementation.
