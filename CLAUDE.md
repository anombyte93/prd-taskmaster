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
   structural tests. If a feature could be a skill, it's not a product feature until the
   engine enforces it.
3. **Persistent vendor-neutral task graph** — tasks.json survives across vendors/sessions.
4. **Cross-vendor cost ledger** — telemetry + economy-report prove the savings.

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
pytest tests/ -q                                   # full suite — must stay green
python3 script.py engine-preflight                 # one-call environment + backend probe
python3 script.py validate-tasks <tasks.json>      # gate before any tasks.json write
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
