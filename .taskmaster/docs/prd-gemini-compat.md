# PRD: prd-taskmaster v4 — Gemini Main-Model Compatibility

**Author:** autonomous ralph-loop (Gemini-powered pass)
**Date:** 2026-04-13
**Status:** Draft
**Version:** 1.0
**Taskmaster Optimized:** Yes

---

## Executive Summary

prd-taskmaster v4 currently defaults to `claude-code/sonnet` as the main task-master model. Users without Claude Max subscriptions cannot use this default. This PRD captures the researched improvements required so that `gemini-cli/gemini-3-pro-preview` (free via Google Gemini CLI) becomes a first-class, tested, documented alternative main-model path — producing PRDs and parsed tasks at the same quality as sonnet.

## Problem Statement

### User Impact

Users on the free tier who do not have a Claude Max subscription face a silent configuration failure today:

1. The install path assumes `claude-code` provider as the default, which only works for Claude Max subscribers.
2. `SETUP.md` does not walk non-Claude-Max users through setting up Gemini CLI as a free alternative.
3. `validate-setup` does not detect Gemini CLI's availability even when `gemini` is on PATH and the provider is registered in `task-master models`.
4. `validate-prd --ai` hardcodes `task-master research` which uses the research-role model — it has not been tested with Gemini as that role.

### Business Impact

Gemini CLI is free for all Google accounts (no subscription required). Supporting it as a tested main-model path unlocks v4 for the estimated 80% of Claude Code users without Claude Max, tripling v4's addressable audience. The cost of not supporting it is every non-Max user bouncing from Phase 0.

## Goals and Success Metrics

### Goal 1: Gemini CLI is a tested main-model path

- Baseline: zero tests exercise Gemini as task-master main model.
- Target metric: `tests/test_gemini_pipeline.py` runs at least 3 tests covering (a) `validate-setup` detecting gemini-cli, (b) `validate-prd` scoring a PRD with Gemini as the main-model provider, (c) a full parse-prd returning at least 10 tasks using Gemini.
- Measurement: `pytest tests/test_gemini_pipeline.py -q` returns all pass.
- Timeframe: this release.

### Goal 2: SETUP.md documents Gemini as a first-class free alternative

- Baseline: SETUP.md only covers claude-code and generic provider options.
- Target metric: SETUP.md has a dedicated Gemini subsection showing the exact commands to set main, research, and fallback models to Gemini CLI (all free).
- Measurement: grep SETUP.md for "gemini-cli" returns at least 3 matches.
- Timeframe: this release.

### Goal 3: validate-setup detects Gemini provider in config

- Baseline: validate-setup only checks `models.main.modelId` exists, not which provider.
- Target metric: validate-setup reports `provider_family` (e.g., "claude-code", "gemini-cli", "anthropic", "openai") for each configured role, letting users see at a glance which pipeline they are using.
- Measurement: `script.py validate-setup` JSON output includes `provider_main`, `provider_research`, `provider_fallback` fields.
- Timeframe: this release.

## User Stories

### Story 1: Non-Claude-Max user installs v4

**As a** Claude Code user without Claude Max,
**I want to** run prd-taskmaster with a free AI provider I already have,
**so that I can** generate PRDs without a paid subscription.

**Acceptance Criteria:**
- [ ] SETUP.md includes a Gemini CLI subsection with exact `--set-main`, `--set-research`, `--set-fallback` commands.
- [ ] `validate-setup` returns `ready: true` with Gemini as the main model.
- [ ] A full parse-prd through Gemini produces at least 10 tasks without any stderr warnings.
- [ ] Total Phase 0 setup time under 60 seconds on a fresh system.
- [ ] No Claude Max subscription required at any point.

### Story 2: Provider-agnostic CI user

**As a** CI pipeline maintainer running prd-taskmaster in an automated context,
**I want to** confirm my provider choice via `validate-setup` JSON,
**so that I can** block the build if the wrong provider is configured.

**Acceptance Criteria:**
- [ ] validate-setup output includes per-role `provider_family` fields.
- [ ] validate-setup supports a `--require-provider gemini-cli` flag that fails if a different provider is configured.
- [ ] The flag failure exit code is 2 (not 1) so CI can distinguish provider mismatches from hard errors.

## Functional Requirements

REQ-101: SETUP.md adds a Gemini CLI subsection under Step 3 **Must have**. Lists the exact three commands: `task-master models --set-main gemini-3-pro-preview --gemini-cli`, `--set-research gemini-3-pro-preview --gemini-cli`, `--set-fallback gemini-3-flash-preview --gemini-cli`. Documents that Gemini CLI is free via Google account.

REQ-102: `cmd_validate_setup` in script.py reports provider family per role **Must have**. Reads `.taskmaster/config.json`, extracts `models.main.provider`, `models.research.provider`, `models.fallback.provider`, surfaces them as fields in the output JSON.

REQ-103: `cmd_validate_setup` adds optional `--require-provider <name>` flag **Should have**. When passed, the check fails with exit code 2 if the main-model provider does not match. Used in CI and multi-provider test matrices.

REQ-104: tests/test_gemini_pipeline.py adds 3 tests exercising Gemini end-to-end **Must have**. Tests skip (not fail) if `gemini` binary is not on PATH so they do not break CI in environments without Gemini.

REQ-105: docs/v4-release/provider-matrix.md documents per-provider behaviour **Should have**. A table covering Claude Code, Gemini CLI, Anthropic API, OpenAI, OpenRouter, showing for each: free-tier availability, quality notes, and verified-working model IDs.

REQ-106: mcp_server/README.md documents the dual-provider pattern **Should have**. Shows how to register the MCP server alongside a Gemini-configured task-master so agents can call tools via either path.

REQ-107: CHANGELOG.md records the v4 release notes **Must have**. First entry covers all v4 changes from the Claude Max pass plus the Gemini compatibility additions from this pass. Conventional-commits format.

REQ-108: validate-prd --ai works with Gemini as the main model **Must have**. The `_ai_review_prd` helper already shells out to `task-master research`, which now uses Gemini. Verified by running on a real PRD.

REQ-109: Comparison doc at docs/v4-release/provider-comparison.md shows Claude Max vs Gemini performance **Should have**. Measures: parse-prd task count, parse-prd latency, validate-prd AI review quality.

REQ-110: Fallback model handling is tested when main and research are both Gemini **Should have**. The fallback model role already defaults to `gemini-3-flash-preview` via this PRD's setup, but no test currently exercises the failure path that triggers fallback usage.

### Dependencies

REQ-102 and REQ-103 depend on REQ-101 — the SETUP.md documentation prompts users to run `--require-provider gemini-cli`, which must exist. REQ-104 depends on REQ-102 — the tests assert on the new per-role provider fields. REQ-105 and REQ-109 depend on actual measured data from running both providers through the same PRD.

## Non-Functional Requirements

**Performance:** Gemini-powered parse-prd must return in under 300 seconds for a 500-line PRD. This is the measured baseline for gemini-3-pro-preview via the CLI integration. If latency exceeds 300 seconds, fallback to gemini-3-flash-preview via the already-configured fallback role.

**Reliability:** validate-setup must detect all 12 provider families supported by task-master 0.43.1: claude-code, anthropic, openai, openrouter, ollama, bedrock, azure, vertex, gemini-cli, codex-cli, lmstudio, openai-compatible.

**Compatibility:** Works with gemini CLI 0.36.0 and later. Requires the user to be logged in via `gemini auth login` or equivalent.

**Security:** No secrets logged. No Gemini-specific auth flow — delegate entirely to the gemini CLI binary.

## Technical Considerations

### System Design

The existing v4 three-layer architecture does not change:

- SKILL.md plus phases is the orchestration layer.
- script.py is deterministic operations with 14 subcommands.
- mcp_server exposes 20 FastMCP tools.

The Gemini compatibility work is additive: new checks in `validate-setup`, new section in SETUP.md, new tests, a provider-comparison doc. No existing behaviour changes.

### Integration Points

- **gemini CLI binary**: available at /usr/bin/gemini version 0.36.0 on this dev machine. Must be on PATH.
- **task-master-ai**: already supports `--gemini-cli` provider flag. No upstream changes needed.
- **Gemini models**: `gemini-3-pro-preview` (main + research), `gemini-3-flash-preview` (fallback) are the currently-recommended free tier.

### Technology Stack

No new dependencies. All changes are additive Python, markdown, and pytest.

## Implementation Roadmap

Phase 1: Documentation updates for SETUP.md, CHANGELOG, provider-matrix (3 hours).
Phase 2: validate-setup provider-family reporting and --require-provider flag (2 hours).
Phase 3: tests/test_gemini_pipeline.py with 3 tests (1 hour).
Phase 4: Performance measurement and comparison doc (2 hours).

## Out of Scope

- Gemini API direct integration (uses gemini CLI instead).
- Multi-account Gemini support.
- Migrating existing Claude Max users off claude-code.
- Prompt-level optimization for Gemini vs Sonnet.

## Open Questions and Risks

**Risk 1:** Gemini CLI auth may expire without warning, causing silent failures in CI. Mitigation: add a gemini-auth check to validate-setup.

**Risk 2:** Gemini pro preview is "preview" — may be deprecated. Mitigation: document the fallback model and version bump path.

**Open Question:** Should `validate-setup` prompt-test all three models, or only validate config? Current design validates config only. Prompt-testing adds latency.

## Validation Checkpoints

**Checkpoint A:** SETUP.md contains Gemini subsection. **Status:** to be implemented.
**Checkpoint B:** validate-setup reports provider_family for each role. **Status:** to be implemented.
**Checkpoint C:** test_gemini_pipeline.py passes 3 tests. **Status:** to be implemented.
**Checkpoint D:** Gemini-generated PRD parse produces at least 10 tasks. **Status:** to be verified by this very document.

## Appendix: Task Breakdown Hints

Estimated effort: 10 tasks, approximately 8 hours. This PRD should produce approximately 10 to 15 tasks when parsed via task-master (using Gemini as the main model — the very test we are running).
