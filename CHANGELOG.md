# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — v4.0.0 (in progress)

The v4.0.0 release merges two previously-unpublished internal lines back into this repo and
re-launches it as an **open-core** product: a free MIT engine plus a commercial **Atlas Pro**
tier.

### Added
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
