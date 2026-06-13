# Dogfood Cycle 6 — Atlas fixes Atlas (npm-page honesty release)

**Date:** 2026-06-13 · **Shipped:** `prd-taskmaster@5.1.1` · **Gate:** `SHIP_CHECK_OK`

The most pointed dogfood yet: the engine ran its **own pipeline** to fix its **own**
npm-page claims. An executed claim-audit of `npmjs.com/package/prd-taskmaster@5.1.0` found
the engine honest about its substance but broken at its front door. We turned the audit
findings into a PRD, let the engine grade and parse it, then executed the fixes under CDD
with evidence per task and the engine's ship-check as the completion gate.

## The pipeline ran on itself

| Phase | What happened |
|---|---|
| SETUP | `engine-preflight` → backend native, TaskMaster 0.43.1; pipeline advanced `null → SETUP`. |
| DISCOVER | Discovery evidence = the executed npm-page audit (auditor agent), not a brainstorm. |
| GENERATE | PRD `(.taskmaster/docs/prd-cycle6.md)` written from the audit; **the engine graded its own fix-PRD EXCELLENT (94.7%, 54/57)** and parsed it into 5 dependency-ordered tasks under tag `cycle6`. |
| HANDOFF | Plan to `.taskmaster/docs/plan.md`, mode controller-CDD. |
| EXECUTE | 5 tasks `claim_task` → CDD card → evidence → `set-status done`, finishing at **SHIP_CHECK_OK**. |

## The five fixes

1. **Placeholder hard-fail (made the claim true).** The README said bare `TBD`/`{{...}}`/`TODO`
   were "a hard fail"; the audit proved they were a warning + ≤10-pt penalty, and bare forms
   weren't detected at all. Now any placeholder floors the grade to NEEDS_WORK, sets
   `hard_fail`, and `validate-prd` exits non-zero. Lowercase prose ("a todo app") stays clean.
2. **Edge redirects.** `atlas-ai.au/install` and `/pro` 404'd at the 5.1.0 launch — the
   recommended first command was dead. Two Cloudflare single-redirects fixed both; a full
   sandboxed install through `atlas-ai.au/install` now completes.
3. **README honesty.** Placeholder wording matched to landed behavior; the ship-check admin
   override disclosed (it's audit-logged and `[OVERRIDE]`-marked, never silent); npm postinstall
   pip step disclosed; the local research proxy marked bring-your-own.
4. **Hygiene.** Marketplace manifest describes its public purpose; the installer clones pinned
   to its own release tag with a branch fallback.
5. **Ship 5.1.1.** Version quintet bumped, CHANGELOG entry, 301/301 tests, CI 7/7 green, tag +
   GitHub release, published to npm (registry shasum `0f5df27b…`), fresh-dir install verified.

## What the dogfood proved

- The engine's grader is trustworthy enough to gate its own release PRD (EXCELLENT, self-test).
- The unfakable ship-check is real: `SHIP_CHECK_OK` only emitted after all 5 tasks carried CDD
  cards and evidence with zero non-zero exit codes — the same gate it sells to users.
- "Fix, don't cut" (Jobs Lens): the false placeholder claim was made **true** rather than
  softened — the harder, better path.

The npm page is now honest behind a working front door, verified by the product that ships it.
