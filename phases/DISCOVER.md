# Phase: Discovery --- Brainstorming-Driven

## The One Rule

**Invoke superpowers:brainstorming for discovery. Intercept before it chains to writing-plans --- we control the exit.**

## Checklist

Copy into your response:
```
DISCOVERY CHECKLIST:
- [ ] Brainstorming invoked with user's goal
- [ ] Discovery questions completed (adaptive, one at a time)
- [ ] Design approved by user
- [ ] Summary captured for GENERATE phase
```

## How Discovery Works

1. Take the user's goal/description from skill invocation
2. Invoke `superpowers:brainstorming` with the goal as input
3. Brainstorming runs its adaptive question flow (one Q at a time, domain-agnostic)
4. **INTERCEPT POINT**: When brainstorming is ready to chain to writing-plans, STOP.
   - Do NOT let it invoke writing-plans
   - Capture the brainstorm output (design, requirements, decisions)
   - Present the summary to the user for approval

## User Approval Gate

After brainstorming completes, present:

```
Discovery Complete:
  Goal: [one sentence]
  Audience: [who it's for]
  Approach: [proposed solution]
  Key decisions: [list]
  Constraints: [known limitations]

Proceed to generate spec? (or refine further)
```

If user says "refine" --- ask what to change, update, re-present.
If user approves --- capture this as the discovery output and proceed to GENERATE.

## Smart Defaults

If brainstorming produces thin answers, fill gaps with reasonable assumptions:
- Target: small team (< 10 users) unless specified
- Timeline: MVP in 4-6 weeks
- Tech stack: determined by requirements
- Scale: moderate (hundreds, not millions)

Document assumptions in the spec during GENERATE.

## Constraint Extraction (MANDATORY before proceeding)

Before moving to GENERATE, explicitly extract and list all constraints mentioned during discovery:

```
CONSTRAINTS CAPTURED:
- Tech stack: [e.g., "must use Python", "React frontend", "no new dependencies"]
- Timeline: [e.g., "MVP in 2 weeks", "no deadline"]
- Team: [e.g., "solo developer", "3-person team"]
- Budget: [e.g., "free tier only", "$500/month max"]
- Integration: [e.g., "must work with existing Postgres DB", "connects to Stripe"]
- Regulatory: [e.g., "HIPAA compliant", "GDPR", "none specified"]
- Domain-specific: [e.g., "authorized pentest scope: 10.0.0.0/24 only", "learning goal: intermediate level"]
```

Present this list to the user alongside the discovery summary. These constraints MUST be passed to GENERATE --- they inform spec content, task decomposition depth, and acceptance criteria. If a constraint is mentioned in discovery but missing from the spec, it's a bug.

## Scope Calibration

Infer project scale from discovery answers and set decomposition guidance:

| Scale | Signal | Task Cap | Subtask Depth |
|-------|--------|----------|---------------|
| Solo/hobby | "just me", "side project", "learning" | 8-12 tasks | 2-3 subtasks each |
| Team/startup | "small team", "MVP", "product" | 12-20 tasks | 3-5 subtasks each |
| Enterprise | "compliance", "multiple teams", "platform" | 20-30 tasks | 5-8 subtasks each |

Pass the scale classification to GENERATE so task count is calibrated, not arbitrary.

## Evidence Gate

**Gate: User has approved the discovery output. Constraints extracted and listed. Scale classified. Proceed to GENERATE phase.**
