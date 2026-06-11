# Dogfood Report — first live Atlas Fleet run (2026-06-11)

Phase B's acceptance gate (B-Task 12): the execute-fleet contract driven end-to-end against a
real 8-task sample project (`wordkit`, stdlib word utilities) with autonomous Claude worker
sessions spawned via atlas-launcher. **Result: `SHIP_CHECK_OK` emitted exactly once, exit 0,
on the `fleet-integration` branch.**

## Acceptance criteria — all met

| Criterion | Evidence |
|---|---|
| fleet-integration branch with all worker branches merged | head `3c9c05f`; 8 `--no-ff` merges, sequential, orchestrator-only |
| Every task done | 8/8 `status: done` in tasks.json (sole-writer updates) |
| CDD card per task | `.atlas-ai/cdd/task-{1..8}.json` on the integration branch |
| One inbox completion message per task | durable inbox messages (ids 107–112 + tasks 7, 8), all `task_handoff` with payload JSON per contract v1 |
| Negative test | worker `fleet-w2-task4` killed mid-task 13:13:15Z (no CDD card) → re-queued ONCE → re-queue verified DONE and merged; never falsely done |
| SHIP_CHECK_OK exactly once | ship-check exit 0 after the Gate-2 fix below |
| main never auto-touched | all fleet work on `fleet-integration` + worker branches |

Every completion claim was independently verified before merging (CDD card present, evidence
exit-0, tests re-run in the orchestrator's shell, commit-scope audit) — no worker's word was
ever counted directly.

## Contract mechanisms exercised live

- `prompt_injected: false` detection + single re-kick (workers 1, 7) — both recovered.
- Worker self-start from the handoff file (worker 2) — faster than the kick path.
- `DONE_WITH_CONCERNS` honesty (worker 5: swept a tracked `.pyc`, recommended the fix — accepted).
- Worker push-back on stale context (worker 7: detected a stale wave-1 handoff file, executed
  the authoritative inline contract, reported the discrepancy).
- Explicit model routing (worker 8 spawned with `model="sonnet"`, standard tier).

## Findings → fixes (all landed during the run)

1. **ship-check Gate 2 rejected the engine's own flat tasks.json format** (only read tagged
   `master.tasks`). The engine's first SHIP_CHECK_OK attempt failed on its own output. Fixed in
   both `skel/ship-check.py` and `prd_taskmaster/shipcheck.py` + regression test (`6db8179`).
2. **Workers' `git add -A` swept launcher spawn metadata** (`.claude/handshake.json`,
   `spawn-meta.md`) → add/add merge conflicts AND a stale handoff file propagating to later
   waves. Worker contract now forbids committing `.claude/`/`__pycache__`; fleet projects
   gitignore them.
3. **TDD red-phase output in evidence files trips strict Gate 5.** Worker contract now mandates:
   evidence = final verification run only; intermediate red runs go to `.atlas-ai/logs/`
   (`2be055c`).
4. **Default-model spawns waste capacity** (first waves ran on the default model). Directive
   encoded: every spawn passes an explicit tier-matched model (`fleet.json` routing /
   `resolve_backend`).

## Honest caveats

- All workers were Claude. The codex/gemini experimental wave was NOT run: the RUNNING
  launcher predates `d757905` (the `backend` param lives on the `feat/session-spawn-backend`
  worktree branch, not yet merged/restarted into the live server). Deferred to the launcher's
  next release; `experimental_backends` remains false by default, matching the documented
  posture ("Claude today, Codex/Gemini experimental").
- Wave scheduling came from `compute_fleet_waves`; merges were conflict-free after the
  metadata fix, so the conflict→fix-task path was exercised only by the benign metadata case.
- The orchestrator was this session (Fable 5) following `skills/execute-fleet/SKILL.md`
  manually as its first executor; the skill text held up — every situation that arose was
  covered by a written rule.
