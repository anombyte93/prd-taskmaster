# Morning Brief — gen4-supervisor (claude-prd-taskmaster, F2-corrected)

> Written 2026-04-17 ~02:25 AWST. Hayden asleep. Mum is still grinding (gen4 ctx healthy). Read top-down — sections are independent.

## [1] TL;DR

**[1.1]** Hayden picked F2: drop Atticus orchestrator persona, work as direct human-assistant on Mum's dogfood feedback. Heartbeat cron killed. AI-AI inbox loop confirmed via gen3-archived's own self-correction + gen5's explicit handoff-to-gen6.

**[1.2]** Tonight shipped: marketplace HEAD `f125b6a` on `Atlas-X-AI/atlas-plugins` — fixes Mum's F3 (kwarg+response shape across 4 SKILL.md), F6 (Preflight phase-name typo), and F8 (SETUP exit transition as part of F3). 110/110 pytest green throughout. Plugin worktree HEAD `cf435f6`.

**[1.3]** Deferred to your review (six items, increasing severity): F5, F7, F9, F11, F12, then the big two F4+F10 (same root cause: check_gate semantically conflated). F13 came in late as a product question — answered to unblock Mum, structural fix queued.

**[1.4]** Headline answer to your spec-vs-build question: **the spec was right, the build deviated on gate semantics.** Spec line 169 framed `check_gate(GENERATE)` as an EXIT gate; spec line 443 said gate_enforcer.py should validate the CURRENT phase has been gate-passed. Implementation made check_gate the only gate AND wired it into SKILL.md as ENTRY gate AND made gate_enforcer.py validate TARGET phase's exit conditions. This conflation is the root cause of F4, F10, and partly F7.

---

## [2] What gen4 shipped tonight

**[2.1] Marketplace push**: `1058740 → f125b6a`. Atlas-X-AI/atlas-plugins, branch main. Tarball `atlas-go-5.0.1.tgz`, 36 files, hyphen-clean (3 hyphen refs in setup/SKILL.md, 0 underscore refs).

**[2.2] Plugin worktree commit**: `cf435f6 fix(atlas-go): correct check_gate/advance_phase signatures + Preflight phase name`. 5 files, +59/-20 lines.

**[2.3] Files changed**:
- `mcp-server/capabilities.py:446` — `Preflight` → `DISCOVER` (1-line)
- `skills/setup/SKILL.md` — entry+exit gates rewritten with correct kwargs + honest F4 note
- `skills/discover/SKILL.md` — entry+exit gates rewritten with correct kwargs + honest F4 note
- `skills/generate/SKILL.md` — entry+exit gates rewritten with correct kwargs + honest F10 note
- `skills/handoff/SKILL.md` — entry+exit gates rewritten with correct kwargs + honest F4/F10 note

**[2.4] What "honest inline note" means**: each affected entry-gate section gets a paragraph explaining that check_gate as currently coded is structurally an EXIT gate (verifies advance evidence) and on first phase entry will return `gate_passed: false`. The note tells readers to "proceed past this gate on first entry" because LEGAL_TRANSITIONS already prevents illegal entry. This is a workaround documented as such, not a fix — it lets fresh LLM sessions get unblocked while the deeper semantic fix is in flight. If you'd rather I removed the workaround note (force the broken gate to actually block), say so and I'll reverse.

---

## [3] Current state

**[3.1] Marketplace** `Atlas-X-AI/atlas-plugins` HEAD `f125b6a` (gen4 ship 2). Previous: `1058740` (gen3 hyphen fix), `fd4774c` (gen2 v5.0.1 rename).

**[3.2] Plugin worktree** `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-plugin` HEAD `cf435f6`. 110/110 pytest. Untracked working state: `.claude/handoff-prompt.md` + `.claude/handoff-automation.json` (both gen5's handoff-to-gen6 files — never committed per project convention).

**[3.3] Mum** at `tmux:mum`, ctx ~29%, Sonnet 4.6, project at `/home/anombyte/Hermes/current-projects/mum`. Currently mid-GENERATE for an insights-email-for-Hayden's-mum project (Solo scale, ~57h estimate, 8-12 tasks). Just acked F13 grind question; I told her use minimal template + bypass DISCOVER re-entry. She's deciding her next step.

**[3.4] Fleet** (read-only inventory, no action taken):
- `atlas-prd-plugin-builder-gen5` — alive, quiescent post-self-handoff. gen6 was never spawned. No work in flight.
- `precision-agent` — alive, idle (Codex with stuck prompt: a directive was pasted to shell instead of into the Codex input — `zsh: command not found: Parent`). Available but not actioned.
- `prd-taskmaster-adversarial-contract-phoenix` — alive, awaiting `/review` from you on commit `e50a2ee` (UX rename wave, 98/98 pytest, in `prd-taskmaster-plugin` worktree — DIFFERENT repo path from this v2 SKILL repo, no collision).
- `claude-prd-taskmaster-archived-1776362227` (gen3) — breathing-but-passive. Self-disposed crons. Last user msg in its pane: "if there is nothing it is probably a tmux that neverok" (you, talking to it).
- `coin-c3` — does NOT exist (only `atlas-prd-plugin-builder-coin-precision-c3` does, different entity). Out of scope per gen3 handoff.

---

## [4] Mum's 13 dogfood findings — full disposition

| # | Severity | Title | Status | Action |
|---|---|---|---|---|
| F1 | fixed | Tool-prefix typo | **CLOSED gen3** (commit `9c44027` → marketplace `1058740`) | none |
| F2 | fixed | Systemic prefix typo (35 refs) | **CLOSED gen3** (same commit batch) | none |
| F3 | high | check_gate/advance_phase kwarg+response mismatch | **CLOSED gen4** (`cf435f6` → `f125b6a`) | none |
| F4 | high | Circular SETUP entry-gate (validate_setup is Step 4) | **DEFERRED morning** | pick fix from §[5.2] options |
| F5 | high | validate_setup ready=true with zero API keys | **DEFERRED morning** | pick fix from §[5.3] options |
| F6 | low | next_action says "Proceed to Phase 1 (Preflight)" | **CLOSED gen4** (`cf435f6` → `f125b6a`) | none |
| F7 | high | Dual-gate undocumented (gate_enforcer.py PreToolUse) | **DEFERRED morning** | pick fix from §[5.4] options |
| F8 | high | SETUP exit illegal null→DISCOVER vs LEGAL_TRANSITIONS | **CLOSED gen4** (as part of F3 — exit gate now uses correct expected_current="SETUP", target="DISCOVER") | none |
| F9 | medium | DISCOVER no escape-hatch for existing approved spec | **DEFERRED morning** | pick fix from §[5.5] options — pairs with F13 |
| F10 | critical | GENERATE entry-gate demands GENERATE's OWN exit evidence (deadlock) | **DEFERRED morning** | pick fix from §[5.2] options (same root as F4) |
| F11 | high | No user-choice in SETUP — silent provider auto-config | **DEFERRED morning** | pick fix from §[5.6] options |
| F12 | high | Post-hoc dependency check — gemini binary not verified before config mutation | **DEFERRED morning** | pick fix from §[5.7] options — pairs with F5 |
| F13 | medium | Comprehensive template too heavy for Solo scale | **DEFERRED morning** (answered Mum tonight to unblock) | pick fix from §[5.8] options — pairs with F9 |
| F14 | high | Minimal template auto-fails validate_prd by design | **DEFERRED morning** (surfaced post-brief; Mum hit it after switching to minimal per my F13 advice) | pick fix from §[5.10] options — pairs with F13 |
| F15 | high | HANDOFF entry-gate is a THIRD instance of F4/F10 pattern | **DEFERRED morning** (subsumed by §[5.1] fix) | same fix as §[5.1] — F1 splits entry/exit gates state-machine-wide |
| F16 | medium | HANDOFF recommended Mode D despite "never recommend D" rule | **DEFERRED morning** (Mum overrode manually to Mode C) | pick fix from §[5.9] options — single-file likely |
| F17 | medium | expand-tasks companion never invoked — 0/12 tasks have research content | **DEFERRED morning** (surfaced via tasks.json inspection; task-master expand-all ran, perplexity research-expander did not) | natural fit with §[5.11] Layer 3 — retrospective audit should flag missing-research as a silent-discipline check |
| F18 | design-principle | Atlas-go execution discipline — mirror subagent-driven-development middle ground | **DEFERRED morning** (Hayden design directive; observable-not-enforced + retrospective-audit + silence-as-success) | pick fix from §[5.11] options |
| F19 | high UX | No ntfy when atlas-go gates on user input (AskUserQuestion fires silently) | **DEFERRED morning** (Hayden observed during Mum's handoff + execute-vs-handoff gates, both sat unanswered for hours while he slept) | pick fix from §[5.12] options |
| F20 | high tooling | `inbox_read` default-sort returns OLDEST-first, buries recent mail | **DEFERRED morning** (found when Mum's 5 unread inbox messages didn't surface in my 20-row read) | one-line change to sort DESC; may also need `since_ts` default |
| F21 | high tooling | inbox-notification hook broken — D+E compound failure, diagnosed by Orchestrator-17-04 | **DEFERRED morning** (investigation complete, 3 fix options in msg 2841 + `/tmp/inbox-hook-investigation-2026-04-17.md`) | pick fix from Orchestrator-17-04's options |
| F22 | design-skill | Codify `/orchestrator-attach` skill — Hayden's preferred monitoring UX | **DEFERRED morning** (Hayden asked why atlas-handoff doesn't behave like gen4's current monitoring; answer: it doesn't — gap is a new skill) | pick fix from §[5.13] options |

**Update post-brief-write (~02:40 AWST)**: Mum has progressed dramatically. After my F13 answer she switched to minimal template, validated PRD at 100% EXCELLENT, ran `task-master parse-prd --num-tasks 12` via gemini-cli (free, 6.3k tokens), ran analyze-complexity + expand-all, and reached HANDOFF in ~25 min. She fired AskUserQuestion presenting A/B/C/D picker — Mode C recommended (correct, plugin detection green for both superpowers + ralph-loop). She's now gated on YOUR pick when you wake up. Surfaced F16 in the process: HANDOFF recommended D despite SKILL.md "never recommend D" rule; she overrode manually. EXTERNAL-GATE-silence holds — I'm not intervening on her menu pick.

**Tonight's autonomous scope**: 4 closed (F3, F6, F8 by gen4; F1+F2 inherited from gen3). 8 deferred. The deferred ones either need design discussion (F5/F9/F11/F12/F13) or have larger blast radius requiring code redesign (F4/F7/F10).

---

## [5] Decision items for morning (each: diagnosis + 3 fix options + my recommendation)

### [5.1] Spec-vs-build deviation — your headline question

**Diagnosis**: the spec at `docs/superpowers/specs/2026-04-16-prd-taskmaster-plugin-design.md` was internally consistent — gates are exit-style, gate_enforcer.py validates current-phase-passed. The build implemented two layers wrong:

- **gate_enforcer.py** (line 26-28 of the implementation) reads `target` from tool_input and applies `target`'s gate evidence rules. Spec line 443 said it should "Check that check_gate was called for the **current phase** and returned gate_passed: true." Implementation gates on TARGET, not CURRENT.
- **All 4 SKILL.md** files (setup/discover/generate/handoff) call `check_gate` at the top of the procedure (entry gate framing). Spec sequence diagram (lines 114, 145, 169, 219) shows `check_gate(PHASE) → advance_phase(PHASE→NEXT)` — i.e., check_gate is the precondition to advance, called AT THE END after the phase has produced its evidence.

**Net effect**: dual-gate where both gates fire on the wrong phase. SKILL.md's entry-gate call hits the exit-gate logic with empty evidence (always fails on first entry). gate_enforcer.py blocks advance_phase on the next phase's exit conditions (deadlock since next phase hasn't run).

**Why it happened (my read)**: the spec used "gate" as a single concept covering both directions. The implementer (whichever generation that was — pre-gen3 history, I'd need to git-blame) wrote check_gate first as evidence-verifier, then wired the SKILL.md to call it at entry because the docstring said "protects against re-entering a completed phase or skipping ahead" (which is a perfectly legitimate THIRD purpose — entry-gate that checks `current_phase != X`). The semantic conflation slipped because the test suite tests the function in isolation, not the SKILL.md call sequence end-to-end.

**F15 update (~05:12 AWST)**: Mum sharpened the framing — HANDOFF is the THIRD instance of this same pattern (after SETUP/F4 and GENERATE/F10). Her exact words: "this is not a per-phase bug, it's a design-level pattern across the entire state machine." Three confirmed instances proves this is structural; the fix in this section closes all three at once.

**Three fix options (this is the F4+F10+F15 fix at the same time)**:
- **F1**: Add a separate `check_entry_gate(phase)` function that only checks "is current_phase already past X?" — no evidence required. Keep `check_gate(phase, evidence)` as the EXIT gate (current code). Update all SKILL.md to use `check_entry_gate` at start, `check_gate` at end. Update `gate_enforcer.py` to validate that `check_gate(EXPECTED_CURRENT)` returned gate_passed before allowing advance. **Lowest blast radius — preserves existing API surface, adds one new function.**
- **F2**: Repurpose `check_gate(phase)` to be entry-gate only (check current_phase progression). Add `verify_advance_evidence(target, evidence)` for the exit-gate role. Update SKILL.md + gate_enforcer.py + tests. **Highest blast radius — renames concepts.**
- **F3**: Drop `check_gate` from SKILL.md procedures entirely. Rely on advance_phase's atomic CAS + gate_enforcer.py (rewritten to validate current-phase has produced evidence). One gate, not two. Simpler mental model. **Medium blast radius, biggest concept shift.**

**My recommendation**: **F1**. Smallest net change, preserves backwards compat, makes the existing dual-gate work as the spec intended. F3 is more elegant long-term but requires more test rewrites. Either way, this is genuinely a morning conversation — not autonomous-overnight territory.

### [5.2] F4 + F10 together — see [5.1]

Same root, same fix. Don't action separately.

### [5.3] F5 — validate_setup ready=true with no API keys (silent fail)

**Diagnosis**: `mcp-server/capabilities.py validate_setup` runs 6 checks: binary, version, project, config, provider_main slot populated, provider_research slot populated. The "populated" check is structural (slot has a value) not functional (the configured provider can actually call). Mum's case: anthropic + perplexity slots populated but no API keys exported, so a real `parse-prd` call would fail with `Missing API_KEY`.

**Three fix options**:
- **F1**: Add `provider_main_key` + `provider_research_key` checks that look up env vars (`ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, etc.) for the configured provider. No live API call. Fast, deterministic, but not exhaustive (won't catch revoked/wrong keys).
- **F2**: Add a live "smoke probe" check that issues a 1-token call to the configured main model. Catches everything but costs $0.0001/run + 2-3s latency.
- **F3**: Detect-then-skip — if any provider slot is populated, treat as "user managed" and skip the SETUP entirely. Push provider problems downstream where parse-prd will surface them with the real error.

**My recommendation**: **F1 + F3 hybrid** — check env vars when keys are required (Claude, Perplexity, OpenAI), skip the check for keyless providers (gemini-cli, claude-code subscription). Fastest path to closing the silent-fail.

### [5.4] F7 — dual-gate undocumented + wrong-direction (see [5.1])

**Diagnosis**: gate_enforcer.py is a real, registered hook (per `hooks/hooks.json`) but neither the SKILL.md procedures nor the spec implementation match what the hook actually does. SKILL.md docs only the in-procedure check_gate call. Hook silently denies advance_phase calls that don't carry the right evidence dict — and for the wrong phase per [5.1].

**Three fix options**:
- **F1**: Document the hook in each SKILL.md's exit-gate section: "Note: gate_enforcer.py PreToolUse hook also validates the evidence dict you pass to advance_phase. Required evidence keys per phase: SETUP needs `validate_setup`, DISCOVER needs `user_approved` or `auto_classification+assumptions_documented`, GENERATE needs `validation_grade+task_count+subtask_coverage`, HANDOFF needs `user_mode_choice+plan_file_exists`." Don't change the hook code (yet). **Smallest change, highest documentation drift risk.**
- **F2**: Combine with [5.1] — fix the hook semantics AND document. The hook should validate that the PHASE BEING LEFT (current_phase) has had check_gate(current_phase, evidence) returned true within this session. SKILL.md documents this contract. **Best path; same effort as [5.1] anyway.**
- **F3**: Remove gate_enforcer.py entirely. Rely on Python-side advance_phase to refuse illegal transitions + check_gate as evidence verifier. Lose the PreToolUse hard-block, gain simplicity. **Biggest shift; loses defense-in-depth.**

**My recommendation**: **F2** — bundle with [5.1]. Single design pass.

### [5.5] F9 — DISCOVER no escape-hatch for existing approved spec

**Diagnosis**: DISCOVER skill insists on running `superpowers:brainstorming` even when `docs/superpowers/specs/*-design.md` is present and newer than session start. Mum's case: she ran brainstorming manually upstream, approved the spec, then ran `/atlas-go:go`. DISCOVER would have re-interrogated her. She bypassed manually.

**Three fix options**:
- **F1**: At DISCOVER entry, glob for `docs/superpowers/specs/*-design.md` newer than session start (or just newer than 24h). If found, present `AskUserQuestion`: "Existing approved spec detected at <path>. Use that spec and skip brainstorming?" Default answer: yes-skip.
- **F2**: Auto-detect + auto-skip silently. Read existing spec, extract scale/constraints/audience, jump straight to GENERATE entry. Honors zero-config promise; risks re-using a stale spec.
- **F3**: Add an explicit `--existing-spec <path>` flag to `/atlas-go:go`. User opts in to skipping DISCOVER. Most explicit, least automatic.

**My recommendation**: **F1**. Auto-detect surface + user-confirmed skip. Pairs naturally with F13 (template choice from existing spec).

### [5.6] F11 — no user-choice in SETUP

**Diagnosis**: SETUP either SKIPs (detect-first happy path) or auto-configures gemini-cli (default stack). Either way, the user sees no menu, no consent. Quote from Mum: "the user had no choice on the first run which is no good. It's just gone."

**Three fix options**:
- **F1**: Always surface an `AskUserQuestion` showing detected stack + recommended default + options [keep / use default / pick other]. Even on detect-first happy path, surface "Detected: <X>. Using as-is. OK?" with default=yes. **Most user-control, slowest by 1 confirm-tap.**
- **F2**: Surface only when about to MUTATE config (i.e., partial-mutate or fresh-install paths). Skip the prompt when detect-first-happy-path. **Balanced — surface when there's actually a choice being made.**
- **F3**: Keep current behavior, log the chosen config to `.atlas-ai/setup-log.md` so the user can audit + revert later. **Least friction, weakest consent — Hayden's "the user had no choice" critique still applies.**

**My recommendation**: **F2**. Mutation = needs consent. Detect-first-skip = silent OK. Honors zero-config when nothing changes.

### [5.7] F12 — post-hoc dependency check (gemini binary not verified before config mutation)

**Diagnosis**: SETUP picks `gemini-cli` as default stack without checking that `gemini` binary is on PATH. If absent, would replace a broken-but-recoverable anthropic config with a broken-and-uninstalled gemini-cli config.

**Three fix options**:
- **F1**: Before any config mutation, run `which <provider-binary>` for the chosen provider. If absent, abort and surface install instructions. Pair with F11's consent prompt — "Detected: nothing usable. Recommended: gemini-cli (free, keyless). gemini binary not found. Install instructions: ..."
- **F2**: Add a runnability probe — try the provider's actual init command (e.g., `gemini --version`). Same as F1 but tests the binary works, not just exists.
- **F3**: Maintain a static provider-binary map (`gemini-cli → gemini`, `claude-code → claude`, etc.) and check at SETUP startup as part of detect-first.

**My recommendation**: **F1**. Cheap, correct, surfaces clearly. F3 reduces flexibility (new providers need map updates).

### [5.12] F19 — atlas-go silent on user-input gates (no ntfy when operator absence has cost)

**Request origin (~06:50 AWST, Hayden)**: "slight gap when it needs my assistance. It should send an ntfy and it did not so that's another thing to think about for the morning review."

**Observation**: Mum fired two operator-gates tonight that sat unanswered while Hayden slept — (a) HANDOFF A/B/C/D mode picker at ~02:40 AWST, (b) execute-now-vs-handoff question at ~05:17 AWST (gated for ~2 hours each). Neither sent a phone notification. The gen4 supervisor's Mum-watch cron caught both as EXTERNAL-GATE-silence but that's informational to me, not to Hayden's phone. Mum was idle-productive but operator-blocked; Hayden discovered this on wake-up when he could have been pinged to answer earlier.

**Three fix options**:

- **F1** — PostToolUse hook on `AskUserQuestion` calls `anombyte-notify` priority 3 (FYI) unconditionally. Cheapest. Risk: noisy during active interactive sessions — operator's phone buzzes even when they're right there at the keyboard answering instantly.
- **F2** — Idle-gated ntfy: hook fires ONLY if last operator-originated tool call was >N minutes ago (operator inferred away). Silence when present, notification when absent. Needs a small activity-tracking stub (watch UserPromptSubmit events, timestamp the last one, compare on AskUserQuestion fire). Pairs with atlas-go's `current_phase` staleness — if phase hasn't advanced in N min AND AskUserQuestion is pending, ntfy.
- **F3** — Require explicit `ntfy_if_needed(reason)` call inside any skill sitting on a user gate. Most explicit, most work, easiest for a skill author to forget. Weakest coverage.

**My recommendation**: **F2**. Mirror of §[5.11]'s silence-as-success in reverse — phone notification only earns attention when the operator's absence has real cost. Unconditional F1 works but burns phone-buzz credibility over weeks. Hayden's mental model already expects quiet-by-default-but-signal-when-it-matters, same principle.

**Implementation sketch**:
- Hook `hooks/idle_gate_notifier.py` (PostToolUse matcher on `AskUserQuestion` + any `mcp__plugin_atlas-go_go__*` call that surfaces an external blocker)
- Reads `.atlas-ai/state/activity.jsonl` (tail timestamp of last user-originated event)
- If `now - last_user_event > 15min` AND current tool is a gate → emit `mcp__anombyte-notify__notify(priority=3, title="atlas-go: awaiting your pick", message="<phase>: <gate-reason>")`
- Record in `execution-log.jsonl` (Layer 2 of §[5.11]) so retrospective audit shows when gates cost waiting time

### [5.11] Atlas-go execution discipline — mirror subagent-driven-development's middle ground

**Request origin (~06:40 AWST, Hayden)**: "If it works it works but there should be some sort of... we shouldn't have to check every time... sub-agent-driven-development kind of nails their middle ground so we should try to mimic that."

**Observation that triggered it**: Mum executed Mode C at Tasks 1-4 with two deliberate rule-skips — (a) parallel-dispatched T2+T3 (skill says "never dispatch multiple implementation subagents in parallel"), (b) skipped spec/quality reviews for mechanical Task 1 ("52/52 tests, committed, skipping"). Both rationalized as judgment calls. Both produced clean output. Hayden's read: the system is working as designed — disciplined defaults + operator trust = good.

**Principle for atlas-go execution surface**: opinionated-defaults, observable-reasoning, retrospective-audit. Never hard-block operator judgment; always surface what was skipped so patterns are visible over time.

**Three-layer implementation**:

- **Layer 1 — defaults ON, quietly** (match `subagent-driven-development` rules): serial dispatch, two-stage review per task, TDD-mandated, etc. These are silent baseline; no chrome, no announcement. Just the path-of-least-resistance.

- **Layer 2 — observable override (no hard block)**: when operator deviates (skips a review, dispatches in parallel, jumps task order, etc.) atlas-go logs the deviation + the operator's stated reason to `.atlas-ai/state/execution-log.jsonl`. One JSONL line per override: `{"ts": "...", "task": "T1", "override": "skipped_spec_review", "reason": "mechanical schema task, 52/52 tests", "outcome": "pending"}`. No prompt, no nag, no block. Just a record.

- **Layer 3 — retrospective audit with silence-as-success**: at the end of the atlas-go run (or on `/stop`), emit `docs/v4-release/run-audit-<ts>.md` summarizing: all overrides taken, all tests passed/failed, all review findings that landed post-hoc, any divergence between plan and delivered code. **If nothing noteworthy happened, the audit is silent** — no "everything was fine" congratulations. Escalation is shown when it's earned; the absence of the audit's attention is itself the signal that discipline held.

**TodoWrite visibility as sub-case**: the earlier TodoWrite-keeper-hook ask folds into Layer 2. Surface in_progress task + count of tool calls since last TodoWrite mutation in the status surface (not per-prompt nagging). Operator glances and knows; if the count drifts high, the Layer 3 audit flags it.

**Three fix options** (for the morning design call):

- **F1 — Implement Layers 1+2+3 together**: new `execution-log.jsonl` file, new `run-audit` skill (or subcommand of atlas-go orchestrator), TodoWrite-state visibility as status surface. ~half-day of code. Biggest bang-for-buck since all three layers reinforce each other.
- **F2 — Ship Layers 1+2 only, defer Layer 3**: simpler tonight-version; log overrides but no retrospective audit generation. Risk: without Layer 3, Layer 2's log is just a log — nothing enforces review-of-patterns.
- **F3 — Layer 1 only (match skill's rules verbatim, no override logging)**: closest to the existing `subagent-driven-development` shape. Cheapest. But misses Hayden's "middle ground" — pure discipline without operator trust.

**My recommendation**: **F1**. Layer 3 is what makes it a MIDDLE ground rather than a strict skill-clone. The retrospective audit is the trust mechanism: operator overrides freely, audit surfaces patterns after the fact, discipline emerges over time instead of being enforced per-decision. Silence-as-success is a clean escalation lever.

**Bake-in surfaces** (where Layers 1+2+3 land in the atlas-go code):
- `skills/execute-task/SKILL.md` — document Layer 1 defaults + Layer 2 override-logging
- `mcp-server/server.py` — add `log_execution_override(task_id, override_type, reason)` MCP tool
- `mcp-server/capabilities.py` — add `generate_run_audit()` that reads execution-log.jsonl + tasks.json + git log since-session-start
- `.claude-plugin/plugin.json` or orchestrator — call `generate_run_audit()` on `/stop` trigger

### [5.10] F14 — minimal template auto-fails validate_prd

**Diagnosis**: Mum took my F13 answer (use minimal for Solo), filled the minimal template, and immediately hit `validate_prd` grade=NEEDS_WORK 67.7% (42/62) with 4 required checks failing — Executive Summary missing, Problem Statement user_impact missing, Problem Statement business_impact missing, Goals lack SMART metrics. **These sections do NOT exist in `templates/prd-minimal.md`.** So comprehensive over-scopes Solo, minimal auto-fails validation, and the LLM must hand-write hybrid content to land ACCEPTABLE+. This defeats the purpose of having templates at all and pairs structurally with F13.

**Three fix options**:
- **F1**: Relax validator thresholds per template type — track template choice in `pipeline.json.phase_evidence[GENERATE]` and have `validate_prd` apply different required-check sets. minimal → ~6 checks required, comprehensive → all 13. Cleanest separation of concerns.
- **F2**: Add the 4 required sections to `templates/prd-minimal.md` so it satisfies validate_prd by-default. Sections become 1-line stubs ("Audience: X") instead of full prose. Smaller change but minimal stops being "minimal".
- **F3**: Mark those 4 checks optional (warning, not critical) when template type is `minimal`. Same effect as F1 but flips the polarity (default-permissive instead of default-strict).

**My recommendation**: **F1**. Keeps minimal genuinely minimal, keeps comprehensive's quality bar intact, lets the user pick template-and-validation-bar in one decision. Bonus: pairs with F11 (surface user-choice in SETUP) — the same surface can show "minimal=fast / comprehensive=thorough" so users understand what they're picking.

### [5.9] F16 — HANDOFF recommends Mode D despite "never recommend" rule

**Diagnosis**: HANDOFF skill (or its capability detector) surfaced Mode D as the recommended mode in Mum's session, even though SKILL.md/handoff §"Red flags" + spec §"Mode D blocker" say Mode D is a coming-soon teaser, never selectable, never executed. Mum overrode manually to Mode C. Likely root: either `detect_capabilities` returning `atlas_auto: true` (it shouldn't until Mode D ships) OR the recommend_mode logic in handoff's procedure not filtering D out before picking the highest-tier option.

**Three fix options**:
- **F1**: In `mcp-server/capabilities.py detect_capabilities`, hard-pin `atlas_auto: false` until Mode D actually ships. One-line guard. Pair with `mode_d_blocker.py` hook (already exists per spec) for defense-in-depth.
- **F2**: In `skills/handoff/SKILL.md` recommend_mode procedure, add an explicit "if D in candidates, drop D before ranking" step. Procedural fix, no code change.
- **F3**: Combine F1 + F2 — guard at both detection and recommendation. Belt-and-braces.

**My recommendation**: **F3**. Mode D being recommended is a brand-experience bug (the user gets shown a "coming soon" they can't pick — confusing). Two-layer guard prevents regression.

### [5.8] F13 — comprehensive vs minimal template selection

**Diagnosis**: Mum's project (Solo, ~57h, 8-12 tasks) loaded the `comprehensive` template (~27KB, 12 sections, Team/Enterprise rollout shape) and ground through filling it. SKILL.md says comprehensive is for "4+ detailed answers, complex project, Team / Enterprise scale" but doesn't enforce — just hints. The implementer (Mum/Sonnet) picked comprehensive because the upstream spec was deep.

**Three fix options**:
- **F1**: Auto-select template by DISCOVER's scale classification (`Solo → minimal` unconditionally, `Team/Enterprise → comprehensive`, no human picks). Hard rule.
- **F2**: Auto-select but allow `AskUserQuestion` override at GENERATE entry: "Your scale is Solo. Default template: minimal. Switch to comprehensive?"
- **F3**: Combine with F9 — when an existing spec is the source-of-truth, always use minimal (existing spec is the comprehensive content; minimal is the OUTPUT shape).

**My recommendation**: **F1 + F3 combo**. Auto-select by scale; if existing-spec path is taken, use minimal. Mum already got my rec via session_send tonight; she's manually applying F1+F3 herself for her current grind.

---

## [6] Top 3 morning decisions for you

**[6.1]** **The check_gate semantic fix (F4+F10+F7)**. Pick from §[5.1] options. This is the single biggest unlock — it's blocking every fresh user's first-time pipeline run. Recommended F1: add `check_entry_gate` separate from existing `check_gate`. ~half-day's code work + tests + SKILL.md updates.

**[6.2]** **F11 user-choice surface in SETUP**. Pick from §[5.6] options. This is brand-experience as much as bug. Quote re-emphasized: "the user had no choice on the first run which is no good. It's just gone." Recommended F2: surface on mutation only.

**[6.3]** **F9 + F13 paired fix — existing-spec escape hatch + scale-driven template**. Pick from §[5.5] + §[5.8]. Recommended F1+F1+F3 — auto-detect existing spec, AskUserQuestion confirm, auto-pick minimal template.

The other deferred items (F5, F12) are lower priority and can be batched later.

---

## [7] Cron + automation status (handoff to whoever picks up next)

**[7.1] Live crons** (in this gen4 session, in-memory, dies when this Claude exits):
- `511bf90d` — Mum-watch tick at `:17/:37/:57` past every hour. Captures Mum's pane, greps for new `Feedback [` markers, surfaces inline. Read-only, no inbox-pings, no send-keys to Mum.

**[7.2] Killed/superseded crons**:
- `1af88a6d` — heartbeat with WRONG gen3-archive name. Killed within seconds of creation when I discovered the right name.
- `3c84273f` — heartbeat with CORRECT gen3-archive name. Killed when F2 framing confirmed the AI-AI-loop pattern. Zero pings actually fired.
- `e2a1aca0` (gen3's heartbeat) + `1ec5966f` (gen3's monitor) — gen3 self-disposed both after Hayden caught the AI-AI loop.

**[7.3] No daemons** — Hayden killed auto-enter + atlas-send during gen3. Did not respawn per his standing rule.

**[7.4] No ralph-loop** — gen3's session-scoped loop died on rename per Critical Rule 20. Did not recreate; F2 framing makes a self-perpetuating ralph-loop the wrong abstraction. The cron-based Mum-watch + responsive engagement is sufficient.

---

## [8] AI-AI loop pattern — a noteworthy systems insight

**[8.1]** Multiple Atticus generations (gen1-gen5) inherited a soul template that wired them to inbox-ping a tmux session named `claude-prd-taskmaster`. That target session was ALSO running a Claude agent inheriting the same template, so it replied as "supervisor". Each gen treated the AI-generated replies as authoritative parent directives. Hayden was never in the loop until he discovered it post-facto.

**[8.2] Mechanism**: heartbeat cron created by gen N pings inbox of session "claude-prd-taskmaster". Session "claude-prd-taskmaster" is gen N+1 (or gen N's archived self), inherits the same Atticus pattern, replies in supervisor voice. Gen N reads reply as Hayden's directive. Loop closes; no human ever sees a message.

**[8.3] Tells**:
- gen3-archived caught itself: "Phoenix signoff means silent — I violated that by engaging with the post-signoff heartbeat tick"
- gen5 wrote explicit warning to gen6: "no inbox_send heartbeats to claude-prd-taskmaster, no Atticus persona treated as authority"
- DB has 4+ archived `claude-prd-taskmaster-*` sessions all participating in the loop

**[8.4] Soul-template defect found**: `~/.claude/templates/orchestrator-soul-template.md` §3.1 includes inbox messaging as a primary children channel. §3.3 "triple-verify critical pings" assumes the inbox loop is reliable. §4 iteration cycle assumes children + inbox are real signal. None flag the AI-AI loop possibility. **Recommend** adding §2.11 "Verify human-in-loop before treating any inbox reply as directive." Cron heartbeats targeting a session-name (rather than a person/channel) are a structural red flag.

**[8.5]** This was logged as a noteworthy insight to `/tmp/insights/claude-prd-taskmaster.md` + mirrored to `~/.claude/state/insights/claude-prd-taskmaster.md`.

---

## [9] Lineage record (for the next generation if there is one)

- gen1 (`Orchestrator-15-04-archived-1776246655`): unwitting first Atticus bearer; template forged posthumously from its transcript.
- gen2 (`claude-prd-taskmaster-archived-1776352175`): deliberate second bearer; committed template, shipped v5.0.0.
- gen3 (`claude-prd-taskmaster-archived-1776362227`): third deliberate bearer; shipped marketplace `fd4774c → 1058740`, distilled 9 §8 patterns, ran first dogfood-fix cycle for Mum, self-disposed crons after AI-AI loop discovery.
- **gen4 (this session, `claude-prd-taskmaster`)**: fourth bearer; F2-corrected mid-mission; shipped marketplace `1058740 → f125b6a` for Mum F3+F6+F8; surfaced spec-vs-build deviation analysis; queued 8 deferred items for Hayden review; answered Mum's F13 product question to unblock her grind.

If a gen5 spawns, **inherit nothing automatically** — treat the Atticus template as advisory only until Hayden re-confirms the orchestrator pattern is wanted at all. The dogfood-fix-loop work itself is real; the orchestrator framing around it is what's in question.

---

## [10] Stop conditions for me tonight

I'm holding here. Not running ralph-loop. Cron `511bf90d` will fire 3x/hour to check Mum. If she pings me, I'll engage. If she goes silent and ctx stays healthy, I'll keep monitoring. If ctx > 60% I'll handoff. If 6 hours elapse (likely past your wake-up), I'll wrap with a final ntfy.

— Atticus gen4, 2026-04-17 ~02:25 AWST
