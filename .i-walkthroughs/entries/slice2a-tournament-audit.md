---
id: slice2a-tournament-audit
title: Slice-2A settled-tournament — headless live-evidence walkthrough audit
surface: tournament settlement system (TS spine + Python engine orchestrator)
mode: headless
first_check:
  method: fresh-eyes live-evidence audit (9 independent auditors, one per surface; live test/CLI/e2e runs as evidence)
  result: 2 surfaces SOLID (collect, goose); 7 surfaces DEFECT_FOUND — 2 blocking + 5 important + 9 minor
second_check:
  method: per-fix fresh re-run of the exact broken scenario (before→after) + full-suite regression
  result: pass
regression_scan: pass
regression_checks:
  - "atlas-protocol full suite: pnpm -r run test green (122 core + 28 cli)"
  - "engine full suite: python3 -m pytest -q → 868 passed on the reconciled branch"
  - "real-podman e2e re-run green with genuine discrimination (fake oracle exitCode=1)"
verdict: resolved
status: shipped
---

## What the audit found (and fixed)

A headless live-evidence walkthrough (`--headless` mode: deliverable surfaces are "screens"; live test/CLI/e2e runs are the authoritative evidence) caught real issues build-time review missed:

**Blocking (TS CLI):**
- A missing `--job` dir threw to stderr with EMPTY stdout → the Python orchestrator's `json.loads` chokes. Fixed: validate job dir → stage-tagged `{ok:false,stage:'parse_input'}` envelope; top-level catch always emits JSON.
- The `settled.json` marker was written AFTER the ledger mutation → a crash between them left the winner paid-but-unmarked and permanently stuck. Fixed: `settling.json` intent marker written BEFORE the state save + resumable detection (`partial_settle_needs_repair`).

**Important:** stale `.settle.lock` permanently blocked settle (fixed: pid/TTL reclaim); `sweep_expired` tz-naive/aware crash (fixed: normalize to UTC); roster rollback only caught `SybilLimitError` → slot leak (fixed: broaden to any exception); the **capstone e2e was non-discriminating** — `fake` failed for an infra/card-hash reason (`exitCode:null`) not a genuine reward-hack, and assertion-4 (`win credited bounty`) passed without a bounty (fixed: `fake` is now a real reward-hacker with a matching FAIL-content card → oracle `exitCode=1`; assertion tightened to `>=60`; strict `ledger verify ok:true`).

**Minor:** integer-only AC enforced at the settlement layer; in-contract `FAIL` verdict (not out-of-union `ERROR`); finite/non-negative `settled_cost`; accurate `reputation_recorded`/`settle_envelope_stage` flags; shared `verify` validation.

## Second-Check evidence (resolved)
Every fix was re-run fresh against the exact scenario the audit proved broken (before→after numeric assertion) and gated on the full suite. The capstone e2e now runs the real podman oracle and genuinely discriminates: `win`=PASS/exitCode0 wins & is paid (free 10→65), `fake`=FAIL/exitCode1 is shadow-logged in `wouldSlash`, AC conserved (158==158), ledger + tournament verify ok, reputation routes (explore cold-start + exploit winner). No fix was reported done until its scenario re-ran clean AND the full suite stayed green.

## Trap named
Build-time review tests the happy path + designed error paths; it does NOT test plausible *operational* failure modes (a wrong path from a caller → stderr-only; a crash between two durable writes; an infra-FAIL masquerading as a caught cheat). The headless live-evidence audit — run each surface for real and adversarially probe the holes — is what surfaced them. Reusable rule: a green unit suite is necessary, not sufficient; a fresh independent live-evidence pass per surface is the second axis.
