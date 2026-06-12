# Agent Instructions — Atlas

> Applies to ANY agent harness working in this repo (Codex, Gemini, Claude Code, or the
> next one). Claude Code also reads CLAUDE.md, which carries the same contract.

## The end goal (north star — test every change against this)

Atlas's entry point is a frontier model acting as the **driver**. The driver understands
the user's intent using skills built for it, then — inside a loop — decomposes the goal
into optimal components and routes each to the **cheapest capable executor**, saving as
many tokens as possible while delivering an outcome as good as if the frontier model had
done all the work itself, at a fraction of the cost.

The executor pool is **any CLI agent harness plus direct API paths, all in parallel** —
never a fixed provider list. Every feature decision is tested against: *does this make
the frontier-driver-decomposes-to-cheap-executors loop better, cheaper, or more provable?*

The four moats (why this is a product, not a prompt pack):
1. Cross-vendor arbitrage — route work across any harness/API by cost and capability.
2. Engine-enforced unfakable gates — validate-tasks, ship-check (`SHIP_CHECK_OK`),
   structural tests. A feature isn't a product feature until the engine enforces it.
3. Persistent vendor-neutral task graph — tasks.json survives across vendors/sessions.
4. Cross-vendor cost ledger — telemetry + economy-report prove the savings.

## Backend model (v4.1+)

TaskMaster is one **optional** pluggable backend. Backend resolution is
`backend: auto|taskmaster|native` in `.atlas-ai/fleet.json`; the 5-op protocol
(detect / init_project / parse_prd / expand / rate) lives in `prd_taskmaster/backend.py`.

- **Task-state ops are engine-native ALWAYS**: `python3 script.py next-task` and
  `python3 script.py set-status <id> <status>` (MCP: `next_task` / `set_task_status`).
  Never call bare `task-master` outside a Mode-B-labeled block — structural tests
  enforce this.
- No API keys → the backend returns a structured `agent_action_required` payload and YOU
  (the driving agent) do the generation, validated through `validate-tasks` before any
  write. Never a crash.
- The **"## Backend operations" table in SKILL.md is normative**. When docs and code
  disagree, fix the docs to match the table.

## Working rules

- `pytest tests/ -q` must stay green; run it before claiming anything is done.
- **Stdlib only** in `prd_taskmaster/` and `mcp-server/server.py` — no new dependencies
  (CI enforces this on a bare runner).
- Errors return FR-28-safe dicts; library code never `sys.exit`s.
- All `.atlas-ai/*.jsonl` writes go through the shared flock-guarded append.
- Tests are hermetic (tmp_path, no network). `tests/plugin/` structurally enforces doc
  invariants — run it after touching SKILL.md or the installer.
- At debrief time, record how the run went: `feedback_submit` MCP tool or
  `python3 script.py feedback-add` → `.atlas-ai/feedback.jsonl`. This feedback loop is
  how Atlas improves; treat it as part of finishing the job.
