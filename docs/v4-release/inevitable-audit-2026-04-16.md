# Inevitability Audit: prd-taskmaster-v2

**Date:** 2026-04-16
**Target:** SKILL.md + phases/*.md + script.py + mcp_server/ + install.sh
**Method:** Dual-agent adversarial audit (inevitability-auditor + mechanism-discovery)
**Guarantees audited:** 12

---

## Section 1: Declared Guarantees

| ID | Guarantee | Source |
|---|---|---|
| G1 | Zero setup questions -- preflight detects everything | SKILL.md:141 |
| G2 | Phase files Read explicitly, never auto-loaded | SKILL.md:34 |
| G3 | Every script.py subcommand outputs JSON on stdout | CLAUDE.md, script.py docstring |
| G4 | Validation catches ALL placeholders | SKILL.md:148, script.py:643 |
| G5 | HANDOFF recommends ONE mode | SKILL.md:145, HANDOFF.md:41 |
| G6 | Expand --all is serial (no data loss) | GENERATE.md:122-126 |
| G7 | claude-code is default provider (zero API key) | SKILL.md:54 |
| G8 | Dual-tool-call gate (EnterPlanMode + AskUserQuestion) | HANDOFF.md:161 |
| G9 | Codification split (AI judgment vs determinism) | CLAUDE.md, SKILL.md |
| G10 | Domain-agnostic (any goal) | SKILL.md:145 |
| G11 | TaskMaster native tools preferred (MCP first) | SKILL.md:29-36 |
| G12 | Idempotent append-workflow (HTML sentinels) | HANDOFF.md:106-143 |

---

## Section 2: Failure-Mode Table (33 modes found)

| ID | G | Failure Mode | Prevention | Tier | Evidence |
|---|---|---|---|---|---|
| F1 | G1 | SETUP.md Step 3 has explicit question branches when provider is empty or unsupported. Contradicts "zero questions." | Convention only (prose conflict between SKILL.md and SETUP.md) | Strongly-likely | SETUP.md:58-62 vs SKILL.md:141 |
| F2 | G1 | Probe test failure (bad API key, network) forces AI to ask user for troubleshooting. No auto-fix path. | Nothing | **Inevitable** | SETUP.md:118-123 |
| F3 | G3 | MCP lib.py coerces empty/truncated subprocess stdout to `{}` (no `ok` field), violating the JSON contract. | Partial | Likely | lib.py:90, script.py:47-49 |
| F4 | G4 | Placeholder regex misses `<TBD>`, `XXX`, `CHANGEME`, `___`, `[TODO: extended text]`. Only catches 5 exact patterns. | Regex only | Strongly-likely | script.py:643-646 |
| F5 | G4 | Placeholders inside code fences (backtick blocks) false-positive. PRDs with template code examples will fail. | Nothing (no fence detection) | Strongly-likely | script.py:643-668 |
| F6 | G4 | `reason:` attribution only checks same line or next line. Two lines below = bare placeholder. | Convention only | Likely | script.py:652-659 |
| F7 | G5 | `detect-capabilities` returns `recommended_mode: "D"` when atlas-loop + atlas-cdd detected. HANDOFF.md says "Mode D never recommended." Script contradicts phase file. | Convention only (AI must override deterministic layer) | **Strongly-likely** | script.py:1818-1820 vs HANDOFF.md:37,41 |
| F8 | G5 | Alternative modes E-J in `alternative_modes` array. Nothing prevents AI from presenting all upfront. | Convention only | Likely | HANDOFF.md:92-103 |
| F9 | G6 | MCP `tm_expand(task_id=N)` accepts per-id calls. Nothing prevents parallel invocation reintroducing the race. | Convention only (GENERATE.md warns, MCP allows) | Strongly-likely | server.py:277-300 |
| F10 | G6 | `task-master expand --all` is serial because upstream CLI implements it that way. If TaskMaster changes to parallel, guarantee breaks silently. | External dependency assumption | Likely | GENERATE.md:126 |
| F11 | G7 | **Three sources disagree on default provider.** SKILL.md: claude-code. SETUP.md: Gemini CLI. validate-setup fix hint: claude-code. | Documentation conflict | **Strongly-likely** | SETUP.md:67-84 vs SKILL.md:54 vs script.py:1674 |
| F12 | G7 | Gemini CLI requires Google account auth. Not truly "zero API key" -- requires `gcloud auth` or `gemini auth login`. | Nothing | Likely | SETUP.md:76 |
| F13 | G8 | `EnterPlanMode` is NOT in SKILL.md `allowed-tools` list. If allowed-tools is a whitelist, the tool is architecturally blocked. | **Not at all** | **Strongly-likely** | SKILL.md:9-18 |
| F14 | G8 | `handoff-gate --recommended` is documented as deterministic enforcement but says "(when implemented)." It does NOT exist in script.py. | **Not at all** | **Inevitable** | HANDOFF.md:201-202 |
| F15 | G8 | Dual-tool-call is pure prose. AI can skip both tools without consequence. No hook enforces invocation. | Convention only | Strongly-likely | HANDOFF.md:161-206 |
| F16 | G9 | SETUP.md Step 3 contains a full decision tree for provider config. This is deterministic logic in an AI-judgment file. | Convention only | Likely | SETUP.md:47-62 |
| F17 | G9 | GENERATE.md contains an inline Python verification script (lines 154-178) that should be a script.py subcommand. | Convention only | Strongly-likely | GENERATE.md:154-178 |
| F18 | G10 | Checks 2-3 require exact strings ("user impact", "business impact", "revenue", "cost"). Pentest/learning PRDs lack these. | Regex only (no domain-adaptive alternatives) | Strongly-likely | script.py:463-489 |
| F19 | G10 | Check 5 (user stories) requires `### Story N` + `- [ ]` checkboxes. Non-software domains won't use this. | Template-enforced only | Likely | script.py:507-521 |
| F20 | G10 | Check 8 requires `REQ-NNN`. Alternative numbering (R-001, Req-1, bullets) scores 0. | Template-enforced only | Likely | script.py:552-560 |
| F21 | G10 | Autonomous mode self-brainstorm questions are software-biased. | Convention only | Best-effort | DISCOVER.md:33-43 |
| F22 | G11 | MCP `validate_prd` does NOT expose `--ai` flag. AI-augmented review is CLI-only despite MCP-first preference. | **Architecturally blocked** | **Inevitable** | server.py:87-89 |
| F23 | G11 | MCP `calc_tasks` only exposes `requirements_count`. Missing `--team-size`, `--scope-phase`, `--thematic-groups`. Context-aware formula inaccessible via MCP. | **Architecturally blocked** | **Inevitable** | server.py:102-104 |
| F24 | G11 | `validate-setup` is referenced in SKILL.md as MCP tool but does NOT exist in server.py. Documentation lie. | **Not at all** | **Inevitable** | SKILL.md:51-52 vs server.py |
| F25 | G12 | `append-workflow` has no MCP tool wrapper. MCP-first users must fall back to CLI. | Not exposed | Strongly-likely | server.py (absent) |
| F26 | G12 | Sentinel check is substring match. If markers remain but content is deleted, check says "present" and skips write. | Convention only | Likely | script.py:996-998 |
| F27 | G2 | Phase file paths hardcoded to install location. Dev/test contexts get wrong paths. | Convention only | Likely | SKILL.md:47-48 |
| F28 | G3 | `_ai_review_prd` extracts JSON from LLM output using `rfind('}')`. Nested braces in code examples break extraction. | Heuristic only | Strongly-likely | script.py:409-417 |
| F29 | G1 | System-level failures (npm behind proxy, no sudo) cascade to unavoidable user questions. | Nothing | **Inevitable** | script.py:1608-1715 |
| F30 | G6 | Inline Python verification handles 3 tasks.json shapes via heuristic. Schema evolution breaks counting. | Heuristic | Likely | GENERATE.md:157-166 |
| F31 | G8 | Debrief called with `|| true` in HANDOFF. If debrief already exists, call silently fails. No update path. | Design tension | Likely | HANDOFF.md:217 |
| F32 | G7 | validate-setup fix hint suggests `sonnet --claude-code` while SETUP.md says Gemini CLI. Auto-fix and phase disagree. | Documentation/code conflict | Strongly-likely | script.py:1674 vs SETUP.md:67-76 |
| F33 | DIST | **install.sh does NOT copy `phases/` directory.** Fresh installs are 100% broken -- SKILL.md says `Read phases/SETUP.md` but the directory was never installed. | **Not at all** | **INEVITABLE** | install.sh:232-258 (missing phases/) |

---

## Section 3: Failure Class Mechanisms

| # | Class | Modes | Proposed Mechanism | Type | Ease | Impact |
|---|---|---|---|---|---|---|
| M1 | **Distribution Integrity** | F33 + 5 more (no checksums, wrong branch, incomplete backup, broken version compare) | Manifest-based install + SHA256 verification + copy ALL required dirs | Code (install.sh rewrite) | Easy | **CRITICAL** |
| M2 | **File Atomicity** | F9, F10, F26, F30 + progress.md/execution-state.json races | `_atomic_write()` via os.replace + `_locked_update()` via fcntl.flock | Code (new module) | Easy | High |
| M3 | **Pipeline State Machine** | F16 phase skipping, re-entry undefined, crash recovery blind to phase | `pipeline.json` + `advance-phase` + `current-phase` subcommands | Architecture | Medium | High |
| M4 | **AI Compliance Drift** | F7, F8, F13, F15, F17 (7 total prose-only gates) | Deterministic `check-gate --phase N --evidence <json>` subcommand | Code + SKILL.md rewrite | Medium | High |
| M5 | **External Dependency Drift** | F10, F11, F28, F30 (TaskMaster flag/schema/format changes) | Contract test suite + version-gated feature map | Code + Tests | Medium | High |
| M6 | **MCP/CLI Parity** | F22, F23, F24, F25 (missing tools/params/docs lies) | `test_mcp_parity.py` -- introspects argparse + FastMCP, asserts coverage | Tests | Easy | Medium |
| M7 | **Validation Completeness** | F4, F5, F6, F18-F20 (shallow regex, domain bias) | Markdown AST parser + check severity tiers + configurable vague-word list | Code (refactor) | Medium | Medium |

---

## Section 4: Guarantee Scoring

| G | Guarantee | Current Tier | Evidence | Mechanism(s) | After Mechanisms |
|---|---|---|---|---|---|
| G1 | Zero setup questions | **Best-effort** | F1 (provider Qs), F2 (probe failure), F29 (system failures) -- some questions are unavoidable | M3 (state), M4 (gates) | Likely |
| G2 | Phase files Read explicitly | **Best-effort** | F27 (hardcoded paths). Nothing prevents AI from reading ahead. | M4 (gate enforcer) | Likely |
| G3 | JSON on stdout | **Likely** | F3 (empty coercion), F28 (brace heuristic). Tests pin shapes. | M5 (contract tests) | Strongly-likely |
| G4 | Catches ALL placeholders | **Strongly-likely** | F4 (narrow regex), F5 (code fence false positive), F6 (attribution gap) | M7 (AST validator) | Strongly-likely |
| G5 | ONE mode recommendation | **Best-effort** | F7 (script returns D despite "never"), F8 (alternatives leak) | M4 (gate: check-gate validates mode != D), fix script.py | Strongly-likely |
| G6 | Serial expansion | **Likely** | F9 (MCP allows parallel), F10 (upstream assumption), F30 (schema drift) | M2 (flock), M5 (contract tests) | Strongly-likely |
| G7 | Default provider | **Hopeful** | F11 (3 sources disagree), F12 (not truly zero-key), F32 (auto-fix contradicts phase) | Align all 3 sources + honest docs | Likely |
| G8 | Dual-tool-call gate | **Hopeful** | F13 (not in allowed-tools!), F14 (handoff-gate unimplemented), F15 (pure prose) | Add EnterPlanMode to allowed-tools, implement handoff-gate, add hook | Likely |
| G9 | Codification split | **Likely** | F16 (decision tree in phase file), F17 (inline Python in phase file) | Extract to script.py subcommands | Strongly-likely |
| G10 | Domain-agnostic | **Best-effort** | F18-F20 (software-biased checks), F21 (software-biased brainstorm Qs) | M7 (domain-adaptive checks) | Likely |
| G11 | MCP-first preference | **Hopeful** | F22-F24 (missing tools, missing params, documented lies) | M6 (parity test) | Likely |
| G12 | Idempotent append | **Likely** | F25 (no MCP tool), F26 (empty-between-markers) | Expose MCP tool, content validation | Strongly-likely |

---

## Section 5: Tier Summary

### Current State

| Tier | Count | Guarantees |
|---|---|---|
| Inevitable | 0 | -- |
| Strongly-likely | 0 | -- |
| Likely | 3 | G3, G6, G9, G12 |
| Best-effort | 5 | G1, G2, G4, G5, G10 |
| **Hopeful** | **3** | **G7, G8, G11** |

**No guarantee reaches Strongly-likely or above.** Three are Hopeful (convention-only).

### After Proposed Mechanisms

| Tier | Count | Guarantees |
|---|---|---|
| Inevitable | 0 | -- |
| Strongly-likely | 5 | G3, G4, G5, G6, G9, G12 |
| Likely | 6 | G1, G2, G7, G8, G10, G11 |
| Best-effort | 0 | -- |
| Hopeful | 0 | -- |

All Hopeful guarantees eliminated. Minimum tier becomes Likely.

---

## Section 6: Critical Findings (Act Now)

### SHIP BLOCKER: install.sh doesn't copy phases/

`install.sh` lines 232-258 copy SKILL.md, script.py, templates/, reference/ -- but NOT phases/. Every fresh install from `curl | bash` produces a skill that immediately fails when SKILL.md says `Read ~/.claude/skills/prd-taskmaster-v2/phases/SETUP.md`. This is not a theoretical failure -- it is a live, 100%-reproduction bug.

### SHIP BLOCKER: EnterPlanMode not in allowed-tools

SKILL.md frontmatter lists 9 allowed tools. `EnterPlanMode` is not one of them. If Claude Code enforces `allowed-tools` as a whitelist, the mandatory HANDOFF Step 5 gate is architecturally impossible.

### DOCUMENTATION LIE: handoff-gate documented but unimplemented

HANDOFF.md:201-202 references `script.py handoff-gate --recommended <A|B|C>` as an existing deterministic enforcement path. It says "(when implemented)" in parentheses. It does not exist. Downstream readers (including the AI) may assume it works.

### DOCUMENTATION LIE: validate-setup MCP tool referenced but missing

SKILL.md:51-52 says `mcp__prd-taskmaster__validate_setup()`. server.py has no such tool.

### THREE-WAY DEFAULT CONFLICT

SKILL.md says `claude-code`. SETUP.md says `Gemini CLI`. validate-setup's fix hint says `sonnet --claude-code`. A user reading different files gets different advice.

---

## Section 7: Irreducible Modes (Cannot Be Fixed)

| Mode | Why Irreducible | Mitigation |
|---|---|---|
| F2: Probe test failure requires user input | API key issues are fundamentally user-environment problems. No automation can fix "wrong key." | Improve error messages, suggest Bitwarden check. Accept that G1 is aspirational. |
| F29: System-level failures (npm proxy, no sudo) | OS/network constraints are outside the skill's control surface. | Surface clear diagnostics. Accept that zero-questions is a goal, not a guarantee. |
| AI can always ignore instructions | No amount of documentation prevents a model from skipping a step in long context. | M4 (tool-call gates) reduces probability but cannot reach Inevitable tier for prose-instructed behavior. |
