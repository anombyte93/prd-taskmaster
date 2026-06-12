# Dogfood: Native Backend End-to-End (v4.1-T8)

> 2026-06-12 · branch v4-merge · engine 4.0.0 · 254 tests green
> The north-star proving gate: the engine runs TaskMaster-free on both native paths,
> with the cost ledger and feedback loop live.

## Run 1 — agent path (no API keys)

Scratch project with `.atlas-ai/fleet.json` = `{"backend": "native"}`, all AI keys
stripped from the environment (`env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`).

- `backend-detect` → `{"ok": true, "selected": "native", "source": "config", "ai_ops": "agent"}` —
  TaskMaster's presence on the machine was reported but not required.
- `parse-prd --input prd.md --num-tasks 5` → no crash, no key demand: a structured
  `agent_action_required` payload carrying the op, the full tasks.json `schema_hint`,
  and the `then` checklist (write → ≥2 subtasks each → validate-tasks → tag).
- The driving agent (Claude, this session) generated the 5 tasks per the hint, then:
  - `validate-tasks` → `{"ok": true, "task_count": 5, "subtask_count": 10}`
  - `next-task` → task 1 served from the engine-native selector.

This is the universal fallback: any agent harness that can read JSON can drive Atlas
with zero API keys and zero TaskMaster.

## Run 2 — API path (key present, cheap model)

Same fleet.json, `OPENAI_API_KEY` present; `llm_client` discovery resolved the
openai-compatible provider with its default `gpt-4.1-mini`.

- `parse-prd --input prd.md --num-tasks 5` →
  `{"ok": true, "task_count": 5, "backend": "native", "ai": "api", "validation": {"ok": true, "task_count": 5, "subtask_count": 10}}` —
  generation, schema validation, and tagged write in one call, 17.5s wall.
- Telemetry row (`.atlas-ai/telemetry.jsonl`), with real token usage from the API
  response (P2):

  ```json
  {"op_class": "structured_gen", "model": "gpt-4.1-mini", "backend": "native-api",
   "exit": 0, "tokens_in": 384, "tokens_out": 1240, "wall_ms": 17505}
  ```

- `economy-report` costs block over that run:

  ```json
  {"naive_baseline_model": "claude-fable-5", "est_cost_usd": 0.0, "naive_cost_usd": 0.0,
   "est_saved_usd": 0.0, "priced_calls": 0, "unpriced_calls": 1,
   "token_coverage": 1.0, "priced_coverage": 0.0}
  ```

  Read this honestly: tokens were measured on 100% of calls (`token_coverage`), but
  `gpt-4.1-mini` has no entry in `PRICES_PER_MTOK` (the map carries only rates
  verified in MODEL-ECONOMY.md §1), so the $ figures correctly cover zero calls
  rather than inventing a price. Runs routed to priced Claude tiers produce real
  `est_saved_usd` numbers — the test suite pins that math
  (`tests/core/test_economy_report.py`).

## Feedback loop

Both dogfood observations were recorded through the new feedback tool
(`script.py feedback-add` → `.atlas-ai/feedback.jsonl`), closing the
any-agent-reports-how-it-went loop on its first day.

## Follow-ups surfaced by dogfooding

1. Extend `PRICES_PER_MTOK` with verified non-Anthropic rates (OpenAI, Codex credit
   conversion) so cross-vendor runs price into `est_saved_usd`.
2. `parse-prd` API-path success currently reports the validated write; consider
   echoing the telemetry row reference for one-call auditability.
