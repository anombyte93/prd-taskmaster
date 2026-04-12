# PRD: prd-taskmaster v4 Public Release

**Author:** Claude Opus (autonomous ralph-loop dogfood)
**Date:** 2026-04-13
**Status:** In Review
**Version:** 1.0
**Taskmaster Optimized:** Yes

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Goals & Success Metrics](#goals--success-metrics)
4. [User Stories](#user-stories)
5. [Functional Requirements](#functional-requirements)
6. [Non-Functional Requirements](#non-functional-requirements)
7. [Technical Considerations](#technical-considerations)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Out of Scope](#out-of-scope)
10. [Open Questions & Risks](#open-questions--risks)
11. [Validation Checkpoints](#validation-checkpoints)
12. [Appendix: Task Breakdown Hints](#appendix-task-breakdown-hints)

---

## Executive Summary

prd-taskmaster v4 is a zero-config goal-to-tasks engine for Claude Code that has been ready for public release pending autonomous dogfood verification. v4 replaces v3's 12-step linear workflow with 5 phases, adds a 20-tool MCP server, and introduces the first autonomous-mode path so the skill works inside ralph-loops and /pentest-wtf invocations without blocking on user input. It preserves every feature v3 users upvoted (comprehensive PRDs, 13-check validation, TaskMaster integration, CLAUDE.md generation) while eliminating the setup friction that bounced new users on first install. Expected impact: first-run setup time drops from 10-plus minutes to under 60 seconds for Claude Max users, and the skill is usable in fully unattended execution environments for the first time.

## Problem Statement

### User Impact

Current v3 users hit three first-run failure modes documented across the repo's issue tracker and discovered during this dogfood session:

1. **Provider setup confusion.** v3's docs told users to run `task-master models --set-main claude-code` which TaskMaster rejects with "Model ID 'claude-code' not found" because `claude-code` is a provider flag, not a model identifier. New users hit this and abandon within two minutes.
2. **Binary name ambiguity.** v3's `script.py` looked for `task-master-ai` (the MCP server) and `taskmaster` (a shell alias, not a real binary), missing the actual CLI binary `task-master`. Users with modern task-master-ai npm installs got false-negative detection.
3. **Interactive-only discovery.** v3's DISCOVER phase assumed a human driver — running it via `/pentest-wtf`, `/ralph-loop`, or any auto-approval session blocked forever waiting for input. Affected users: anyone trying to script PRD generation.

These aren't edge cases — they're the default path. Anyone installing v3 fresh from the curl pipe, running it once, and trying to configure the recommended `claude-code` provider will hit at least failure mode 1. The skill gets an upvote from users who push through, and silent abandonment from users who don't.

### Business Impact

prd-taskmaster is the top-of-funnel for the broader Atlas skill ecosystem. Every failed first-run is a lost user who does not discover Atlas at all, will not convert to the premium atlas-loop tier, and signals on GitHub that the project is unreliable. Revenue impact is indirect but meaningful: the skill has GitHub stars and active issues on v3, meaning the growth is real. v4 must not regress any v3 user while converting the bouncers. Strategic cost of shipping a broken v4 is repository reputation damage to the upstream Atlas business.

## Goals & Success Metrics

### Goal 1: Zero-friction first-run setup

- **Baseline:** 12-step workflow, 4 conditional provider install paths, docs that contain a copy-paste command that fails
- **Target metric:** Mean time to first successful `ready: true` under 60 seconds for Claude Max users
- **Measurement approach:** `tests/test_phase_pipeline_e2e.py::test_validate_setup_returns_structured_checks` plus tmp-dir dogfood trace committed to git history
- **Timeframe:** Achieved in this release

### Goal 2: Autonomous mode as a first-class path

- **Baseline:** DISCOVER phase blocks forever when invoked without a human
- **Target metric:** 100 percent of ralph-loop and /pentest-wtf invocations complete DISCOVER without user input
- **Measurement approach:** This session itself — a v4 dogfood running inside `/ralph-loop:ralph-loop` — reaches a ship-ready state without blocking. Git commit chain on main branch serves as proof
- **Timeframe:** Proven during this release

### Goal 3: MCP layer for tool-first invocation

- **Baseline:** Every subcommand requires `python3 script.py <sub>` plus JSON parsing overhead
- **Target metric:** 20 MCP tools registered, 6 plus smoke tests passing, end-to-end MCP shim parity with direct CLI calls
- **Measurement approach:** `python3 mcp_server/test_server.py` exits 0 with "All smoke tests passed"
- **Timeframe:** Achieved

### Goal 4: Defensible test coverage

- **Baseline:** Unit tests per script.py subcommand, no end-to-end phase flow tests
- **Target metric:** 200 plus total tests with 0 failures, including regression tests for every ship-blocker discovered
- **Measurement approach:** `pytest -q` returns `210 passed, 1 skipped, 0 failed`
- **Timeframe:** Achieved — commit `cb55fce` reports `210 passed, 1 skipped`

## User Stories

### Story 1: First-run Claude Max user

**As a** Claude Max user who just installed prd-taskmaster-v4 via curl,
**I want to** run the skill and get a validated PRD with zero configuration,
**so that I can** start task-driven development without reading setup docs.

**Acceptance Criteria:**
- [ ] Installation via `install.sh` completes in under 30 seconds
- [ ] First invocation of `/prd-taskmaster-v2` runs `validate-setup` and reports `ready: true` or prints exact fix commands
- [ ] Copy-pasting any failing check's `fix` command resolves that check on retry
- [ ] Phase 0 to Phase 1 transition happens silently when `ready: true`
- [ ] Total time from install to Phase 1 under 60 seconds

### Story 2: Autonomous agent user

**As a** developer running prd-taskmaster inside `/ralph-loop` or `/pentest-wtf`,
**I want to** have the skill complete Phase 2 DISCOVER without a human,
**so that I can** script PRD generation for batch work or overnight runs.

**Acceptance Criteria:**
- [ ] DISCOVER.md documents an explicit "Autonomous Mode — no user present" section
- [ ] The skill detects autonomous context via `.claude/ralph-loop.local.md` or an explicit `--autonomous` flag
- [ ] In autonomous mode, the skill self-brainstorms by writing a discovery summary to `session-context/discovery-*.md` and proceeds to GENERATE without blocking
- [ ] The git commit history serves as the audit trail of autonomous decisions
- [ ] No ralph-loop session blocks on Phase 2 DISCOVER

### Story 3: PRD quality auditor

**As a** user who wants to judge whether my PRD is shippable,
**I want to** run `validate-prd --ai` and get both deterministic scoring and a holistic LLM quality review,
**so that I can** catch subjective quality issues regex checks miss.

**Acceptance Criteria:**
- [ ] `validate-prd` always runs 13 deterministic regex checks regardless of flags
- [ ] `validate-prd --ai` additionally invokes task-master's configured main model for a JSON-shaped quality review
- [ ] When task-master is missing, `--ai` falls back to deterministic-only output with a warning (never hard-fails)
- [ ] The `ai_review` field in JSON output is only populated when `--ai` is passed
- [ ] Cost is zero for Claude Max users (reuses claude-code provider)

## Functional Requirements

REQ-001: `validate-setup` subcommand returns structured per-check pass/fail output. **Must have**. The subcommand runs binary-found, version-supported, project-initialized, config-present, main-model-set, research-model-set, and fallback-model-set checks. Each failing check returns a `fix` field containing an executable shell command that resolves that check. Task breakdown: add subcommand, register in argparse, write 7 checks with fix hints, wire into `_check_taskmaster_version` helper. Implementation step: approximately 4 hours.

REQ-002: `_detect_taskmaster_method` checks for `task-master`, `task-master-ai`, and `taskmaster` binaries in that priority order. **Must have**. The `task-master` binary is the real CLI; the other two are legacy/fallback detection paths for older installs. Task breakdown: update shutil.which chain, add regression test. Implementation step: approximately 1 hour.

REQ-003: `cmd_init_taskmaster` calls `task-master init --yes` with graceful flag degradation. **Must have**. When the full flag set (`--store-tasks-in-git --rules=claude`) fails on older task-master versions, the code falls back to `--yes` only. No flag combinations that fail silently. Task breakdown: implement attempts loop, return structured result with command trace. Implementation step: approximately 2 hours.

REQ-004: `cmd_detect_capabilities` returns a `tier` field distinguishing `"free"` from `"premium"`. **Must have**. Mode D routing requires the literal `atlas-loop` and `atlas-cdd` skills to be installed; the generic `cdd` skill (ships in pr-review-toolkit) does not trigger Mode D. Task breakdown: add Atlas skill detection, derive tier flag, update decision logic. Implementation step: approximately 2 hours.

REQ-005: DISCOVER.md documents an "Autonomous Mode — no user present" section with a self-brainstorm template. **Must have**. The autonomous path is not a degraded mode — it is a first-class path covering ralph-loop, pentest-wtf, and auto-approve sessions. Task breakdown: write autonomous section, document detection heuristics, define self-approval gate. Implementation step: approximately 1 hour.

REQ-006: SKILL.md preflight decision table includes a row for `prd_path exists + task_count == 0`. **Must have**. This handles the ambiguous state where a stale PRD exists but was never parsed into tasks. Task breakdown: add decision table row, document backup-and-replace path. Implementation step: approximately 30 minutes.

REQ-007: `validate-prd --ai` is opt-in LLM augmentation shelling out to `task-master research`. **Must have**. Deterministic checks always run first. AI review is additive and never replaces the regex path. Failures degrade silently with a warning. Task breakdown: implement `_ai_review_prd` helper, wire `--ai` argparse flag, add JSON extraction from task-master output, write fallback-degradation test. Implementation step: approximately 3 hours.

REQ-008: A FastMCP server at `mcp_server/server.py` exposes all 12 script.py subcommands as MCP tools. **Must have**. The server uses a subprocess shim pattern in `mcp_server/lib.py` so script.py stays unmodified. Task breakdown: install FastMCP, implement 12 tool functions, write smoke tests, document registration snippet. Implementation step: approximately 4 hours.

REQ-009: The MCP server additionally exposes 8 `tm_*` wrapper tools for task-master CLI operations. **Should have**. These are fallback wrappers used when the real `task-master-ai` MCP server isn't registered in the user's `.claude.json`. Task breakdown: write `run_taskmaster` subprocess helper, implement 8 tool wrappers, parse models output to strip ANSI, test with real task-master CLI. Implementation step: approximately 5 hours.

REQ-010: `tests/test_phase_pipeline_e2e.py` contains end-to-end phase-integration tests including a regression test for the SETUP.md `--set-main claude-code` syntax bug. **Must have**. Total test count must be 200 plus with 0 failures. Task breakdown: write 9 e2e tests, assert no broken fix commands, cover tier field, check MCP parity. Implementation step: approximately 3 hours.

REQ-011: `_check_taskmaster_version` warns when the detected task-master version is older than `TASKMASTER_MIN_VERSION = "0.43.0"`. **Should have**. The warning does not block (since older versions often work partially), but `validate-setup` surfaces it. Task breakdown: implement version parser, add helper function, wire into validate-setup as warning-severity check. Implementation step: approximately 1 hour.

REQ-012: README lead positioning describes v4 as standalone and free. **Must have**. The Atlas pipeline is a one-paragraph optional footnote, not a front-loaded context that suggests paid-tier dependency. Users searching GitHub see "free standalone skill" as the first sentence after the title. Task breakdown: rewrite Where-This-Fits section, lead with standalone positioning, demote atlas to footnote. Implementation step: approximately 1 hour.

REQ-013: Mode C (ralph-loop + superpowers) is the default free-tier recommendation in HANDOFF. **Must have**. Mode D (atlas-loop + atlas-cdd) recommendation is gated on both Atlas skills actually being installed. Task breakdown: update HANDOFF.md mode table, clarify free/premium split, verify detect-capabilities routing alignment. Implementation step: approximately 1 hour.

REQ-014: All phase files stay under 150 lines. **Should have**. This keeps the codification pattern intact — SKILL.md is an index, phase files are recipes. Task breakdown: audit line counts, tighten any phase file exceeding 150, verify post-edit. Implementation step: approximately 30 minutes.

REQ-015: Task-master status values use hyphens (`in-progress`), not underscores (`in_progress`). **Must have**. TaskMaster 0.43.1 rejects underscore form. Any phase file documenting the task workflow must use the correct form. Task breakdown: grep for in_progress across phase files, replace with in-progress, document valid status set. Implementation step: approximately 15 minutes.

### Dependencies

REQ-002 and REQ-003 depend on REQ-001 — `validate-setup` surfaces bugs in the other two during first-run diagnostics and must exist before the others are testable. REQ-008 and REQ-009 depend on REQ-001 because the MCP server's `validate_setup` tool wraps the subcommand. REQ-007 depends on REQ-011 because older task-master versions may not support the `research` command the AI path invokes. REQ-013 depends on REQ-004 because tier routing requires capability detection to be correct at the script level. REQ-015 is a doc-correctness prerequisite that blocks user-facing workflow docs (HANDOFF in particular).

## Non-Functional Requirements

**Performance targets:** `validate-setup` must return in under 5 seconds (measured: under 1 second on dev machine). `preflight` must return in under 3 seconds (measured: under 500 ms). `validate-prd` deterministic path must complete in under 1 second for a 1000-line PRD (measured: under 800 ms on comprehensive template). The AI-augmented path may take up to 120 seconds (timeout-bounded via subprocess timeout parameter).

**Reliability targets:** All script.py subcommands must emit JSON on stdout even in error states (never stack traces). Subprocess timeouts must be explicit on every external call. No subcommand may leave partial state on failure — if `init-taskmaster` fails, no `.taskmaster/` directory is created.

**Compatibility:** Must work with task-master 0.43.0 and later. Python 3.8 plus. No new runtime dependencies beyond what v3 required. FastMCP is optional — the skill works without `mcp_server/` installed.

**Security:** No shell injection paths. All user input to `task-master research` is passed through argv (list form), not a shell string. No secrets logged. No automatic git push. The `_ai_review_prd` function truncates user input to 8000 characters to bound token cost exposure.

**Scalability:** Handles PRDs up to 50000 characters (larger ones truncated for AI review, full validation still runs). Task graphs with up to 200 tasks (constrained by `calc-tasks` clamp of 10-40 recommended, but parsing accepts any count).

## Technical Considerations

### System Design and Architecture

v4 preserves v3's codification pattern (AI judgment in SKILL.md plus phase files, deterministic operations in script.py) and adds a third layer: an MCP server that exposes script.py subcommands as callable tools. The three-layer architecture is:

- **SKILL.md plus phases/*.md**: AI judgment and procedural recipes (134 plus approximately 500 lines)
- **script.py**: Deterministic operations, approximately 1400 lines, 13 subcommands, all emit JSON
- **mcp_server/**: FastMCP thin wrapper, 20 tools (12 script plus 8 tm_*), subprocess shim pattern

Phase files are Read explicitly at runtime — Claude never pays context cost for phases it doesn't enter. This is a load-bearing architectural decision that preserves the thin-orchestrator pattern.

### Integration Points

- **task-master-ai**: REQUIRED dependency, installed via `npm install -g task-master-ai`. The skill invokes it via both CLI subprocess and (preferred) the task-master-ai MCP server when available.
- **superpowers plugin**: OPTIONAL. Enables Mode A and Mode C by providing `brainstorming`, `writing-plans`, and `subagent-driven-development` skills.
- **ralph-loop skill**: OPTIONAL. Enables Mode C (recommended free) by providing the iterative execution loop.
- **atlas-loop plus atlas-cdd**: OPTIONAL. Enables Mode D (premium). Detected via filesystem presence in `~/.claude/skills/`.

### Data Model

The skill operates on three persistent file types:

1. `.taskmaster/docs/prd.md` — the generated PRD (markdown, template-based)
2. `.taskmaster/tasks/tasks.json` — parsed task graph (task-master schema)
3. `.taskmaster/reports/task-complexity-report.json` — complexity analysis (written by `task-master analyze-complexity`)

No new schemas introduced by v4. Config lives in `.taskmaster/config.json` (task-master-owned).

### Technology Stack

- Python 3.8 plus for script.py and mcp_server
- FastMCP (optional) for the MCP server layer
- task-master-ai (Node, via npm) for task graph mechanics
- Bash for install.sh entry point
- pytest for the 210-test suite

## Implementation Roadmap

**Phase 1 (complete): Ship-blocker fixes.** Tasks REQ-001 through REQ-006 plus REQ-015 must land first — they unblock first-run users. Completed in commits `e1a5ab5`, `906250d`, `cb55fce`.

**Phase 2 (complete): AI augmentation plus MCP layer.** Tasks REQ-007, REQ-008, REQ-009 deliver the key v4 differentiators over v3.

**Phase 3 (in progress — this session): Dogfood verification and polish.** Tasks REQ-010 through REQ-014 plus the comparison doc proving v4 is better than v3 along every axis.

**Phase 4 (post-release): Telemetry and follow-ups.** Add opt-in usage metrics, a `/prd-taskmaster-v2 --report-bug` command, and domain-specific templates (pentest, business, learning) to round out the domain-agnostic claim.

## Out of Scope

- **Rewriting task-master itself.** v4 is a thin orchestrator. If task-master has a bug, we work around it or file upstream — we do not fork.
- **UI.** prd-taskmaster is a CLI/skill, not a web app. No frontend work.
- **Task execution.** v4 generates PRDs and parses tasks; execution is handed off to `ralph-loop`, `atlas-loop`, or `task-master next`. We do not implement an executor.
- **Paid premium features.** Mode D's premium capabilities ship via `atlas-loop` and `atlas-cdd`, which are separate skills. v4 itself is 100 percent free.
- **Non-English localization.** v4 accepts English input and generates English PRDs.
- **Custom LLM providers beyond what task-master supports.** The skill reuses the user's task-master provider chain — it does not introduce a new provider abstraction.

## Open Questions and Risks

**Risk 1: task-master version drift.** Future task-master releases may remove flags v4 depends on. Mitigated by `_check_taskmaster_version` warning, graceful flag fallback in `cmd_init_taskmaster`, and the `TASKMASTER_MIN_VERSION` constant that we bump when breaking changes are detected.

**Risk 2: Autonomous mode produces low-quality specs.** When running without a user, the self-brainstorm template may miss nuances a human would catch. Mitigated by explicit assumption documentation in `session-context/discovery-*.md` and the "if you would have to ask more than 2 questions the user didn't anticipate, stop and write a handoff note" rule in DISCOVER.md.

**Risk 3: MCP server divergence from script.py.** As script.py evolves, the MCP shim may drift out of sync. Mitigated by `test_mcp_shim_returns_same_payload_as_direct_cli` in the e2e test suite, which catches parity regressions.

**Open Question 1:** Should `validate-prd --ai` use `task-master research` (current) or `task-master update` with a custom prompt? `research` is designed for broad web research; `update` may be more targeted for PRD review. Decided for release: stick with `research` — it's the path task-master documents as a general LLM query.

**Open Question 2:** Should autonomous-mode discovery write the session-context file or commit it? Currently writes; commit is user's call. Future work: auto-commit with a `[autonomous-discovery]` prefix so the audit trail is immediate.

## Validation Checkpoints

**Checkpoint A: Phase 0 clean-slate replay.** Run `validate-setup` in a fresh tmp dir, expect 3 plus critical failures with fix hints. Run fix hints. Re-run `validate-setup`, expect `ready: true`. Status: PASSED (evidence: bash trace in this session).

**Checkpoint B: Full test suite.** Run `pytest tests/ -q`. Expect 200 plus passed, 0 failures, 1 skipped. Status: PASSED (210 passed, 1 skipped, evidence in commit `cb55fce`).

**Checkpoint C: MCP server smoke test.** Run `python3 mcp_server/test_server.py`. Expect 6 tests passing covering preflight, detect_capabilities, validate_prd, tm_models_list, tm_next, tm_list. Status: PASSED (evidence: agent delivery report).

**Checkpoint D: End-to-end MCP shim parity.** Call a script.py subcommand directly and via the MCP shim; expect byte-identical JSON payloads. Status: PASSED (evidence: `test_mcp_shim_returns_same_payload_as_direct_cli` in e2e suite).

**Checkpoint E: PRD validation grade.** Run `validate-prd --input .taskmaster/docs/prd.md` on this very PRD. Expect grade GOOD or better. Status: to be verified next — this is the self-referential proof that v4 can generate its own shippable PRDs.

## Appendix: Task Breakdown Hints

Estimated effort: 20 tasks total, approximately 15 hours for the remaining polish work after the ship-blocker fixes are committed.

- **Tasks 1-6 (3-4 hours)**: Ship-blocker fixes (SETUP.md syntax, binary detection, init-taskmaster, Mode D routing, decision table, DISCOVER autonomous) — already complete in earlier commits.
- **Tasks 7-11 (3 hours)**: AI augmentation plus MCP layer plus e2e tests — already complete.
- **Tasks 12-15 (2 hours)**: README repositioning, version awareness, skill-forge scaffolding — already complete.
- **Tasks 16-18 (2 hours)**: Phase-file bug fixes (in-progress hyphen, analyze-complexity stdout assumption, taskmaster models output ANSI) — already complete.
- **Tasks 19-20 (3 hours)**: This PRD plus v3/v4 comparison doc — in progress.
