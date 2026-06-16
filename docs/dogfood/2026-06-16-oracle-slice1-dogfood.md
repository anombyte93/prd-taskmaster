# Oracle Slice-1 DOGFOOD — cross-repo acceptance test

**Date:** 2026-06-16
**Task:** 5.3 — cross-repo DOGFOOD acceptance test (capstone of Slice 1)
**Test:** `tests/core/test_oracle_dogfood.py` (engine worktree)
**Status:** GREEN — 3/3 passed (real podman, real CLI, real ship-check subprocess; no mocks)

## What was proven

The unfakable Atlas oracle gates a real `prd-taskmaster` ship-check end-to-end.
For each DONE task, `skel/ship-check.py` (Gate 5) shells `atlas oracle grade`,
which checks out the submitted commit into a throwaway worktree, **overlays the
operator-held tests over the submitter's tree**, re-executes the card's grading
command inside a digest-pinned podman sandbox, derives `PASS` iff exit 0, and
appends a tamper-evident ledger event.

1. **Genuine pass ships.** Operator-held `grade.sh` = `exit 0`. Ship-check emits
   `SHIP_CHECK_OK`, returncode 0, and the ledger records `verdict == "PASS"`.
2. **Reward hack blocked (the acceptance criterion).** The submitter ships a
   cheat — a committed `grade.sh` that always `exit 0` — while the operator-held
   `grade.sh` is `exit 1`. The cheat does **NOT** ship: the oracle overlays and
   re-executes the operator's copy, so the verdict is `FAIL`. `SHIP_CHECK_OK` is
   absent, returncode is non-zero, stderr names the oracle FAIL for task 1, and
   the ledger records `verdict == "FAIL"`. **Non-vacuous:** the only difference
   between case 1 and case 2 is which `grade.sh` the oracle re-runs — the
   submitter's committed copy never reaches the verdict.
3. **Ledger integrity.** `atlas ledger verify <dir>` reports
   `{"ok": true, "eventCount": 1}` after the genuine pass.

## ATLAS_ORACLE_CMD used

```
ATLAS_ORACLE_CMD="/home/anombyte/Hermes/current-projects/.worktrees/atlas-coin-oracle/node_modules/.bin/tsx /home/anombyte/Hermes/current-projects/.worktrees/atlas-coin-oracle/apps/cli/src/index.ts"
```

`ship-check.py` shlex-splits `ATLAS_ORACLE_CMD` and appends
`oracle grade --repo <root> --commit <HEAD> --card ... --held ... --evidence ... --ledger ...`.

**Why `tsx` on the CLI source and not `node dist/index.js`:** the spine
monorepo's workspace packages (`@atlas-protocol/core|cards|evidence|executor`)
declare `exports: "./src/index.ts"`, so the compiled `apps/cli/dist/index.js`
resolves its workspace deps to TypeScript sources that bare `node` cannot load
(`ERR_MODULE_NOT_FOUND: .../packages/executor/src/grade.js`). The `tsx`
executable runs the identical CLI code path the spine's own vitest suite uses,
with **no edits to the spine repo**. (Building the CLI — `pnpm --filter
@atlas-protocol/cli build`, plus `pnpm -r build` for the workspace deps — was
done as Step 0 and is required so the source resolves; the dist itself is not
the run target.)

## Observed results

### Pass case (operator-held `grade.sh` = `exit 0`)

```
$ ATLAS_ORACLE_CMD="$TSX $SRC" python3 skel/ship-check.py --cwd /tmp/ev_pass
SHIP_CHECK_OK
rc=0
```

Ledger event payload (excerpt):

```json
{
  "type": "verification.completed",
  "actor": { "kind": "executor", "id": "oracle" },
  "lifecycleState": "verification_passed",
  "payload": { "verdict": "PASS", "exitCode": 0, "overlayHash": "sha256:..." }
}
```

### Reward-hack case (submitter cheat `exit 0`, operator-held `exit 1`)

```
$ ATLAS_ORACLE_CMD="$TSX $SRC" python3 skel/ship-check.py --cwd /tmp/ev_hack
rc=1
--- stdout (empty — no SHIP_CHECK_OK) ---
--- stderr ---
FAIL: task 1: oracle verdict FAIL
```

The committed cheat (`exit 0`) was overlaid away by the operator-held `exit 1`
and re-executed in the sandbox → verdict `FAIL` → ship blocked.

## pytest

```
$ python3 -m pytest tests/core/test_oracle_dogfood.py -v
tests/core/test_oracle_dogfood.py::test_genuine_pass_ships PASSED   [ 33%]
tests/core/test_oracle_dogfood.py::test_reward_hack_blocked PASSED  [ 66%]
tests/core/test_oracle_dogfood.py::test_ledger_integrity PASSED     [100%]
============================== 3 passed in 13.05s ==============================
```

## Slice-2 hardening note

The Graded Card's `contentHash` is a syntactically valid placeholder.
`gradeSubmission` does not re-verify `contentHash` against the card body in
Slice 1 (it is only echoed into the ledger payload). Slice 2 should recompute
and verify it before grading so a tampered card body cannot be graded under a
stale hash. (Also tracked in the executor's `SLICE-1` deferral comments:
infra-failure exit codes are currently recorded as `FAIL`, and `evidenceRef`
records a path rather than a `sha256:`-prefixed content ref.)
