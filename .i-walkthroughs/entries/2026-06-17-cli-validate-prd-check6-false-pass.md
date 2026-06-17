---
id: 2026-06-17-cli-validate-prd-check6-false-pass
schema_version: 1
repo: anombyte93/prd-taskmaster
branch: walkthrough/atlas-cli-surfaces
commit: pending
date: 2026-06-17
route: "cli:validate-prd"
screen_purpose: "Give a user a fast, honest, point-scored verdict on whether a PRD is complete enough to parse into a trustworthy task graph."
mode: auto
viewport: cli
device_class: desktop
severity: P2
category: trust
root_cause: "Check 6 ran VAGUE_PATTERN.findall over an empty string when no requirements section existed; an empty match list read as 'no vague terms' → passed:true + 'All requirements are specific'."
assumption_trap: "no-vague-terms == requirements-are-testable (true only when requirements actually exist)."
reusable_rule: "A presence/quality check over an ABSENT section must fail-closed, never pass-and-assert-quality on emptiness."
evidence_method: [code]
files_changed: ["prd_taskmaster/validation.py", "tests/core/test_validation.py"]
first_check: {result: fail, metric: "empty PRD → check6.passed=true, detail='All requirements are specific', checks_passed=3, score=13", evidence_ref: "live: python3 script.py validate-prd --input /tmp/wt_empty.md (pre-fix)"}
second_check: {result: pass, metric: "empty PRD → check6.passed=false, detail='No requirements section found', checks_passed=2, score=8, grade=NEEDS_WORK", evidence_ref: "live post-fix run + pytest -k 'validate_empty_prd or check6_fails_closed'", regression_scan: pass}
regression_checks: ["sample_prd (real requirements) still passes check6", "thorough PRD still 57/57 EXCELLENT exit 0", "grade boundary tests", "full offline suite tests/core+tests/plugin"]
verdict: resolved
status: verified
approval: pending
evidence_dir: evidence/2026-06-17-cli-validate-prd-check6-false-pass
tags: [validate-prd, honesty, fail-closed, vacuous-pass]
related: []
title: "validate-prd Check 6 falsely passed + claimed specificity on a PRD with zero requirements"
---

## Lesson (TL;DR)
`validate-prd` Check 6 ("Functional requirements are testable") passed AND printed "All requirements are specific" on a PRD that had no requirements section at all — a positively false claim about content that does not exist. Root cause: a vague-term scan over an empty string returns no matches, which the code read as success. A presence/quality check over an absent section must fail-closed.

## Screen & Purpose
Surface `cli:validate-prd` (13-check PRD quality gate, `validation.py:run_validate_prd`). Soul purpose: an honest, point-scored verdict on PRD completeness. Headless/CLI; evidence = live runs + unit tests.

## Issue (first check)
Live, pre-fix, on a PRD containing only a title + Overview (zero requirements):
`check 6 → passed:true, detail:"All requirements are specific"`; `checks_passed:3, score:13`. The detail makes an affirmative specificity claim about requirements that are absent. (The final grade NEEDS_WORK was already correct; the defect is the per-check honesty + an inflated checks_passed.)

## Root Cause
`reqs_section` was empty; `VAGUE_PATTERN.findall("")==[]` → `passed = len([])==0 = True` and the else-branch detail "All requirements are specific" fired. The check never distinguished "present and specific" from "absent".

## Fix
`validation.py`: when `reqs_section.strip()` is empty, emit `passed:false, detail:"No requirements section found"` (fail-closed); otherwise the original vague-term logic. Smallest coherent change; checks 5 & 10 (user-stories / NFRs are genuinely OPTIONAL sections) left intentionally untouched.

## Second Check (re-verification, MANDATORY)
Same empty PRD, post-fix: `check 6 → passed:false, detail:"No requirements section found"`, `checks_passed:2, score:8, grade:NEEDS_WORK`. Same-metric assertion now passes. Regression scan: `sample_prd` (real requirements) still passes check 6; a thorough PRD still scores 57/57 EXCELLENT (exit 0); grade-boundary tests green; full offline suite green. `regression_scan=pass`, `verdict=resolved`.

## Reusable Rule
A presence/quality check over an ABSENT section must fail-closed — never pass-and-assert-quality on emptiness.

## Decision Trail
Owner: walkthrough auto-mode (Hayden stand-in); real owner approves via the PR. Rejected: only rewording the detail while keeping `passed:true` (would leave the vacuous pass + inflated count). Deferred: checks 5 & 10 pass-on-absent (P3; those sections are legitimately optional) — recorded for a future decision.

## Revisions
- 2026-06-17: initial fix; second check passed on first attempt.
