# Design Spec — `execute-wave`: a Bounded Dynamic-Workflow Execution Mode for Atlas

> Status: **DESIGN APPROVED** (research/brainstorming lane, 2026-06-25). No code yet — implementation
> awaits an explicit greenlight. Design forks confirmed with the owner (see Decisions).

## Context

Atlas's north star: a frontier **driver** decomposes a goal and routes each component to the
**cheapest capable executor**. Today the executor pool is reached two ways:

- **atlas-dispatch → atlas-launcher phoenix(es)** (`skills/execute-fleet/SKILL.md`): persistent,
  cross-session, multi-day, walk-away tmux workers with succession, model re-hatch, durable inbox
  monitoring. Durable but heavy; depends on the atlas-launcher MCP.
- **direct subagent fan-out** via the Claude Code **Workflow** tool: ephemeral, non-interactive,
  session-bound, capped subagents orchestrated by a JS script (`agent()/parallel()/pipeline()`),
  with native git-worktree isolation and schema-validated structured returns.

**Field evidence (Capel Signal Intelligence OS gen-2, "Wave 11"):** a dynamic Workflow ran **8
file-disjoint connector agents in parallel**, kept tool churn inside subagent contexts (cheap on
the driver), forced structured returns `{name, collectExport, sourceId, envVars, live, testPassed}`,
and used a **single integrator** for shared files. It worked *because the wave was provably
file-disjoint and bounded.* But Workflow is **not** a phoenix replacement: its agents are ephemeral,
non-interactive, session-bound, and capped.

**The need:** a first-class, **engine-gated fast lane** for the common case — a PRD whose ready
frontier is file-disjoint and fits in **one wave**, fannable out, green-gated, and turned into a PR
**in-session, in minutes** — without losing the phoenix/handoff machinery for the durable case.

**The load-bearing gap (verified in code):** `fleet.compute_waves()` (`prd_taskmaster/fleet.py:394`)
does **dependency-ordered topological chunking only** — it never checks file overlap. The task
schema (`backend.py:32`) has **no `filesAffected`/`scopedTo` field**. `docs/product/PRODUCT-SPEC.md`
**FR-21 mandates a partition checker, but none exists** — file-disjointness is advisory today.
This mode's safety rests on closing that gap with an unfakable, engine-enforced gate.

## Decisions (confirmed with owner)

1. **Disjointness = declared scope + deterministic checker.** Tasks carry a `filesAffected` glob
   list (LLM proposes at generate-time); a new **stdlib `partition-check` gate** deterministically
   rejects any wave whose chunk globs overlap. Fail-closed. (Not LLM-judgment-only.)
2. **First implementation slice = the partition-check gate alone** — reused by BOTH this mode and
   execute-fleet; closes FR-21 without touching orchestration.
3. **Pre-fan-out validation = deterministic grade + panel ratifies partition.** Reuse
   `validation.py` (PRD grade ≥ GOOD) AND a small reviewer panel (the `atlas-review`
   friendly+hostile pattern) ratifies the partition is genuinely disjoint/well-scoped.

## Proposed mode boundaries

`execute-wave` is the **third execution mode**, selected at the HANDOFF phase alongside the others:

| Mode | What | Parallelism | Durability | Backend |
|------|------|-------------|------------|---------|
| `execute-task` | solo, sequential, per-task subagent | none | in-session | subagent |
| **`execute-wave` (NEW)** | **one bounded file-disjoint wave, synchronous** | **parallel, capped (≤ ~8)** | **in-session only** | **Workflow tool (`parallel`/worktree)** |
| `execute-fleet` (PRO) | multi-wave, multi-day, walk-away | parallel across waves | cross-session phoenix | atlas-launcher MCP |

**Routing rule (added to `skills/handoff`):** recommend `execute-wave` when `compute_waves` yields a
**single ready wave** (or short chain) AND `partition-check` PASSes AND the user wants in-session
speed without walk-away durability. Recommend `execute-fleet` when there are many dependency-ordered
waves, the run is multi-day, or it needs phoenix survival/re-hatch/inbox/succession. `execute-wave`
**never** falls back to fleet from inside itself — it reports and stops, letting handoff re-route.

**The pipeline (`workflows/execute-wave.js`, run by the Workflow tool):**
`preflight → validate(judge panel) → partition-check → fan-out(parallel + worktree) →
integrate(single integrator) → green-gate(ship-check) → one PR`. Strictly **one wave** — the
multi-wave loop stays execute-fleet's job.

## Existing code / skill surfaces found (reuse, don't reinvent)

- **Wave scheduling:** `fleet.compute_waves()` / `run_fleet_waves()` / `ready_set()`
  (`fleet.py:394/433/383`), `route_task()` for cheapest-capable model (`fleet.py:306`); CLI
  `python3 script.py fleet-waves`; MCP `compute_fleet_waves` (`mcp-server/server.py:163`).
- **Fleet choreography to mirror:** `skills/execute-fleet/SKILL.md` — hard gates, **sole-writer
  rule** (orchestrator alone writes `tasks.json`/`pipeline.json`), CDD-card-before-terminal-status,
  sequential merge into `fleet-integration`, `ship-check` → `SHIP_CHECK_OK` → one PR.
- **Binding green gate (reuse verbatim, do not weaken):** `skel/ship-check.py` — 6 gates incl.
  Gate 5 oracle re-execution (`oracle_bridge.py`, fail-closed) and Gate 6 reachability
  (`reachability.py`); emits `SHIP_CHECK_OK`/exit 0. `prd_taskmaster/shipcheck.py` is **display-only**.
- **Reachability:** `reachability-sweep` CLI → WIRED/EXEMPT/ORPHAN/ERROR.
- **Task state:** `task_state.py` (`next-task`/`claim-task`/`set-status`, atomic); schema
  `backend.py:32` (`TASKS_SCHEMA_HINT`).
- **Deterministic PRD validation:** `validation.py` (13 checks, 57 pts, grades
  EXCELLENT/GOOD/ACCEPTABLE/NEEDS_WORK; placeholder hard-fail). **No judge panel exists today.**
- **Reviewer pattern to reuse for the panel:** the `atlas-review` skill (paired friendly+hostile
  reviewers, confidence-gated triangulation).
- **Telemetry / cost ledger:** `economy.append_telemetry()` (`economy.py:95`), `feedback-add` CLI.
- **Result-merge precedent:** `parallel.apply_results()` (`parallel.py:125`) — atomic, flock-guarded.
- **Skill conventions:** lowercase-hyphenated, phase-bound `execute-*` skills are
  `user-invocable: false`, dispatched by `skills/handoff`. New skill slots beside `execute-fleet`.

## Data contracts

- **Task schema extension (additive):** `filesAffected: string[]` — declared write-scope globs
  (e.g. `["prd_taskmaster/economy.py", "tests/core/test_economy.py"]`). A task with **no**
  `filesAffected` is treated as **unscoped → touches everything → forces serialization**
  (conservative/fail-closed). Emitted by `skills/generate`; absent on legacy tasks (back-compatible).
- **partition-check input:** `{ tag, chunks: [[taskId,…],…], scopes: { taskId: [globs] } }`
  (chunks default to the first wave of `compute_waves`).
- **partition-check verdict:** `{ ok, verdict: "DISJOINT"|"OVERLAP"|"UNSCOPED",
  disjoint: bool, overlaps: [{a, b, files:[…]}], unscoped: [taskId,…] }`. **Fail-closed:** OVERLAP
  or UNSCOPED ⇒ not dispatchable as a single wave.
- **Structured agent return (generalizes the Wave 11 contract):**
  `{ taskId, branch, cddCard, filesTouched: [string], testPassed: bool,
  status: "DONE"|"BLOCKED"|"NEEDS_CONTEXT" }`. `filesTouched` enables the **post-hoc scope audit**
  (did the worker stay inside its declared `filesAffected`?). Enforced via the Workflow `schema:`
  option so non-conforming returns are auto-retried.
- **Reused unchanged:** `tasks.json` shape, CDD card `.atlas-ai/cdd/task-<id>.json`, `SHIP_CHECK_OK`,
  telemetry rows.

## Safety checks

1. **`partition-check` (NEW, the core gate)** — deterministic glob-overlap, fail-closed, pre-dispatch.
   Closes FR-21. Stdlib (`fnmatch`/`pathlib`), hermetic, pure function.
2. **Declared-scope-or-serialize** — an unscoped task can't join a disjoint wave.
3. **Post-hoc scope audit** — integrator diffs each worker's `filesTouched` against its declared
   `filesAffected`; out-of-scope writes ⇒ reject that branch. (Without this, the gate is theater —
   it is mandatory, not optional.)
4. **Worktree isolation** — `parallel()` with `isolation: 'worktree'` (Workflow-native), mirroring
   execute-fleet's worktree-per-worker.
5. **Sole-writer rule** — orchestrator/integrator alone writes `tasks.json` + `pipeline.json`.
6. **Two-gate "done" preserved** — green gate is `skel/ship-check.py` (oracle Gate 5 + reachability
   Gate 6), neither weakened nor bypassed. No oracle call ever added to the display heuristic.
7. **Boundedness** — one wave only; hard chunk cap (≤ ~8, within the Workflow concurrency cap of
   `min(16, cores−2)`). Bigger/needier ⇒ route to execute-fleet.
8. **Telemetry** — every agent + gate appends via `economy.append_telemetry` for the cost ledger.

## How it composes with atlas-dispatch and prd-taskmaster

- **prd-taskmaster:** `execute-wave` is a new **phase-execution skill** selected at HANDOFF (sibling
  to `execute-task`/`execute-fleet`), consuming the same `tasks.json`, complexity report, CDD
  discipline, and `ship-check`. `skills/generate` gains optional `filesAffected` emission.
- **Shared engine surface:** `partition-check` is called by **both** `execute-wave` *and*
  execute-fleet's wave loop (before `session_spawn`) — so the FR-21 gate hardens the **existing**
  PRO path as a side benefit, not just the new mode.
- **atlas-dispatch:** keeps owning the durable phoenix-fleet path; unchanged. The handoff picker
  gains the new option. `execute-wave` does **not** replace dispatch — it's the fast lane for the
  single-wave common case.

## Non-goals (phoenix/handoff capabilities deliberately NOT replaced)

A bounded in-session wave **structurally cannot** provide these — they remain execute-fleet /
atlas-launcher territory, and the mode must say so rather than fake them:

- **Cross-session survival** — wave dies with the session (no `session_spawn` persistence).
- **Model-downgrade re-hatch** — no `session_respawn` / `session_restart_self_phoenix`; a failed
  agent is retried at most once, then `BLOCKED`.
- **Interactive async mid-task discovery** — no live inbox Q&A; a blocked agent returns `BLOCKED`.
- **Succession / handoff** — no `session_handoff` / `session_reparent`.
- **Inbox-first tmux monitoring** — no durable SQLite inbox; returns are ephemeral aggregation.
- **Interactive `/atlas` discovery** — stays in `skills/discover` / the phoenix path.
- **Multi-day / multi-wave walk-away** — explicitly one wave; many waves ⇒ execute-fleet.
- It is **not** a replacement for execute-fleet, and **never** the executor for unscoped/oversized work.

## Risks

1. **Glob-disjoint ≠ semantically disjoint** — different files can still couple via shared
   imports/symbols. Mitigation: post-hoc `filesTouched` audit + the judge panel's semantic
   ratification + the green-gate catches integration breakage.
2. **Unscoped tasks degrade to serialization** — if `generate` omits `filesAffected`, the mode can't
   fan out. Mitigation: `generate` emits scope; unscoped tasks fall to `execute-task`.
3. **Workflow caps / ephemerality** — capped, non-interactive; >cap chunks or interactive context
   can't run here. Mitigation: handoff routes those to execute-fleet.
4. **Shared-file changes** (configs, `tasks.json`) must go through the single integrator, never
   workers. Mitigation: sole-writer rule + integrator owns shared files (the Wave 11 pattern).
5. **Worktree churn cost** — `isolation:'worktree'` has per-agent setup cost. Acceptable only because
   the wave is bounded (≤ ~8).
6. **Gate false-confidence** — a PASS is theater if a worker writes outside scope undetected; the
   post-hoc audit (#3 above) is therefore non-negotiable.
7. **Workflow opt-in** — the Workflow tool requires explicit opt-in; the skill must guard intentional
   invocation and never auto-launch a fleet of agents.

## First implementation slice (when greenlit)

**Scope = the partition-check gate ONLY** (confirmed). Smallest, highest-leverage, closes FR-21,
immediately consumable by execute-fleet too:

- `prd_taskmaster/partition.py` — stdlib pure functions: `check_partition(chunks, scopes) -> verdict`
  with `fnmatch`/`pathlib` glob-overlap detection, fail-closed on unscoped. FR-28-safe error dicts;
  no `sys.exit` in library code.
- `script.py partition-check --tag <tag> [--concurrency N]` — loads `tasks.json`, derives the first
  ready wave (reuse `fleet.ready_set` / `compute_waves`), reads each task's `filesAffected`, runs
  `check_partition`, emits verdict JSON. Wire into `cli.py` following the `cmd_fleet_waves` pattern
  (`fleet.py:473`).
- `tests/core/test_partition.py` — hermetic: disjoint→PASS, overlap→FAIL, unscoped→FAIL, glob edge
  cases (directory globs, overlapping prefixes), empty wave, single chunk.
- Docs: record in PRODUCT-SPEC that FR-21's partition checker now exists; mirror any operating-rule
  change into `AGENTS.md`.
- Constraints: **stdlib-only** (CI AST-scans the package), version-string agreement if bumped.

**Subsequent slices (not slice 1):** ① `filesAffected` emission in `skills/generate` + round-trip
test; ② `workflows/execute-wave.js` + `skills/execute-wave/SKILL.md` (validate→partition→fan-out→
integrate→gate→PR) over existing CLIs; ③ the judge-panel ratification step (atlas-review pattern);
④ handoff routing rule + picker option.

## Tests

- **Slice 1:** `tests/core/test_partition.py` (above) — the disjointness invariant, fail-closed paths,
  glob edge cases.
- **Future:** `filesAffected` round-trips through generate; a **structural** test in `tests/plugin/`
  asserting `execute-wave` SKILL.md declares the green-gate + sole-writer + non-goals invariants
  (matches existing doc-invariant tests); golden-parity for the `partition-check` CLI
  (`tests/parity`, the AI-golden-parity-refactor pattern); a hermetic 2-disjoint-task fixture →
  PASS and a 2-overlapping fixture → FAIL. The green-gate path stays covered by existing
  `ship-check` tests, which `execute-wave` reuses unchanged.

## Provenance

- Grounded by direct reads of `skills/execute-fleet/SKILL.md`, `prd_taskmaster/fleet.py`,
  `prd_taskmaster/backend.py`, plus three exploration sweeps over the wave machinery, the
  Workflow/gate CLI surfaces, and the atlas-launcher phoenix/handoff capability set.
- The full Wave 11 feasibility analysis is available from `claude-capel-crane-radar-gen-2` if the
  Risks section needs hardening with additional real-run gotchas.
