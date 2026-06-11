# Dogfood Report — v4 engine on the Phase B goal (2026-06-11)

The merged v4 engine ran its own 4-phase pipeline on a real goal: planning **Phase B (Atlas
Fleet)**. Full pipeline completed: Preflight → Discovery (approved) → Generate → Handoff.

## Run evidence

| Artifact | Result |
|---|---|
| Preflight | TaskMaster CLI 0.43.1 detected; fresh state; providers auto-configured (codex-cli main, sonar research via local proxy) |
| PRD | `.taskmaster/docs/prd.md` — first validate **NEEDS_WORK (59.6%)** → fix loop (one iteration) → **EXCELLENT 57/57 (100%)**, 0 placeholders |
| Task graph | 12 tasks / 29 subtasks, dependencies forming a real DAG; `validate-tasks` caught an empty subtask description (authoring error) before accepting; enrich idempotent; phaseConfig coverage 1.0 (11 MEDIUM, 1 COMPLEX) |
| Handoff | Mode A (Plan & Drive) recommended for this machine-state; Atlas Fleet correctly locked |

The validation fix loop (UC-4) worked exactly as designed — the engine refused its own
author's first draft and every demanded fix (user/business impact, measurable goals, P0/P1
priorities, ~Nh effort hints) genuinely improved the spec.

## Findings (fix before v4.0.0 ships)

1. **P0 — `task-master init` clobbers an existing `.mcp.json`.** Running the engine's setup in
   a project that already has `.mcp.json` (e.g. any Claude plugin repo — including this one)
   overwrites it with TaskMaster's template full of placeholder API keys. The SETUP phase must
   extend the DETECT-FIRST principle (FR-6) to `.mcp.json`: back up before init and re-merge
   the user's entries after, or pass init flags that skip MCP config writing.
2. **P1 — `configure-providers` sequencing gap.** SKILL.md Phase 1 says to run it right after
   preflight, but it hard-fails with ".taskmaster/config.json not found; run task-master init
   first". Either the skill flow inits first, or the command should auto-init / return a
   recommended-action instead of an error.
3. **P2 — `calc-tasks` ignores the scale classification.** Discovery classified the project
   Solo (8–12 tasks per the product spec); the CLI heuristic recommended 21 from
   requirement-count alone. The MCP variant takes team/scope params; the CLI should accept
   (or infer) scale.
4. **P2 — recommendation legibility.** `detect-capabilities` (CLI) returns an empty
   recommendation reason and no `tier` field ("None"), violating the UX-SPEC rule that every
   recommendation carries a reason. The plugin's mode_recommend emits both; the CLI path
   should too.

## Execution-layer comparison (the dogfood's second purpose)

Three candidates for executing a task graph in parallel were compared:

- **The /atlas engine** owns the front of the pipeline (goal → graded PRD → dependency DAG)
  and the verification spine (CDD cards, ship-check). It does not execute in parallel — by
  design it hands off.
- **orchestrating-peer-cli-agents** is a manual discipline for driving peer CLI agents in
  tmux: decompose by hand, review plans, independently verify every claim, own the scoreboard.
  No planner, no deterministic artifacts — but its verification doctrine is the strongest part.
- **atlas-dispatch** (personal skill) already automates PRD → launcher fleet → dependency
  waves → checker → integration branch → one PR. It is the working prototype of Phase B.

**Verdict: combine, don't choose.** They are three layers of one stack, and the Phase B PRD
encodes exactly that: the engine plans and verifies; `execute-fleet` (productized
atlas-dispatch) executes; and the peer-cli skill's rules are written into the worker contract
as hard requirements — REQ-006..REQ-009 are its "never trust the peer's word", "orchestrator
owns the scoreboard", and "self-contained goal with an invitation to push back" doctrines made
machine-enforceable. The manual skill remains the documented no-launcher fallback.
