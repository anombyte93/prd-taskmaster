# Dogfood Run: atlas-shade Phase 5 PRD

**Date:** 2026-04-13
**Target project:** [atlas-shade](https://github.com/anombyte93/atlas-shade) — Shade Pentest OS (Raspberry Pi 5, 6 MCP servers, 69 tools, 308 passing tests)
**Goal fed in:** Phase 5 Integration — n8n pipelines, local Ollama inference, FastAPI+HTMX dashboard hardening, HackTheBox proving ground
**Session:** `shade-prd-dogfood-1` (tmux, retired mid-handoff)
**Related:** [ship-readiness-discovery.md](./ship-readiness-discovery.md) (self-dogfood findings), [provider-comparison.md](./provider-comparison.md) (Claude vs Gemini on self-PRD)

This is the missing debrief for the atlas-shade dogfood run. It was captured retrospectively from three sources because no debrief was authored at the time — see the "meta-finding" at the bottom for why.

---

## 1. What went in

The user invoked `/prd-taskmaster-v2` from `~/Hermes/current-projects/atlas-shade/` with a Phase 5 goal: integrate four layers (n8n, local AI, dashboard status UI, HTB proving ground) onto a working Pentest OS substrate without regressing 308 existing tests.

Constraint list the skill had to respect:
- Existing 308 tests must stay green
- Zero external data egress for sensitive operations (local Ollama only)
- FastAPI + HTMX — no React, no JS framework
- Pantone-mapped colors (Atlas AI brand palette)
- Pi-hosted Docker only (no SaaS n8n)

The goal was non-trivial: four parallel feature tracks on a shipped product, hard constraints, existing test suite that cannot regress.

## 2. What v4 produced

Artifacts live in `atlas-shade/.taskmaster/` (still untracked there as of 2026-04-14):

| Artifact | Content |
|---|---|
| `docs/prd.md` | 401-line PRD, v1.0, dated 2026-04-13, sentinel-tagged (`dogfood-sentinel-0f136ba0-9da1-4fe8-abad-800b9fef6a6f`) |
| `tasks/tasks.json` | 12 tasks, 86KB, dependency-graphed |
| `reports/task-complexity-report.json` | Threshold 5, avg 4.58, spread from 2–8 |

### PRD shape
- Executive summary, user impact, business impact, success metrics — all REQ-mapped
- **32 requirements** (REQ-001 to REQ-032), P0/P1 prioritised
- **North-star alignment table** mapping every deliverable to "always on / always visible / always safe"
- **Hard non-goals** listed (no React, no cloud AI, no refactor of Phases 1–4, 10 tools on HTB sufficient)
- Passes its own `validate-prd` rules — no `{{mustache}}` placeholders, no TBD, no TODO

### Task decomposition
12 tasks with explicit dependency chains. The graph is functionally correct:

- **Task 1** (n8n Docker setup) gates tasks 2, 3, 4 (the three workflow implementations)
- **Task 5** (Ollama install on Pi) gates Task 6 (shade-analyst MCP extensions)
- **Task 7** (dashboard API endpoints) gates Task 8 (UI components) — API before UI is the correct order
- **Task 9** (HTB VPN routing) gates Task 10 (proving-ground execution)
- **Task 11** (integration smoke test) depends on both workflow + AI tracks (4 and 6)
- **Task 12** (regression gate) depends on all prior — the textbook release-task pattern

No dependency inversion errors. No orphan tasks. Every P0 requirement maps to at least one task.

### Complexity analysis
Threshold: 5. Distribution: average 4.58, two tasks above threshold.

| Task | Title | Score |
|---|---|---|
| 12 | Phase 5 Integration Testing and Regression Gate | **8** |
| 10 | HTB Proving Ground Execution | **7** |
| 7  | Dashboard API Endpoint Extensions | 6 |

Both high-complexity tasks are accurate calls: #12 is end-to-end regression across four feature tracks, #10 is live exploitation with evidence capture. A tool that scored everything at 5 (v3's degenerate behavior) would be useless here; the spread 2–8 is evidence v4's complexity analysis discriminates meaningfully.

## 3. What worked

- **Zero-config discovery:** the skill ran against atlas-shade with no setup prompts. Preflight detected the existing `.taskmaster/` directory and routed accordingly.
- **Domain-agnostic generation:** the output is a pentest-OS PRD with pentest-OS vocabulary (kill-switch, tunnel tiers, WireGuard namespaces, Mullvad exit IPs). v3's comprehensive template would have imposed a web/API shape on this goal.
- **Requirement-to-task traceability:** 32 REQs → 12 tasks with explicit mapping. Traceable both ways.
- **Non-goal enforcement:** the PRD calls out seven explicit non-goals, preventing scope creep during execution. Task decomposition respects them (no React task, no cloud AI task).
- **Validation pass:** PRD cleared the 13 automated quality checks with no `{{mustache}}`, TBD, or TODO patterns — proving the generated content is not template-leaked.
- **Sensible prioritisation:** P0/P1 split aligned with what a solo operator would actually ship first (n8n → Ollama → UI → HTB — HTB is explicitly lowest-priority and can ship in a separate PR).

## 4. What broke

### The HANDOFF gate failure (captured in `/tmp/fleet-delta/t{0,1}/shade-prd-dogfood-1`, Apr 13 17:53)

The session completed PRD generation and task parsing, then **retired at the HANDOFF prompt without choosing an execution mode.** The fleet-delta snapshot captured the final visible state:

- A `PreToolUse:AskUserQuestion` hook (automated-session mode) blocked the interactive A/B/C/D mode picker from firing
- The Claude session fell back to surfacing the choice as prose text ("Reply with A, B, or C...")
- The user did not reply (automated/unattended run)
- Claude Code exited; the tmux pane fell back to a raw zsh prompt (`Archie:atlas-shade dev ...`)
- Another fleet session (`codex-web-delivery`) later harvested the tmux snapshot before the pane was reclaimed — that harvest is the only reason this evidence exists

The session emitted its own `[AI]` insight before dying:

> *"Hook conflict surfaced: a `PreToolUse:AskUserQuestion` hook is blocking the interactive gate because it's configured for automated/unattended sessions. This is correct behavior for fleet/orchestrator runs — but it means the user-agency handoff gate can't fire programmatically. The right fix is either a session-level hook toggle or the orchestrator providing the mode selection as part of the directive."*

### Fix landed: `a0a3c28`

This finding drove commit `a0a3c28` in the skill repo: `fix(handoff): enforce EnterPlanMode + AskUserQuestion dual-call, gate Atlas-Auto as coming-soon`. `phases/HANDOFF.md` now:

- Calls `EnterPlanMode` *and* `AskUserQuestion` (dual-tool-call) — either one alone left a gap
- Has an explicit hook-blocked graceful-degradation fallback: prose option table preserving the same semantics, surfaced as an `[AI]` insight block so the parent orchestrator can detect the fallback

The Shade dogfood is the engagement that proved the original gate was single-point-of-failure. Without this run, the bug would have shipped in v4.0.

## 5. Comparison to the other Apr 13 dogfoods

| Dogfood | Target | Outcome | Artifacts |
|---|---|---|---|
| **Self-dogfood (sonnet)** | prd-taskmaster v4's own meta-PRD | Succeeded end-to-end, 20 tasks, grade EXCELLENT 56/57. Surfaced 20 ship-blockers in `ship-readiness-discovery.md` | Committed to this repo |
| **Self-dogfood (Gemini)** | Same meta-PRD, different provider | Succeeded end-to-end, 10 tasks, grade EXCELLENT 57/57, 113x fewer tokens. Captured in `provider-comparison.md` | Committed to this repo |
| **This run: atlas-shade** | External, pentest-OS domain | Succeeded through PRD + tasks + complexity. **Retired at HANDOFF** due to hook conflict. Drove commit `a0a3c28`. | Still untracked in atlas-shade; snapshot in `/tmp/fleet-delta/` |

The three together are a meaningful validation set: two self-dogfoods (testing the skill on content it was trained on) plus one external-domain run (testing generalisation). v4 passed all three on content generation; the Shade run is the one that uncovered an execution-mode bug that the self-dogfoods didn't surface because they weren't running under the fleet's automated-session hook configuration.

## 6. Meta-finding: the debrief asymmetry

**This debrief was authored on 2026-04-14, one day after the run, only because a later session noticed the absence.**

At the time of the run, no debrief was written. The self-dogfood got `ship-readiness-discovery.md` because it surfaced bugs — bugs prompt authorship. The Shade run largely succeeded on content generation and the bug it did find (hook conflict) was actionable enough that someone fixed it via `a0a3c28` without documenting the provenance. The artifacts (PRD, tasks.json, complexity report) sat untracked in atlas-shade; the tmux snapshot landed in volatile `/tmp/fleet-delta/` with a half-life measured in reboots.

**Failure leaves a trail. Success leaves only artifacts.** This asymmetry silently biases the repo's documentation toward "what went wrong" and away from "what worked on a real external target."

### Possible fix

A `script.py debrief --from-tasks` subcommand could auto-emit a scaffold from `tasks.json + complexity-report + validate-prd grade`, writing to `docs/v4-release/dogfood-<project>-<date>.md`. Closes the asymmetry by making success-case authorship a single deterministic command instead of a discretionary chore. Not implemented yet — flagged as a follow-up.

---

## Evidence anchors

- atlas-shade PRD: `~/Hermes/current-projects/atlas-shade/.taskmaster/docs/prd.md` (untracked)
- atlas-shade tasks: `~/Hermes/current-projects/atlas-shade/.taskmaster/tasks/tasks.json` (untracked)
- atlas-shade complexity: `~/Hermes/current-projects/atlas-shade/.taskmaster/reports/task-complexity-report.json` (untracked)
- Session snapshot: `/tmp/fleet-delta/t{0,1}/shade-prd-dogfood-1` (volatile — copy into this repo's commit history if durability matters)
- Session-context log: `~/Hermes/current-projects/atlas-shade/session-context/CLAUDE-activeContext.md` `[SYNC] 20:05 13/04/2026` entry
- Derivative fix in skill repo: commit `a0a3c28`
