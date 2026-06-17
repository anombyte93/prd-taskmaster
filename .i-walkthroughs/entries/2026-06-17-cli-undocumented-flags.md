---
id: 2026-06-17-cli-undocumented-flags
schema_version: 1
repo: anombyte93/prd-taskmaster
branch: walkthrough/atlas-cli-surfaces
commit: pending
date: 2026-06-17
route: "cli:set-status"
screen_purpose: "Expose the engine's CLI flags clearly enough that a cold user can discover what each does — and what values it accepts — from -h alone."
mode: auto
viewport: cli
device_class: desktop
severity: P2
category: interaction
root_cause: "Several argparse flags were added with no help= string; most damaging, set-status --status is a REQUIRED flag whose valid vocabulary (pending/in-progress/done/review/deferred/cancelled/blocked) appeared nowhere in help, SKILL.md, or the MCP tool."
assumption_trap: "the flag name is self-documenting (a required enum flag is not — the accepted values must be shown)."
reusable_rule: "Every CLI flag gets help text; a required enum flag must enumerate its accepted values in that help."
evidence_method: [code]
files_changed: ["prd_taskmaster/cli.py", "tests/core/test_cli.py"]
first_check: {result: fail, metric: "build_parser(): set-status --status, engine-preflight --no-configure, next-task --tag, economy-report --input all have help==None", evidence_ref: "pytest test_cli_flags_have_discoverable_help (pre-fix RED) + live set-status -h showing bare '--status STATUS'"}
second_check: {result: pass, metric: "all four flags have non-empty help; set-status --status help contains 'in-progress'", evidence_ref: "pytest (GREEN) + live: set-status -h now prints 'Task status; one of: pending, in-progress, done, review, deferred, cancelled, blocked'", regression_scan: pass}
regression_checks: ["set-status invalid-status error path unchanged (help-only, no argparse choices added → still returns FR-28 dict, not an argparse usage error)", "all existing CLI subprocess tests", "full offline suite"]
verdict: resolved
status: verified
approval: pending
evidence_dir: evidence/2026-06-17-cli-undocumented-flags
tags: [cli, discoverability, help-text, consistency, set-status]
related: []
title: "Undocumented CLI flags — esp. set-status --status whose valid vocabulary was undiscoverable"
---

## Lesson (TL;DR)
Four CLI flags carried no help text; the worst was `set-status --status`, a REQUIRED flag whose accepted values were findable nowhere a user looks (`-h`, SKILL.md, or the MCP tool). A cold user had to read source to learn the status vocabulary. Every flag gets help; a required enum flag enumerates its values.

## Screen & Purpose
Surfaces `cli:set-status`, `cli:engine-preflight`, `cli:next-task`, `cli:economy-report`. Soul purpose: a self-describing CLI a cold user can drive from `-h`.

## Issue (first check)
`build_parser()` introspection: `set-status --status`, `engine-preflight --no-configure`, `next-task --tag`, `economy-report --input` all had `help is None`. Live `set-status -h` printed `--status STATUS` with no value list — the vocabulary (pending/in-progress/done/review/deferred/cancelled/blocked) was invisible.

## Root Cause
Flags were added via `add_argument(...)` without `help=`. Inconsistent with sibling flags (e.g. `parse-prd --input`) that do carry help.

## Fix
`cli.py`: add help strings to the four flags. For `set-status --status`, the help enumerates the valid status vocabulary. Help-only (NOT argparse `choices=`) so the engine's existing FR-28-safe status validation + error dict is preserved rather than replaced by an argparse usage error.

## Second Check (re-verification, MANDATORY)
Post-fix: introspection shows all four flags with non-empty help; `set-status --status` help contains "in-progress"; live `set-status -h` prints the full status list. Regression scan: the invalid-status path still returns the engine's FR-28 error dict (no `choices=` added, so no behavior change to error handling); all existing CLI subprocess tests pass; full offline suite green. `regression_scan=pass`, `verdict=resolved`.

## Reusable Rule
Every CLI flag gets help text; a required enum flag must enumerate its accepted values in that help.

## Decision Trail
Owner: walkthrough auto-mode; real owner approves via PR. Rejected: adding argparse `choices=` for `--status` (would move validation to the parse layer and emit an argparse usage error instead of the engine's structured FR-28 dict — a contract change). Deferred: also documenting the status vocabulary in SKILL.md + the MCP tool description (follow-up; this entry fixes the CLI surface).

## Revisions
- 2026-06-17: initial fix; second check passed on first attempt.
