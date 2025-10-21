# PRD Validation Checklist

Automated and manual checks to ensure PRD quality before taskmaster task generation.

## Automated Validation Checks

These checks are run automatically by the skill before presenting the PRD to the user.

### Required Elements (Must Pass All)

- [ ] **Executive Summary exists**
  - Check: Document contains "## Executive Summary" section
  - Check: Executive summary is 2-4 sentences (50-200 words)
  - Failure: Add executive summary

- [ ] **Problem Statement includes user impact**
  - Check: Contains "User Impact" or "Who is affected"
  - Check: Describes specific pain points
  - Failure: Add user impact section to problem statement

- [ ] **Problem Statement includes business impact**
  - Check: Contains "Business Impact" or quantifiable cost
  - Check: Mentions revenue, costs, or strategic importance
  - Failure: Add business impact to problem statement

- [ ] **All goals have SMART metrics**
  - Check: Each goal has: Metric, Baseline, Target, Timeframe
  - Check: Metrics are measurable (numbers, percentages, counts)
  - Failure: Convert vague goals to SMART format

- [ ] **User stories have acceptance criteria**
  - Check: Each user story has "Acceptance Criteria:" section
  - Check: Minimum 3 criteria per story
  - Check: Criteria are specific (not vague)
  - Failure: Add concrete acceptance criteria

- [ ] **All functional requirements are testable**
  - Check: Each requirement has measurable acceptance criteria
  - Check: No vague language ("fast", "good", "user-friendly")
  - Failure: Make requirements specific and testable

- [ ] **Non-functional requirements have specific targets**
  - Check: Performance metrics have numbers (e.g., "< 200ms")
  - Check: Security requirements specify methods (e.g., "bcrypt cost 12")
  - Failure: Replace vague NFRs with specific targets

- [ ] **Technical considerations address architecture**
  - Check: Contains architecture description or diagram
  - Check: Mentions integration points or dependencies
  - Failure: Add architectural considerations

- [ ] **Out of scope is explicitly defined**
  - Check: Contains "## Out of Scope" section
  - Check: Lists at least 1 item
  - Failure: Define what's NOT being built

---

### Taskmaster-Specific Checks (Should Pass Most)

- [ ] **Requirements have task breakdown hints**
  - Check: Requirements include "Task Breakdown:" section
  - Check: Tasks have complexity estimates (Small/Medium/Large)
  - Warning: Add task breakdowns for better taskmaster output

- [ ] **Complexity estimates provided**
  - Check: Tasks include time estimates (e.g., "Medium (4-8h)")
  - Check: Estimates are realistic ranges, not exact times
  - Warning: Add complexity estimates to help taskmaster schedule

- [ ] **Dependencies identified for task sequencing**
  - Check: Requirements list dependencies (or "None")
  - Check: Dependencies reference other requirements (REQ-XXX)
  - Warning: Document dependencies for proper task ordering

- [ ] **Acceptance criteria are concrete**
  - Check: Criteria can be directly converted to task completion checks
  - Check: Each criterion is verifiable (not subjective)
  - Warning: Make criteria more specific for better tasks

---

## Quality Warnings

These warnings don't block PRD creation but suggest improvements.

### Vague Language Warnings

**Pattern:** Detect vague adjectives/adverbs

- ⚠️ **"should be fast"**
  - Suggestion: Replace with specific metric (e.g., "< 200ms p95")

- ⚠️ **"should be performant"**
  - Suggestion: Define performance target (throughput, latency, etc.)

- ⚠️ **"should be user-friendly"**
  - Suggestion: Define UX criteria (click count, time to complete, etc.)

- ⚠️ **"should be secure"**
  - Suggestion: Specify security controls (authentication method, encryption, etc.)

- ⚠️ **"should be scalable"**
  - Suggestion: Define scale requirements (users, requests/sec, data volume)

- ⚠️ **"should work well"**
  - Suggestion: Define success criteria objectively

**Auto-Detection:**
```
Search for patterns:
- "fast", "quick", "slow"
- "good", "bad", "poor"
- "user-friendly", "easy", "simple"
- "secure", "safe"
- "scalable", "flexible"
- "performant", "efficient"

Without accompanying numbers or specific criteria
```

---

### Missing Detail Warnings

- ⚠️ **Technical spec missing code examples**
  - Pattern: "Technical Specification:" section exists but no code blocks
  - Suggestion: Add API request/response, database schema, or code example

- ⚠️ **No complexity estimates for tasks**
  - Pattern: Task breakdown exists but no (Small/Medium/Large) labels
  - Suggestion: Add complexity estimates for taskmaster scheduling

- ⚠️ **User story has < 3 acceptance criteria**
  - Pattern: Acceptance criteria list has only 1-2 items
  - Suggestion: Add more criteria (edge cases, error handling)

- ⚠️ **No validation checkpoints defined**
  - Pattern: Missing "Validation Checkpoints" section
  - Suggestion: Add checkpoints for each implementation phase

---

### Insufficient Detail Warnings

- ⚠️ **API endpoint missing error responses**
  - Pattern: API spec shows only success response
  - Suggestion: Document all error cases (400, 401, 404, 500, etc.)

- ⚠️ **Database schema missing indexes**
  - Pattern: CREATE TABLE exists but no CREATE INDEX
  - Suggestion: Add indexes for foreign keys and query columns

- ⚠️ **No test strategy defined**
  - Pattern: Missing "Testing Strategy" section in technical considerations
  - Suggestion: Define unit, integration, and E2E testing approach

- ⚠️ **No error handling specified**
  - Pattern: No mention of error handling in technical spec
  - Suggestion: Document error handling approach and fallback behavior

---

## Validation Output Format

```
✅ PRD Quality Validation

Required Elements: 9/9 ✅
Taskmaster Optimization: 4/4 ✅

Overall Quality: EXCELLENT
Ready for taskmaster task generation.
```

Or with warnings:

```
✅ PRD Quality Validation

Required Elements: 9/9 ✅
Taskmaster Optimization: 3/4 ⚠️

⚠️ Warnings (4):

1. REQ-007: "should be performant" is vague
   Location: Functional Requirements > REQ-007
   Suggestion: Replace with "< 200ms response time for 95th percentile"

2. User Story 2: Only 2 acceptance criteria
   Location: User Stories > Story 2
   Suggestion: Minimum 3 recommended. Add edge case criterion.

3. No complexity estimates for Phase 2 tasks
   Location: Implementation Roadmap > Phase 2
   Suggestion: Add estimates (Small: 2-4h, Medium: 4-8h, Large: 8-16h)

4. API endpoint /api/users missing error responses
   Location: Technical Considerations > API Specifications
   Suggestion: Document 400 (validation), 401 (auth), 409 (conflict) responses

Overall Quality: GOOD (minor improvements suggested)
Safe to proceed with taskmaster task generation.

Would you like to:
  1. Proceed with current PRD
  2. Let me fix warnings automatically
  3. Review and fix warnings manually
```

---

## Manual Validation Checklist

For human review before finalizing PRD:

### Content Quality

- [ ] **Problem is clearly articulated**
  - Can someone unfamiliar with the project understand the problem?
  - Is the user pain point specific and relatable?
  - Is there data or evidence supporting the problem?

- [ ] **Solution makes sense**
  - Does the proposed solution actually solve the problem?
  - Is it the simplest solution that could work?
  - Are there obvious alternatives considered?

- [ ] **Goals are achievable**
  - Are targets realistic given timeline and resources?
  - Are metrics actually measurable with available tools?
  - Do goals align with business strategy?

### Technical Accuracy

- [ ] **Architecture is sound**
  - Does the proposed architecture fit existing system?
  - Are integration points correctly identified?
  - Are there technical red flags or risks?

- [ ] **Estimates are realistic**
  - Do task estimates account for complexity?
  - Is there buffer for unknowns?
  - Have similar projects taken longer?

- [ ] **Dependencies are complete**
  - Are all technical dependencies identified?
  - Are team/resource dependencies noted?
  - Are external dependencies (APIs, services) documented?

### Completeness

- [ ] **All user scenarios covered**
  - Happy path
  - Error scenarios
  - Edge cases
  - Recovery flows

- [ ] **All stakeholders addressed**
  - Engineering (technical details)
  - Product (business value)
  - Design (UX requirements)
  - QA (testing criteria)
  - Support (documentation needs)

- [ ] **Nothing ambiguous**
  - No "TBD" or "TODO" in final PRD
  - All open questions have owners and deadlines
  - Success criteria are clear

### Taskmaster Readiness

- [ ] **Can taskmaster generate tasks?**
  - Are requirements atomic enough?
  - Is detail level sufficient?
  - Are task boundaries clear?

- [ ] **Will tasks be actionable?**
  - Can an engineer pick up a task and implement it?
  - Is enough context provided?
  - Are acceptance criteria clear?

- [ ] **Will task scheduling work?**
  - Are dependencies correct?
  - Can tasks be parallelized appropriately?
  - Is the critical path identified?

---

## Validation Scoring

**Score Calculation:**

```
Required Elements (60 points):
  - 9 required checks × 5 points each = 45 points
  - 4 taskmaster checks × 3 points each = 12 points
  - Vague language penalty: -1 point per instance (max -5)
  - Missing detail penalty: -1 point per instance (max -5)

Total: /60 points

Grading:
  55-60 points: EXCELLENT ✅ (91-100%)
  50-54 points: GOOD ⚠️ (83-90%)
  45-49 points: ACCEPTABLE ⚠️⚠️ (75-82%)
  < 45 points: NEEDS WORK ❌ (< 75%)
```

**EXCELLENT (91-100%):**
- All required elements present
- All taskmaster optimizations included
- 0-1 minor warnings
- Ready for immediate use

**GOOD (83-90%):**
- All required elements present
- Most taskmaster optimizations included
- 2-4 minor warnings
- Safe to use, improvements recommended

**ACCEPTABLE (75-82%):**
- All required elements present
- Some taskmaster optimizations missing
- 5-8 warnings
- Usable but may need refinement

**NEEDS WORK (< 75%):**
- Missing required elements
- Significant taskmaster gaps
- 9+ warnings or critical issues
- Should be refined before use

---

## Example Validation Run

**Input PRD:** User authentication with 2FA

**Automated Checks:**
```
Required Elements:
  ✅ Executive Summary exists (78 words)
  ✅ Problem Statement includes user impact
  ✅ Problem Statement includes business impact
  ✅ Goals have SMART metrics (3/3 goals)
  ✅ User stories have acceptance criteria (5 stories, avg 4.2 criteria)
  ✅ Functional requirements are testable (12/12 requirements)
  ✅ Non-functional requirements have targets (Performance: ✅, Security: ✅, Scalability: ✅)
  ✅ Technical considerations address architecture
  ✅ Out of scope defined (5 items)

Taskmaster Checks:
  ✅ Requirements have task breakdowns (12/12)
  ✅ Complexity estimates provided (26 tasks estimated)
  ✅ Dependencies identified (12/12 requirements)
  ✅ Acceptance criteria are concrete

Warnings:
  ⚠️ REQ-007: "should be fast enough" detected
     Suggestion: Replace with "< 200ms response time"

  ⚠️ Phase 2: No validation checkpoint defined
     Suggestion: Add checkpoint criteria

Score: 58/60 points (97%)
Grade: EXCELLENT ✅

Result: Ready for taskmaster task generation!
```

---

## Continuous Validation

**During PRD Development:**
- Run validation after each major section completed
- Fix issues immediately (easier than batch fixing)
- Use warnings as learning guide

**Before Finalizing:**
- Run full validation suite
- Address all required element failures
- Review and address warnings
- Score should be ≥ 50/60 (GOOD)

**After Taskmaster Generation:**
- Review generated tasks for quality
- If tasks are vague, trace back to PRD
- Improve PRD and regenerate tasks

---

**Remember:** Validation is not just a checklist - it's quality assurance. A well-validated PRD leads to high-quality tasks, which leads to successful implementation. Take the time to validate thoroughly.
