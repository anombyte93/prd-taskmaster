# Product Specification — `prd-taskmaster` v4.0.0

> Open-core "goal → validated PRD → executable task graph → CDD-gated execution" engine for
> Claude Code. Repo `anombyte93/prd-taskmaster` (508★, name retained). Free MIT engine +
> commercial **Atlas Pro**. This document is the contract the dogfood `ship-check` verifies
> against — it is a living doc, updated as the product evolves.

**Codebase basis:** 5-phase state machine `SETUP→DISCOVER→GENERATE→HANDOFF→EXECUTE`
(`prd_taskmaster/pipeline.py`), FastMCP tools (`mcp-server/server.py`), deterministic PRD
checks with EXCELLENT/GOOD/ACCEPTABLE/NEEDS_WORK grading (`prd_taskmaster/validation.py`),
capability/mode detection (`prd_taskmaster/capabilities.py`), atomic flock-guarded state
(`prd_taskmaster/lib.py`), a CDD execute-task loop (`skills/execute-task/SKILL.md`), and a
deterministic 5-gate ship-check emitting `SHIP_CHECK_OK` (`skel/ship-check.py`). The paid
fleet is the `atlas-launcher` MCP (worktree-isolated tmux workers, dependency-wave dispatch,
SQLite inbox collection, integration-branch merge).

---

## 1. Personas

### P1 — Indie Ivy (Solo Indie Developer)
- **Goals:** Ship side-projects/MVPs fast; turn a rough idea into shippable code without
  writing a spec by hand; avoid ad-hoc prompting that drifts.
- **Pains today:** Claude Code sessions lose the thread; no structure between "idea" and
  "code"; verification is vibes-based; re-prompts cost time and money.
- **Lands on:** FREE. Solo single-session execution + free research is enough.
- **Willingness to pay:** Low ($0–9/mo). Converts only when builds are big enough to want
  overnight parallelism.

### P2 — Lead Theo (Small-Team Tech Lead, 2–6 devs)
- **Goals:** Standardize idea→PRD→tasks; enforce quality gates so junior output is verifiable;
  ship features overnight; reduce review thrash.
- **Pains today:** Inconsistent specs; no shared "definition of done"; can't parallelize agent
  work safely (tasks.json corruption, merge conflicts); no audit trail.
- **Lands on:** PAID Atlas Pro. Dependency-wave fleet + git-worktree isolation + durable inbox
  audit trail directly solve his parallelism and accountability pain.
- **Willingness to pay:** High ($29–99/mo per seat).

### P3 — Orchestrator Olu (AI Power-User / Agent Orchestrator)
- **Goals:** Run fleets of parallel agents across many sessions; walk away and return to proof;
  squeeze cost via model-agnostic dispatch (claude/codex/gemini).
- **Pains today:** DIY tmux orchestration is brittle; spawned sessions silently fail to receive
  their task; no durable wave-state; no deterministic completion token they can trust.
- **Lands on:** PAID Atlas Pro (heaviest user). Buys for `atlas-launcher`, wave scheduling,
  bundled MCPs.
- **Willingness to pay:** Highest ($29–149/mo); evangelizes. Primary churn risk if fleet
  reliability slips.

### P4 — Contributor Cam (OSS Contributor / Evaluator)
- **Goals:** Evaluate, file issues/PRs, fork, learn the architecture.
- **Pains today:** Closed black-box AI tools; abandoned repos; zero-test plugins.
- **Lands on:** FREE (MIT). Drives stars, credibility, top-of-funnel.
- **Willingness to pay:** Near-zero, high strategic value.

---

## 2. KPIs / Success Metrics

Targets: **[v4.0.0 launch] → [+6 months]**.

### Adoption (FREE)
| KPI | Definition | Target |
|---|---|---|
| A1 Installs | Cumulative npm/plugin + curl installs (postinstall ping, opt-out) | 2,000 → 12,000 |
| A2 Stars growth | Net new GitHub stars | +250 (758★) → +1,500 (≈2,000★) |
| A3 WAI | Distinct installs invoking `/atlas` ≥1×/week | 400 → 2,500 |
| A4 Skill-vs-plugin split | % invocations via zero-dep skill vs FastMCP plugin | ≥40% plugin |

### Activation
| KPI | Definition | Target |
|---|---|---|
| AC1 Full-run completion | % of pipelines reaching EXECUTE with ≥1 task done | 35% → 55% |
| AC2 Reach-execution | % advancing past HANDOFF | 50% → 70% |
| AC3 PRD validation pass | % of PRDs grade ≥ GOOD on first validate | 60% → 80% |
| AC4 Time-to-first-tasks.json | Median wall-clock /atlas → parsed tasks.json | ≤15 min → ≤8 min |

### Conversion (PAID)
| KPI | Definition | Target |
|---|---|---|
| C1 Free→Pro | % monthly active free users starting a subscription | 1.5% → 4% |
| C2 Trial→paid | % trials converting to a paying month | 25% → 40% |
| C3 MRR | Monthly recurring revenue at ~$29/mo | $1.5k → $12k |
| C4 Monthly churn | % paid cancellations / month | <8% → <5% |
| C5 Fleet runs/user | Mean fleet runs per paid user / month | 4 → 12 |

### Quality / Trust
| KPI | Definition | Target |
|---|---|---|
| Q1 Task completion | % parsed tasks reaching done within a run | 70% → 88% |
| Q2 SHIP_CHECK_OK rate | % EXECUTE runs emitting the deterministic token (5 gates pass) | 45% → 70% |
| Q3 Rework rate | % done tasks reopened/blocked within same run (false-done proxy) | <20% → <10% |
| Q4 NPS | 0–10 promoter score, in-CLI + post-run | +20 → +40 |

> Q2/Q3 are the trust differentiators — the deterministic `SHIP_CHECK_OK` (Gate 5 forbids any
> non-zero `Exit status N` in evidence) is the marketing-grade proof that completion is real,
> not narrated. Instrument it as the headline reliability metric.

---

## 3. User Stories (by Epic)

### Epic: Discovery
- **US-D1 [FREE]** As Indie Ivy, I want adaptive one-question-at-a-time discovery, so that I
  don't write a spec from a blank page.
  - AC: `discover` invokes `superpowers:brainstorming` (interactive) or self-brainstorms
    (autonomous); emits `CONSTRAINTS CAPTURED`; classifies scale Solo/Team/Enterprise; gate
    requires `user_approved` OR `auto_classification=CLEAR` + `assumptions_documented`.
- **US-D2 [FREE]** As Orchestrator Olu, I want autonomous discovery in unattended sessions, so
  that fleet/cron runs don't stall on a modal prompt.
  - AC: autonomous mode never blocks; writes + commits a discovery file as audit trail.

### Epic: PRD Generation
- **US-G1 [FREE]** As any user, I want my PRD scored against deterministic checks with a letter
  grade, so that I know it's testable before I build.
  - AC: `validate_prd` runs the checks; grades EXCELLENT≥91 / GOOD≥83 / ACCEPTABLE≥75 /
    NEEDS_WORK<75; bare placeholders = hard fail; vague-language penalty.
- **US-G2 [FREE]** As Lead Theo, I want deferred decisions allowed when attributed (`reason:`),
  so that a thin spec is honest rather than blocked.
- **US-G3 [FREE]** As any user, I want every task expanded into subtasks before handoff.
  - AC: GENERATE gate requires `task_count>0` AND `subtask_coverage==1.0`; expansion via the
    backend-aware token-economy decision tree (FR-30): TaskMaster backend when explicitly selected
    or available under auto, native backend otherwise, agent_action_required fallback when no API
    key is available. Concurrent expands in ONE directory remain forbidden (lock-stale race) —
    isolation dirs are the parallel mechanism.

### Epic: Task Planning
- **US-T1 [FREE]** As any user, I want task count calibrated to project scale.
  - AC: `calc_tasks` → Solo 8–12 / Team 12–20 / Enterprise 20–30.
- **US-T2 [FREE]** As any user, I want TaskMaster-native complexity scoring so dispatch can tier
  the model per task.
  - AC: complexity read from `.taskmaster/reports/task-complexity-report.json`, not stdout.

### Epic: Solo Execution
- **US-E1 [FREE]** As Indie Ivy, I want a CDD-gated single-session loop where each task is
  verified by evidence before done.
  - AC: 13-step `execute-task` cycle; complexity-tiered subagent dispatch; triple-verify + hard
    exit-code gate; one task pending→done per iteration.
- **US-E2 [FREE]** As any user, I want a deterministic completion token, so "done" is provable.
  - AC: `SHIP_CHECK_OK` emitted only when all 5 gates pass; `/sync` first; appears exactly once.
- **US-E3 [FREE]** As any user, I want a crashed pipeline to resume.
  - AC: `preflight` recommends resume/parse/generate/setup from on-disk state; every phase skill
    re-reads `current_phase()` on entry.

### Epic: Parallel Fleet (PRO)
- **US-F1 [PRO]** As Lead Theo, I want my task graph dispatched as dependency waves of
  file-disjoint chunks across many sessions, so the build finishes overnight.
- **US-F2 [PRO]** As Orchestrator Olu, I want durable result collection + verified handoff, so a
  worker that silently failed to receive its task is caught.
  - AC: every spawn verifies `prompt_injected`; results collected via SQLite inbox, not the
    worker's word.
- **US-F3 [PRO]** As Lead Theo, I want git-worktree isolation + sequential integration so
  parallel writers never corrupt `tasks.json` or hide merge conflicts.
- **US-F4 [PRO]** As Orchestrator Olu, I want model-agnostic backends (claude/codex/gemini).

### Epic: Monetization / Licensing
- **US-M1 [PRO]** As a paying user, I want a license key that unlocks the fleet installer.
- **US-M2 [PRO]** As a paying user offline, I want a grace period so a flaky network doesn't
  brick my fleet mid-run. FREE engine never degrades.
- **US-M3 [FREE]** As a free user, I want a non-intrusive Pro teaser at handoff.
  - AC: HANDOFF shows "Atlas Fleet (Pro)" as a non-selectable teaser with a checkout URL;
    selecting it returns the upgrade path and re-prompts free modes.

### Epic: Onboarding
- **US-O1 [FREE]** As Indie Ivy, I want a one-line install + first run.
  - AC: curl-install or `npm i -g`; `setup` detects task-master, DETECT-FIRST provider config
    (never overwrites working config), scaffolds `.atlas-ai/`.
- **US-O2 [FREE]** As any user, I want the engine to recommend solo vs fleet from what I have
  installed.

---

## 4. Use Cases

### UC-1 — First-time install & first goal *(FREE)*
Primary: Indie Ivy. Pre: Claude Code installed; Node/Python present.
Main: Install → `/atlas` → preflight+current_phase route to setup → SETUP validates/configures,
selects a backend, scaffolds `.atlas-ai/` → DISCOVER brainstorm → GENERATE writes+validates PRD
(≥ACCEPTABLE) → parses tasks.json, expands subtasks → HANDOFF recommends a solo mode → user
picks → EXECUTE loop to `SHIP_CHECK_OK`.
Alt: task-master missing → select native backend and report the optional install cmd (never
auto-install). Config present → DETECT-FIRST skips. Grade NEEDS_WORK → fix-loop (UC-4).

### UC-2 — Resuming a crashed pipeline *(FREE)*
Pre: `.atlas-ai/state/pipeline.json` + `.taskmaster/` exist.
Main: `/atlas` → preflight reads state → recommends resume → routes to recorded phase →
execute-task resumes at next ready task.
Alt: PRD exists, 0 tasks → parse_prd. Deadlock → report + halt. Bookkeeping drift >5 tasks →
halt, do not silently reconcile.

### UC-3 — Parallel fleet build *(PRO)*
Pre: valid Atlas Pro license; `atlas-launcher` alive; git repo with committed PRD+tasks.
Main: provision deps → recon → file-disjoint chunks → checker approves → commit base,
`session_spawn` per chunk, verify+kick → monitor (inbox-first) → merge wave branches
sequentially into integration branch, checker green-gates → next wave → final single PR →
`SHIP_CHECK_OK`.
Alt: `prompt_injected:false` → kick. Not file-disjoint → re-partition. Worker blocked → logged
via inbox, never faked. No launcher → fall back to FREE solo EXECUTE.

### UC-4 — PRD validation failure → fix loop *(FREE)*
Main: `validate_prd` → NEEDS_WORK or bare_placeholders>0 → surface failed checks + vague terms →
revise → re-validate → on ≥GOOD + 0 bare placeholders, gate passes.
Alt: ACCEPTABLE → offer proceed-with-risk vs auto-fix (never silently advance).

### UC-5 — Subscribing & license activation *(PRO)*
Main: teaser at HANDOFF → checkout URL → pay (Stripe) → license key → run installer with key →
validate online → provision atlas-launcher + bundled MCPs → next `/atlas` HANDOFF offers fleet
as selectable.
Alt: invalid/expired key → installer refuses, gated artifacts never fetched. Network failure →
retry with backoff; FREE engine remains functional throughout.

### UC-6 — License lapse / offline grace *(PRO)*
Main: fleet dispatch checks cached token → within grace → proceeds → background re-validation
when network returns.
Alt: grace expired → fleet refuses new dispatch with renewal prompt; in-flight run drains to
completion (no mid-run brick); FREE solo unaffected. Cancelled → locks at next dispatch.

### UC-7 — Handoff mode recommendation *(FREE)*
Main: `detect_capabilities` → recommends ONE mode → AskUserQuestion picker (recommended default)
→ dispatch.
Alt: AskUserQuestion hook-blocked → prose fallback table + `[AI]` insight block. Fleet teaser
shown but unlicensed → returns upgrade path, re-prompts free modes.

---

## 5. User Flows

### (a) Free quickstart: curl-install → first tasks.json
1. Run curl one-liner (or `npm i -g prd-taskmaster`); postinstall installs Python MCP deps
   (warns, never hard-fails).
2. `/atlas` → preflight + current_phase → null → route setup.
3. SETUP: select backend (`auto|taskmaster|native`), report optional TaskMaster install if
   missing, initialize `.taskmaster/` task state → DETECT-FIRST provider config → scaffold
   `.atlas-ai/` + ship-check → advance SETUP→DISCOVER.
4. DISCOVER: interactive brainstorm → CONSTRAINTS CAPTURED + scale → approve → advance.
5. GENERATE: load template → fill PRD → CONSTRAINT + SCOPE check → validate_prd (NEEDS_WORK →
   fix-loop) → calc_tasks → parse_prd → analyze-complexity → expand --all → coverage 1.0 →
   tasks.json exists → advance GENERATE→HANDOFF.
6. Outcome: `.taskmaster/tasks/tasks.json` populated. *(median target ≤8 min)*

### (b) Handoff mode selection (solo vs fleet)
1. `detect_capabilities()` → per-tool flags + tier + recommended mode + alternatives.
2. Decision (first match): superpowers+ralph-loop → Verified Loop; superpowers only → Plan &
   Drive; task-master only → Auto-Execute; fallback → Plan & Drive.
3. License branch: valid license + launcher → Atlas Fleet selectable; else non-selectable teaser
   with checkout URL.
4. Append idempotent task-workflow block to CLAUDE.md (HTML-comment sentinels, timestamped
   backup).
5. AskUserQuestion picker, recommended = default (hook-blocked → prose fallback + `[AI]`).
6. Dispatch chosen mode. Selecting teaser unlicensed → upgrade path + re-prompt.

### (c) Upgrade-to-Pro
1. Free user hits Fleet teaser at HANDOFF (or an inline "fleet would finish 4× faster" hint when
   task count/complexity is high).
2. Checkout URL → Stripe → pay → license key.
3. Run installer with key → online validation (invalid → refuse, fetch nothing) → cache signed
   offline-grace token → provision launcher + bundled MCPs.
4. Next `/atlas` → tier=premium → HANDOFF offers Atlas Fleet as selectable.
5. Outcome: fleet unlocked; free engine unchanged.

### (d) Fleet execution run *(PRO)*
1. Wave dispatch: provision (PRD+tasks, git base committed, launcher alive) → partition into
   file-disjoint chunks → topo-order into waves → checker approves (overlap → re-partition).
2. Spawn: commit base → `session_spawn(isolation="worktree")` (or `session_create` for
   codex/gemini) per chunk → verify `prompt_injected` (false → kick + confirm).
3. Worker CDD loop: each worker runs the 13-step execute-task cycle in its worktree on its own
   branch.
4. Result collection: monitor (inbox-first) → done/blocked (blocked → log, skip-not-fabricate;
   dead worker → bounded retry then escalate).
5. Merge: integrate wave branches sequentially into integration branch → checker green-gates
   (red → halt, surface) → advance until current_wave > total.
6. Ship: final single PR; ship-check 5 gates → `SHIP_CHECK_OK`; main never auto-touched.

---

## 6. Functional Requirements

Tags: **[FREE]/[PRO]**, phase.

**Engine / Orchestration**
- **FR-1 [FREE]** The orchestrator MUST route purely on `current_phase()`+`preflight()` and
  re-check after each phase, holding no procedure itself.
- **FR-2 [FREE]** Phase transitions MUST be atomic CAS (`advance_phase(expected,target,evidence)`)
  over flock-guarded `pipeline.json`; a stale `expected` MUST error, not write.
- **FR-3 [FREE]** Only `None→SETUP→DISCOVER→GENERATE→HANDOFF→EXECUTE` MUST be permitted; illegal
  transitions rejected with the legal set.
- **FR-4 [FREE]** Every phase skill MUST be resumable by re-reading `current_phase()` on entry.

**SETUP**
- **FR-5 [FREE]** SETUP MUST run 6 backend-aware checks (project, backend selection,
  TaskMaster binary/version ≥0.43.0 when the TaskMaster backend is selected or detected, config,
  main provider, research provider) with per-check pass/fail + fix/notice; missing TaskMaster is
  an optional-backend notice, while version/research remain warnings.
- **FR-6 [FREE]** Provider config MUST be DETECT-FIRST: never overwrite a working config; only
  fill empty roles; ask before mutating an unsupported provider.
- **FR-7 [FREE]** SETUP MUST scaffold `.atlas-ai/customizations/` + `.atlas-ai/ship-check.py`
  before EXECUTE. MUST NOT auto-install task-master.

**DISCOVER**
- **FR-8 [FREE]** Interactive MUST use `superpowers:brainstorming` and intercept before it chains
  to `writing-plans`; autonomous MUST NOT block and MUST write a committed discovery file.
- **FR-9 [FREE]** DISCOVER MUST emit `CONSTRAINTS CAPTURED` + scale; gate requires `user_approved`
  OR (`auto_classification=CLEAR` + `assumptions_documented`).

**GENERATE / Validation**
- **FR-10 [FREE]** `validate_prd` MUST run the deterministic checks and grade EXCELLENT≥91 /
  GOOD≥83 / ACCEPTABLE≥75 / NEEDS_WORK<75 with the vague-language penalty.
- **FR-11 [FREE]** Bare placeholders (`{{}}`,`[TBD]`,`[TODO]`,`[FIXME]`,`[PLACEHOLDER]` without
  `reason:`/`defer:`) MUST be a hard fail; attributed placeholders recorded as
  `deferred_decisions`.
- **FR-12 [FREE]** GENERATE gate MUST require grade ∈ {EXCELLENT,GOOD}, `task_count>0`,
  `subtask_coverage==1.0`. Subtask expansion MUST follow the FR-30 decision tree; concurrent
  expands in a single project directory are forbidden (lock-stale race).
- **FR-13 [FREE]** Complexity MUST be read from the report JSON, never the stdout table.
  `calc_tasks` MUST calibrate count to scale.

**Capability detection / HANDOFF**
- **FR-14 [FREE]** `detect_capabilities` MUST scan Claude plugins, skills, external CLIs, and
  taskmaster (MCP>CLI>none), and recommend ONE mode with a reason.
- **FR-15 [FREE]** HANDOFF MUST present mode choice via AskUserQuestion with recommended default;
  hook-blocked → prose table + `[AI]` block. MUST append the task-workflow block to CLAUDE.md
  idempotently.
- **FR-16 [PRO]** With a valid license + launcher detected, Atlas Fleet MUST be selectable;
  otherwise a non-selectable teaser with a checkout URL that MUST NOT execute even if selected.

**EXECUTE / Ship gate**
- **FR-17 [FREE]** `execute-task` MUST run the 13-step CDD cycle, dispatching an implementer
  subagent (never in-session) tiered by complexity, accepting only DONE / DONE_WITH_CONCERNS /
  NEEDS_CONTEXT / BLOCKED.
- **FR-18 [FREE]** A hard exit-code gate (`ship-check --dry-run`) MUST fail any task whose
  evidence contains a non-zero `Exit status N`; override only via `SHIP_CHECK_OVERRIDE_ADMIN`,
  audit-logged.
- **FR-19 [FREE]** On done, parent task + evidenced subtasks + pipeline.json per-task state MUST
  be written consistently (no divergence).
- **FR-20 [FREE]** Termination MUST be strict: ship-check exit 0 → `/sync` → emit
  `SHIP_CHECK_OK` exactly once. 5 gates: phase==EXECUTE; all tasks done; CDD card per task; plan
  file present; no non-zero exit in evidence.

**Parallel fleet (PRO)**
- **FR-21 [PRO]** The fleet MUST partition tasks into file-disjoint chunks, topo-order into
  waves, and gate the split via a partition checker before dispatch.
- **FR-22 [PRO]** Each chunk MUST run in an isolated worktree on a committed base; spawns MUST
  verify `prompt_injected` and kick on false; results MUST be collected via the durable inbox.
- **FR-23 [PRO]** Waves MUST integrate sequentially into an integration branch, each green-gated;
  main MUST never be auto-modified; completion produces one final PR + `SHIP_CHECK_OK`.
- **FR-24 [PRO]** Fleet backends MUST be model-agnostic (claude via `session_spawn`;
  codex/gemini via `session_create`).

**Licensing / Installer**
- **FR-25 [PRO]** A license key MUST be validated online before any gated artifact is fetched;
  non-subscribers MUST never receive the gated payload or private-repo access.
- **FR-26 [PRO]** The installer MUST provision atlas-launcher + bundled MCPs only on valid
  license.
- **FR-27 [PRO]** A validated license MUST cache a signed offline-grace token; after grace, fleet
  dispatch MUST refuse new runs but allow in-flight runs to drain; the FREE engine MUST remain
  fully functional regardless of license state.

**Token economy**
- **FR-29 [FREE]** A `token_economy` setting (conservative|balanced|performance, default balanced)
  MUST control start tiers per op class, escalation steps/ceiling, and research-provider choice;
  explicit user routing/models MUST always win over presets.
- **FR-30 [FREE]** Task expansion/research MUST route through backend abstraction and token
  economy: `auto` selects the TaskMaster backend when TM ≥0.43 and a real structured API is the
  research role, otherwise native. The TaskMaster backend MAY use TaskMaster AI parallelized via
  isolated workdirs; the native backend uses direct API generation or the agent_action_required
  fallback for free proxy, no-key, provider-failure, and repo-grounded research cases.
- **FR-31 [FREE]** Every AI invocation the engine orchestrates MUST append a telemetry row
  (op_class, model, exit, wall_ms, escalated) to .atlas-ai/telemetry.jsonl; `economy-report` MUST
  summarize success-rate and p50 wall per (op_class, model).
- **FR-32 [PRO]** Adaptive auto-tuning of fleet.json routing from accumulated telemetry is an
  Atlas Pro capability (roadmap).

- **FR-33 [FREE, SHIPPED v4.1]** Backend abstraction MUST make TaskMaster one pluggable backend:
  selection is `auto|taskmaster|native`, both backends expose the 5-op protocol
  `detect/init/parse_prd/expand/rate`, and the native backend returns an `agent_action_required`
  no-key fallback when direct API generation is unavailable. Task-state ops (next/set-status) are
  engine-native under every backend. tasks.json format compatibility is permanent (the migration
  funnel from TaskMaster's ecosystem).

**Cross-cutting**
- **FR-28 [FREE]** All MCP tools MUST return dicts and MUST NEVER call `sys.exit` / terminate the
  host process.

---

## 7. Non-Functional Requirements

**Performance**
- **NFR-1** `validate_prd` MUST complete <500 ms for a ≤5k-word PRD (pure regex, no network).
- **NFR-2** Deterministic state ops MUST complete <100 ms.
- **NFR-3 [PRO]** Wave scheduling MUST complete <60 s for a ≤30-task graph.
- **NFR-4** Capability detection MUST complete <2 s (5 s subprocess timeout cap per probe).

**Reliability**
- **NFR-5** Phase transitions MUST be atomic via flock + tmp-write + `os.replace`; concurrent
  writers MUST NOT corrupt pipeline.json.
- **NFR-6 [PRO]** Under parallel fleet, tasks.json MUST NOT be corrupted — file-disjoint chunking
  + serial integration + sole-writer orchestrator.
- **NFR-7** `SHIP_CHECK_OK` MUST be emitted only when all 5 gates pass and exactly once.
- **NFR-8 [PRO]** A dead/silent worker MUST be detected (bounded retries) and surface a blocker.

**Security**
- **NFR-9 [PRO]** License keys MUST be stored securely (chmod 600 / keychain), never logged or
  committed.
- **NFR-10 [PRO]** Bundled-MCP secrets MUST never be logged or committed.
- **NFR-11 [PRO]** Private fleet assets MUST NOT leak to non-subscribers; gated artifacts fetched
  only after server-side validation.
- **NFR-12 [FREE]** The FREE tier MUST require no paid API key.

**Portability**
- **NFR-13** MUST run on Linux, macOS, WSL. `fcntl.flock` is POSIX-only — native Windows
  unsupported for the atomic-state path; document and detect, do not silently misbehave.

**Compatibility**
- **NFR-14** MUST support `task-master-ai >= 0.43.0` and degrade gracefully (warning) on
  older/unparseable versions.
- **NFR-15** MUST conform to the Claude Code plugin API (FastMCP, hooks.json, skills,
  marketplace/plugin.json) and tolerate AskUserQuestion being hook-blocked.

**Maintainability**
- **NFR-16** Deterministic logic MUST have a single source of truth shared by both the zero-dep
  skill and the FastMCP plugin — no divergent re-implementations.
- **NFR-17** Test coverage MUST gate releases; string-shape assertions MUST be backed by
  runtime-resolution checks.

**Cost**
- **NFR-18 [FREE]** A complete free run MUST be achievable at $0 marginal API cost using the
  default free provider stack.
- **NFR-19 [PRO]** Complexity-tiered dispatch MUST keep dollars-per-task sane.

---

## 8. Narrative — "What the final product looks like"

`prd-taskmaster` is the open-core engine that turns *"I want to build X"* into shipped,
**verified** code inside Claude Code — replacing ad-hoc prompting with a structured, auditable
pipeline.

A developer installs it free (MIT) from the 508★ repo and types `/atlas`. The engine walks a
five-phase state machine with atomic, flock-guarded transitions: **SETUP** detects and configures
the environment without overwriting working config; **DISCOVER** runs adaptive brainstorming (or
self-brainstorms unattended) and captures constraints + scale; **GENERATE** writes a PRD, scores
it against deterministic quality checks with a letter grade — bare placeholders are a hard fail,
attributed deferrals are honest — then parses it into a TaskMaster task graph with complexity
scores and full subtask coverage; **HANDOFF** detects what the user has installed and recommends
one execution mode through a structured picker; **EXECUTE** runs a CDD-gated loop where every task
is implemented by a complexity-tiered subagent and proven by evidence, culminating in a
deterministic `SHIP_CHECK_OK` token that is structurally impossible to fake (a non-zero exit code
in any evidence file blocks it). The whole free run costs $0 in API spend and works on
Linux/macOS/WSL.

The free engine is genuinely complete and useful on its own — and it is the funnel. At the
handoff, power users see **Atlas Pro** ($29/mo): **Atlas Fleet**, which lifts the same engine from
one session to many. A license-gated installer provisions the `atlas-launcher` daemon and bundled
MCPs. Fleet partitions the task graph into file-disjoint chunks, schedules them in dependency
waves, spawns model-agnostic tmux workers (claude/codex/gemini) in isolated git worktrees,
collects results through a durable inbox rather than trusting an agent's word, and merges waves
sequentially into an integration branch behind a checker gate — never touching `main` until one
final green PR. Licenses validate online with an offline grace window so a flaky network never
bricks a run, secrets never hit logs, and nothing private leaks to non-subscribers.

The result is a single coherent promise across both tiers: **you can answer, at every moment, "is
what I built what I wanted?"** — free for solo builders, and at fleet scale for teams and
orchestrators who want to walk away and come back to proof.
