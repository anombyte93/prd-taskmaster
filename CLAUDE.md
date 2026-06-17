# Claude Code Instructions — Atlas

## The end goal (north star — test every change against this)

Atlas's entry point is a frontier model (Fable, or whatever the best frontier model is)
acting as the **driver**. The driver understands the user's intent using skills built for
it, then — inside a loop — decomposes the goal into optimal components and routes each to
the **cheapest capable executor**, to save as many tokens as possible while delivering an
outcome as good as if the frontier model had done all the work itself, at a fraction of
the cost.

The executor pool is **any CLI agent harness** (Claude Code, Codex, Gemini, whatever
ships next) **plus direct API paths** (the native backend's parse/expand/rate), all in
parallel. Not a fixed provider list. Every feature decision is tested against: *does this
make the frontier-driver-decomposes-to-cheap-executors loop better, cheaper, or more
provable?*

What makes Atlas a product, not a prompt pack (the four moats):
1. **Cross-vendor arbitrage** — route work across any harness/API by cost and capability.
2. **Engine-enforced unfakable gates** — validate-tasks, ship-check (`SHIP_CHECK_OK`),
   the two-axis "done" (oracle + reachability, below), structural tests. If a feature could
   be a skill, it's not a product feature until the engine enforces it.
3. **Persistent vendor-neutral task graph** — tasks.json survives across vendors/sessions.
4. **Cross-vendor cost ledger** — telemetry + economy-report prove the savings.

## Unfakable "done" — the two gates (5.3.0+, the trust backbone)

A task ships only when **both** axes pass — `done = oracle-PASS AND code WIRED/EXEMPT`.
This is the property the whole product (and the marketplace below) rests on; do not weaken it.

- **Gate 5 — re-execution oracle.** The binding ship gate is `skel/ship-check.py`
  (oracle-backed). It re-runs the operator-held tests at the *claimed commit* in a
  network-isolated, digest-pinned **podman** sandbox, so a submitter cannot pass by editing
  their own logs. `prd_taskmaster/oracle_bridge.py` maps a CDD card → graded verdict via the
  spine's `atlas oracle` CLI; it is **fail-closed** (any ambiguity → FAIL, never PASS). The
  self-grantable `SHIP_CHECK_OVERRIDE_ADMIN` bypass was removed.
  (`prd_taskmaster/shipcheck.py` is a NON-binding display heuristic only — never add an oracle
  call there.)
- **Gate 6 — reachability** (`prd_taskmaster/reachability.py`, `reachability-sweep` CLI). A
  green test on an orphan module (imported by nothing) is **blocked** and surfaced as
  `⚠ scaffolded`. Verdicts: WIRED (a non-test file imports it) / EXEMPT (declared
  `cli:|route:|tool:|hook:|plugin:|dynamic:` scheme, accepted on trust in v1) / ORPHAN (fail).
  Read-only at runtime.

## Tournament marketplace (`prd_taskmaster/tournament/`)

The trustworthy two-gate signal feeds a **settled tournament**: N executors race one job →
every submission is adjudicated through both gates → the winner is paid in **AtlasCoin** →
a UCB reputation store routes the next job to the cheapest proven-capable executor.

- `tournament-run` / `tournament-status` CLI; flow is `spawn → collect → adjudicate → settle
  → reputation` (`cmd.py`), with anti-sybil slots released in a crash-safe `finally`.
- `collect.py` is the security core — **commit-reveal** (`commit_hash = sha256(diff base..HEAD)`)
  defeats the diff-copy attack. `antisybil.py` enforces per-job / per-operator economic caps.
- `goose_backend.py` is the cheap-API racer (one OpenRouter model via `goose run`).
- **Invariants (enforced + tested — keep them):** **shadow-slash only** until an independent
  out-of-band watcher exists (proven cheating is logged, no AtlasCoin burned); honest losers
  are **always refunded**; **AtlasCoin is conserved** (no mint/burn, even under account aliasing).

## The spine (`atlas-protocol`, separate repo)

The gates shell out to the **spine CLI** (`atlas oracle` / `atlas tournament settle` / ledger),
which lives in the `atlas-protocol` repo (branch `dev`) and runs via `tsx` today. Point
`ATLAS_ORACLE_CMD` at it (e.g. `tsx apps/cli/src/index.ts`) for the real-podman e2e gates.
Packaging the spine for production is on the roadmap — see CHANGELOG `## [5.3.0]`.

## Backend model (v4.1+)

TaskMaster is one pluggable backend, not a prerequisite. *"Atlas speaks TaskMaster
natively — but doesn't need it."*

- Backend resolution: `backend: auto|taskmaster|native` in `.atlas-ai/fleet.json`
  (auto = taskmaster iff binary ≥0.43 present, else native). The 5-op protocol
  (detect / init_project / parse_prd / expand / rate) lives in `prd_taskmaster/backend.py`.
- **Task-state ops are engine-native ALWAYS**: use `python3 script.py next-task` and
  `python3 script.py set-status <id> <status>` (or the MCP tools `next_task` /
  `set_task_status`). Never call bare `task-master` commands outside a Mode-B-labeled
  block — structural tests enforce this.
- No API keys → backend returns a structured `agent_action_required` payload; the driving
  agent does the generation itself. Never a crash, never a hard requirement.
- The normative reference is the **"## Backend operations" table in SKILL.md**. When docs
  and code disagree, fix the docs to match the table.

## Task execution workflow

1. `python3 script.py next-task` — get the next dependency-ready task
2. `python3 script.py set-status <id> in_progress`
3. Implement (follow the plan step linked to the task)
4. `python3 script.py set-status <id> done`
5. Repeat. TodoWrite for user visibility; tasks.json is the source of truth.

## Commands

```bash
pytest tests/ -q                                   # full suite (872); the 4 real-podman e2e gates
                                                   #   auto-skip unless the env below is set
ATLAS_ORACLE_CMD="<spine>/node_modules/.bin/tsx <spine>/apps/cli/src/index.ts" \
  pytest tests/core -q -k "e2e or dogfood"         # un-skip the 4 real-podman gates (need the spine CLI + podman)
python3 script.py engine-preflight                 # one-call environment + backend probe
python3 script.py validate-tasks <tasks.json>      # gate before any tasks.json write
python3 script.py reachability-sweep               # Gate 6 — orphan-module detection
python3 script.py tournament-run                   # settled marketplace: spawn→…→reputation
python3 script.py economy-report                   # cost ledger from .atlas-ai/telemetry.jsonl
```

## Conventions (engine code)

- **Stdlib only** in `prd_taskmaster/` and `mcp-server/server.py` — no new dependencies.
  CI enforces stdlib-only imports on a bare runner.
- Errors return FR-28-safe dicts; library code never `sys.exit`s.
- All `.atlas-ai/*.jsonl` writes go through the shared flock-guarded append
  (`economy.append_telemetry` pattern).
- Tests are hermetic (tmp_path, no network). Structural tests in `tests/plugin/` enforce
  doc invariants — if you change SKILL.md or installer text, run them.
- Agents record how each run went via the feedback tool (`feedback_submit` MCP tool /
  `script.py feedback-add` → `.atlas-ai/feedback.jsonl`) — this is the product's
  improvement loop; use it at debrief time.
