---
id: 2026-06-17-cli-watcher-permit-reason-mask
schema_version: 1
repo: anombyte93/prd-taskmaster
branch: walkthrough/atlas-cli-surfaces
commit: pending
date: 2026-06-17
route: "cli:watcher-run"
screen_purpose: "Let an operator see the fail-closed real-slash permit for a job and understand WHY it is or isn't permitted."
mode: auto
viewport: cli
device_class: desktop
severity: P2
category: trust
root_cause: "The permit reason ladder tested `not to_slash` before `discrepancies`, so a job with no to-be-slashed submissions but a cheating-winner DISCREPANCY reported the benign 'no to-be-slashed' message instead of the discrepancy."
assumption_trap: "empty to-be-slashed set == nothing interesting happened (ignores discrepancies/abstains on the winners)."
reusable_rule: "Order a fail-closed reason ladder most-serious-finding first; never let a benign branch shadow a security-relevant one."
evidence_method: [code]
files_changed: ["prd_taskmaster/tournament/watcher.py", "tests/core/test_tournament_watcher.py"]
first_check: {result: fail, metric: "permit_enforce_slash(record with empty to_slash + cheating-winner DISCREPANCY).reason == 'blocked: no to-be-slashed submissions to confirm' (discrepancy masked)", evidence_ref: "pytest test_permit_reason_surfaces_winner_discrepancy_over_empty_slash (pre-fix RED)"}
second_check: {result: pass, metric: "same record → reason contains 'discrepancy' and NOT 'no to-be-slashed'; permitted still False; ex-win in discrepancies", evidence_ref: "pytest (post-fix GREEN)", regression_scan: pass}
regression_checks: ["existing permit reason tests (discrepancy-among-slashes, abstained-winner, empty-to_slash, mixed-batch) unchanged", "permitted boolean decision unchanged across all permit tests", "full offline suite"]
verdict: resolved
status: verified
approval: pending
evidence_dir: evidence/2026-06-17-cli-watcher-permit-reason-mask
tags: [watcher, slash-gate, fail-closed, legibility, self-review]
related: [atlas-watcher-built]
title: "watcher permit reason masked a caught cheating-winner discrepancy with a benign 'no to-be-slashed' message"
---

## Lesson (TL;DR)
The watcher's real-slash permit correctly BLOCKED a job where a winner was an independent discrepancy, but its human-readable `reason` said "no to-be-slashed submissions to confirm" — hiding the very thing the operator most needs to see. The boolean was right; the explanation lied by omission. Order the reason ladder most-serious-first.

## Screen & Purpose
Surface `cli:watcher-run` → `watcher.permit_enforce_slash` (the fail-closed gate that decides whether real `--enforce-slash` forfeiture may proceed). Soul purpose: an operator-legible, honest permit verdict.

## Issue (first check)
A record with zero to-be-slashed submissions but a cheating winner (recorded PASS, watcher DISCREPANCY) returned `permitted:false` (correct) with `reason:"blocked: no to-be-slashed submissions to confirm"` (wrong — the discrepancy was in `out["discrepancies"]` but never surfaced in the headline reason). `to_slash` is empty because the winner recorded PASS, so the `elif not to_slash` branch fired before `elif discrepancies`.

## Root Cause
Reason-ladder ordering: `permitted → not to_slash → discrepancies → abstained → track_record`. The benign empty-set branch shadowed the security-relevant discrepancy branch.

## Fix
`watcher.py`: reorder the ladder to `permitted → discrepancies → abstained → not to_slash → track_record`. The `permitted` boolean is unchanged (already `not discrepancies and not abstained and ...`); only the explanatory string ordering changed.

## Second Check (re-verification, MANDATORY)
Post-fix, same record: `reason` contains "discrepancy", does NOT contain "no to-be-slashed", `permitted` still False, `ex-win` in `discrepancies`. Regression scan: all prior permit tests (discrepancy-among-slashes, abstained-winner, empty-to_slash, mixed-batch, concordance boundary) unchanged; every `permitted` boolean identical to before. Full offline suite green. `regression_scan=pass`, `verdict=resolved`.

## Reusable Rule
Order a fail-closed reason ladder most-serious-finding first; a benign branch must never shadow a security-relevant one.

## Decision Trail
Owner: walkthrough auto-mode; real owner approves via PR. This fix touches code authored earlier this same session — a good reminder that the adversarial surface review caught a legibility gap the build-time tests didn't assert. No alternatives rejected; the reorder is the minimal correct change.

## Revisions
- 2026-06-17: initial fix; second check passed on first attempt.
