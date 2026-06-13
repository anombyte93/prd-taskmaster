# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.2.0] — 2026-06-13

Progress visualization — the README/UX-SPEC panels are now real output.

### Added
- **`status` command + `render_status` MCP tool** that draw the boxed Atlas progress
  panels from real pipeline state: phase tracker, the GENERATE validation scorecard
  (grade bar + checks + line-located warnings + placeholders + task/subtask counts),
  the preflight capability panel, the handoff panel, the execute progress bar, and the
  ship-check gates panel. `--format boxed|ascii|json`, `--all`, `--phase`.
- `prd_taskmaster/render.py` (pure renderer, UX-SPEC §7 symbol grammar with ASCII
  fallbacks via `ATLAS_ASCII=1`; display-width-aware so borders align even with the 🔒
  emoji) and `prd_taskmaster/status.py` (pure reader of pipeline/tasks/validation state).
- `validate-prd` now persists its result to `.atlas-ai/state/validation.json` so the
  scorecard renders without recomputation.
- Phase skills (setup, generate, handoff, execute-task) render the matching panel at
  each phase boundary.

### Changed
- The grade bar floors rather than rounds (49/57 = 86% → 8/10 filled), matching the
  README mockup and never inflating a grade.
- UX-SPEC pricing mockups marked superseded by the private-pilot decision (no `$29`).

## [5.1.2] — 2026-06-13

Honesty + positioning + discoverability.

### Added
- **Pre-alpha status** is now stated up front (badge + Project status section): the newer systems
  (fleet, backend abstraction, token economy, Pro MCPs) are not yet battle-tested; expect
  breaking changes.
- PRD validation warnings (vague language + placeholders) now carry **line numbers** — the
  "quoted + located, not just counted" claim is now executable truth, not just rendering.
- `package.json` `keywords` for npm search discoverability (factual token-economy /
  cost-ledger / model-routing mechanism terms — no unproven savings claims).

### Changed
- **Atlas Pro reframed as a private pilot.** Not generally available, not for sale; pricing
  removed. Access is granted at discretion during the pilot; "Get Atlas Pro" CTAs become "Request
  pilot access" pointing at GitHub Discussions (an `atlas-ai.au/pilot` signup page is in progress).

## [5.1.1] — 2026-06-13

Audit-driven honesty release (dogfood cycle 6 — the engine ran its own pipeline on this work).

### Added
- **Placeholder hard fail.** Any placeholder — `{{...}}`, bracketed, or bare case-sensitive
  `TBD`/`TODO` — now floors the PRD grade to NEEDS_WORK, sets `hard_fail` in the result, and
  makes `validate-prd` exit non-zero. The README's rigor claim is now executable truth.
- Installer pins its clone to its own release tag (`--branch v$VERSION`, branch fallback).

### Fixed
- `atlas-ai.au/install` and `atlas-ai.au/pro` now resolve (Cloudflare single-redirects) —
  the recommended install path 404'd at 5.1.0 launch.
- README discloses the audit-logged ship-check admin override, the npm `postinstall` pip
  step, and marks the local research proxy bring-your-own.
- Marketplace manifest description no longer reads as an internal testing artifact.

## [5.1.0] — 2026-06-13

First npm publish (`prd-taskmaster@5.1.0`). This release consolidates the two development
lines into one artifact and re-launches the repo as an **open-core** product: a free MIT
engine plus a commercial **Atlas Pro** tier.

**Lineage**: the public v4.x line (this repo) absorbed the private v5.x plugin line
(`prd-taskmaster-plugin`, internal name "atlas-go", final state `v5-final` @ `f140490`) via
file-level imports marked with `Imported-From:` commit trailers — state machine, ship-check
gates, execute-task hardening, npm pack hygiene, and the granular validation test suite.
Versioning continues from the higher v5.x line so the consolidated artifact supersedes both.

### Added (5.1.0 consolidation)
- Plugin namespace renamed `prd-taskmaster` → **`prd`** — commands are now `/prd:go` etc.;
  MCP tool ids are `mcp__plugin_prd_go__*` (old prefixes kept as legacy allowed-tools aliases).
- Per-directory `.npmignore` files keep Python bytecode out of the npm tarball (npm 11
  ignores the root `.npmignore` inside `files[]`-allowlisted directories).
- 21 granular PRD-validation tests ported from the plugin suite (`tests/core/test_validation.py`).
- Setup/execute-task skills resolve the customizations starter pack and `ship-check.py`
  from the packaged `${CLAUDE_PLUGIN_ROOT}/skel/` (previously referenced a developer-machine path).

The notes below document the v4.0.0 line that this release ships for the first time.

### Added
- **Token economy** (`token_economy`: conservative|balanced|performance) — per-op-class start
  tiers, validator-gated escalation with per-mode ceilings, and economy-aware provider
  configuration. Verified priors and sources in `docs/product/MODEL-ECONOMY.md`.
- **Parallel native TaskMaster expansion** (`tm-parallel` / `tm_parallel_expand`) — TaskMaster's
  model-agnostic `expand --research` runs concurrently in isolated workdirs (per-task economy-tier
  models), merged atomically; the Claude-subagent path becomes the documented fallback.
- **Local cost telemetry** (`.atlas-ai/telemetry.jsonl`) + `economy-report` summarizer.
- **Unified deterministic core** (`prd_taskmaster/`) — a single stdlib-only Python package that
  is the one source of truth for PRD validation, task calculation, complexity enrichment,
  capability detection, the pipeline state machine, and the ship-check gate. Imported by both the
  zero-dependency skill (`script.py`) and the FastMCP plugin (`mcp-server/server.py`).
- **5-phase gated pipeline** — `SETUP → DISCOVER → GENERATE → HANDOFF → EXECUTE` with atomic
  compare-and-swap transitions over a flock-guarded `pipeline.json`.
- **CDD execute loop** — `skills/execute-task` runs a 13-step contract-driven cycle with evidence
  cards; completion is gated by a deterministic `SHIP_CHECK_OK` token (a non-zero exit code in any
  evidence file blocks it).
- **Parallel research fan-out** (`prd_taskmaster/parallel.py`) — `plan`/`apply` research packets
  let an agent expand tasks across parallel subagents and merge results atomically.
- **`/atlas` command** — the primary user-facing invocation (alias of the orchestrator skill).
- **Product + UX specs** (`docs/product/`) — the living contract the dogfood ship-check verifies
  against.
- **Atlas Pro teaser** — the handoff surfaces **Atlas Fleet** (parallel multi-session execution)
  as a locked, clearly-priced upgrade. The free engine stays fully functional standalone.

### Changed
- Repo keeps the name **prd-taskmaster** (and its 508★). The product/command brand is **Atlas**;
  the internal "atlas-go" name from the plugin line is retired.
- PRD validation is stricter than older internal versions (grade thresholds + placeholder
  attribution). PRDs that previously passed loosely may now score lower — by design.
- Two install paths from one repo: curl one-liner (zero-dependency skill) and Claude Code plugin /
  `npm install` (full FastMCP plugin).

### Fixed
- Ship-check tests aligned to the live `skel/ship-check.py` gate contract (3 stale-schema
  failures resolved).

### Lineage
v4.0.0 merges the **prd-taskmaster-v2 skill line** (internally versioned 2.x, never published) and
the **atlas-go plugin line** (internally 5.x, never published) back into this repository. Those
internal version numbers do not appear as tags here; the public lineage runs
v3.0.0 → v4.0.0.

## [3.0.0] — 2026-02-12
- Codified deterministic operations into `script.py`; curl installer with update notifications;
  template-based PRD and CLAUDE.md generation; community files. (Pre-merge single-skill product.)
