# UX & Product-Presentation Specification — Atlas / `prd-taskmaster`

> Surfaces: terminal interaction (Claude Code skill), GitHub README storefront,
> atlas-ai.au/pro pricing page, install/upgrade flows. Living doc — the canonical vocabulary
> here (§6) governs every user-facing string in the codebase.

## 0. Design principles

1. **One screen, one decision.** Every phase ends in exactly one structured choice
   (AskUserQuestion). Never present >4 options.
2. **Status blocks have a fixed grammar.** Same box style, symbol set, and order
   (what happened → evidence → next step) in every phase.
3. **Evidence over assertion.** Never print "validated ✓" without the number, grade, and what
   failed. The product's pitch is verification — its own output must model it.
4. **The paywall is a fact, not a trap.** Locked features show real value computed from *this*
   project, state the price inline, never default-select, never re-prompt.
5. **MIT-free-forever is the trust anchor.** Every commercial surface repeats: the engine is
   free, open, model-agnostic; Pro adds orchestration + bundled MCPs.
6. **Junior-comprehensible, zero system jargon.** No "phoenix", "CDD", "ralph-loop", or "Mode D"
   as a primary label in anything a user reads.
7. **Monochrome-first.** Every state = symbol + word. Color and emoji are enhancement only.

---

## 1. Terminal interaction design

### Phase shape (all phases)
```
┌─ atlas ── PHASE n/4: NAME ─────────────────────────┐   ← phase header bar (always n/4)
│  ...status lines / question / result               │   ← body
└─────────────────────────────────────────────────────┘
  Next: <one sentence>                                    ← single next step
```
Gates surface as `Gate passed:` / `Gate blocked:` lines inside the body — never raw JSON.

### Moment 1 — Preflight (zero-config but legible)
```
┌─ atlas ── PHASE 1/4: PREFLIGHT ────────────────────────────┐
│  ✓ TaskMaster        MCP                                   │
│  ✓ AI provider       Claude Code (sonnet)                  │
│  ✓ Research          Perplexity (local, free)              │
│  ○ Browser verify    not installed — optional              │
│                                                            │
│  Gate passed: environment ready, nothing to configure.     │
└────────────────────────────────────────────────────────────┘
  Next: a short interview about your goal — one question at a time.
```
Missing *optional* capabilities use `○ … — optional`, never `✗`. `✗` is reserved for blockers:
```
│  ✗ TaskMaster        not found — required                  │
│  Gate blocked: TaskMaster is the task engine.              │
│  Fix:  npm install -g task-master-ai     (~30s)            │
│  Or:   say "manual" and I'll do its job by hand.           │
```

### Moment 2 — Discovery (the interview)
```
  Discovery 3 of ~6 — scope
  ─────────────────────────
  So far: CLI tool · for your own team · must stay Python-only

  Should v1 handle concurrent runs, or is single-user fine?
  (Single-user is the simpler bet — say "simpler" to take defaults
   for the rest and jump to the spec.)
```
`3 of ~6` (the `~` is honest about adaptivity); live "So far:" constraint accumulation; a
standing **"simpler" exit ramp**. Approval gate ends with a structured picker:
**Approve / Refine / Start over**.

### Moment 3 — Generate + Validate (the scorecard, the signature moment)
```
┌─ atlas ── PHASE 3/4: GENERATE ─────────────────────────────┐
│  Spec written   .taskmaster/docs/prd.md   (2,140 words)    │
│                                                            │
│  VALIDATION ───────────────────────────────────────────    │
│  Grade: GOOD  ▰▰▰▰▰▰▰▰▱▱  49/57 (86%)                      │
│                                                            │
│   ✓ 11 checks passed   structure · testability · metrics   │
│   ⚠ 2 warnings                                             │
│      W1  REQ-007 says "fast" — no measurable threshold     │
│      W2  success metric has no baseline number             │
│   ✓ 0 placeholders     (TBD/TODO/{{...}} scan clean)       │
│                                                            │
│  Gate: GOOD or better required — passed.                   │
│                                                            │
│  Tasks: 14 parsed · 52 subtasks · dependencies mapped      │
│  Complexity: 3 complex · 8 medium · 3 simple               │
└────────────────────────────────────────────────────────────┘
  Fix the 2 warnings (≈1 min) or continue to handoff?
   ▸ Fix warnings, then continue   (recommended)
   ▸ Continue as-is
   ▸ Show me the spec first
```
Grade word + bar + score + percent; the four-grade scale prints with its thresholds the first
time it appears. Warnings are *quoted and located*, never just counted. The placeholder scan is
named explicitly (it's a differentiator).

### Fleet wave dispatch status (Pro, the walk-away view)
```
┌─ atlas fleet ── wave 2 of 3 ──────────────── ▶ running 12m ┐
│  wave 1  ✓ merged     3 tasks · 18m · integration green    │
│  wave 2  ▶ running                                         │
│    claude-1   task 6  API endpoints      ▰▰▰▱  3/4         │
│    codex-1    task 7  UI components      ▰▰▱▱  2/4         │
│    claude-2   task 9  DB migrations      ✓ done — waiting  │
│  wave 3  ○ queued     4 tasks · starts when wave 2 merges  │
│                                                            │
│  Gate: a wave merges only after the checker approves it    │
│        and the integration branch builds green.            │
│                                                            │
│  watch:  atlas fleet status        logs: .atlas-ai/fleet/  │
└────────────────────────────────────────────────────────────┘
```
Workers named by model + index (`claude-1`, `codex-1`) — the model-agnostic story is visible in
the UI. Never "phoenix" in user-facing output. The gate is restated in plain English on every
render — the trust line that justifies "walk away".

---

## 2. The paywall / upgrade moment

### Anti-dark-pattern contract
1. Fleet appears once per handoff, in the mode list, never as an interstitial.
2. The recommended free mode is the default selection. Fleet is never default.
3. Price is inline at the lock — no "find out" click.
4. The teaser shows a personalized projection computed from this project's real task graph
   (wave count, time estimate), labelled an estimate.
5. Selecting Fleet while locked = one informative response + immediate re-prompt with free
   modes. Never re-teased in the same session.
6. The free path is never degraded to make Fleet look better, and the copy says so.

### Locked handoff screen
```
┌─ atlas ── PHASE 4/4: HANDOFF ──────────────────────────────┐
│  Spec: GOOD (86%) · 14 tasks · 52 subtasks                 │
│                                                            │
│  How should these tasks get executed?                      │
│                                                            │
│  ▸ Verified Loop                          ✓ recommended    │
│    One session works the graph task-by-task. Every task    │
│    must show execution evidence before it counts as done.  │
│    Est. ~6h 30m supervised-ish.                            │
│                                                            │
│    Auto-Execute        TaskMaster's native loop — faster,  │
│                        lighter verification.               │
│    Plan & Drive        Get the plan, implement it yourself.│
│                                                            │
│  ──────────────────────────────────────────────────────    │
│    Atlas Fleet                              🔒 Pro $29/mo  │
│    Your 14 tasks split into 3 parallel waves across        │
│    isolated worktrees (claude ×2, codex ×1), checker-      │
│    gated merges, one final PR.                             │
│    Est. ~2h 05m wall-clock, walk-away.   (estimate from    │
│    your dependency graph — actual time varies)             │
│    Unlock: atlas-ai.au/pro — resumes this exact handoff.   │
└────────────────────────────────────────────────────────────┘
```
Free mode's estimate is stated first so the comparison is symmetric. Lock = `🔒` + "Pro" + price,
visually separated below a rule. The honesty parenthetical is mandatory copy.

**Selecting Fleet while locked:**
```
  Atlas Fleet is part of Atlas Pro ($29/mo).
  What you'd get on this project: 3 waves · 3 parallel workers
  · checker-gated merges · est. ~2h 05m instead of ~6h 30m.
  Unlock at atlas-ai.au/pro — your spec and tasks are saved,
  and the installer resumes this handoff.

  Meanwhile, everything below is free forever:
   ▸ Verified Loop   ✓ recommended
   ▸ Auto-Execute
   ▸ Plan & Drive
```

### Unlocked state
```
│  ▸ Atlas Fleet                     ★ Pro · ✓ recommended   │
│    3 waves · claude ×2, codex ×1 · est. ~2h 05m            │
│    License: ✓ active (renews 2026-07-11)                   │
```
Once licensed, Fleet *becomes* the recommendation when the graph parallelizes (≥2 independent
chains). If the graph is serial, Fleet is **not** recommended and says why — recommending against
the paid feature when it's wrong is the cheapest trust you'll ever buy.

---

## 3. GitHub README storefront

| # | Section | Contents |
|---|---------|----------|
| 1 | Hero | H1 tagline, value prop, badges (stars · MIT · works-with Claude/Codex/Gemini) |
| 2 | Animated demo | One GIF/asciinema ≤45s above the fold: goal → scorecard → handoff → fleet |
| 3 | How it works | `goal → discovery → graded PRD → task graph → verified execution` + 4 one-liners |
| 4 | Quickstart | Two install paths, 90s to first run |
| 5 | What "verified" means | evidence gates, placeholder scan, grades, scorecard screenshot |
| 6 | Free vs Pro table | (below) |
| 7 | Atlas Fleet (Pro) | 1 paragraph + fleet screenshot + /pro link |
| 8 | Social proof | star history, "508+ developers", quotes when available |
| 9 | FAQ | free forever? open vs closed? need TaskMaster? which models? |
| 10 | Contributing / License | MIT restated; "engine will always be MIT" |

**Hero copy:**
> # Turn any goal into shipped code.
> **prd-taskmaster** by [Atlas AI](https://atlas-ai.au) is an open-source engine for Claude Code
> that takes a one-line goal, interviews you like a senior PM, writes a **graded,
> placeholder-proof PRD**, compiles it into a **dependency-ordered task graph**, and executes
> every task with **verification evidence** — so "done" means proven, not claimed.
>
> Free and MIT, forever. Works with Claude, Codex, and Gemini.
> ```
> Grade: GOOD  ▰▰▰▰▰▰▰▰▱▱  49/57 (86%) · 0 placeholders · 14 tasks parsed
> ```

**Free vs Atlas Pro:**
| | Free (MIT) | Atlas Pro — $29/mo |
|---|:---:|:---:|
| Discovery interview (adaptive) | ✓ | ✓ |
| Graded PRD validation + placeholder scan | ✓ | ✓ |
| Dependency-ordered task graph (TaskMaster) | ✓ | ✓ |
| Verified solo execution — evidence per task | ✓ | ✓ |
| Model-agnostic: Claude / Codex / Gemini | ✓ | ✓ |
| **Atlas Fleet** — parallel waves, checker-gated merges, one final PR | — | ✓ |
| Browser-verification MCP | — | ✓ |
| Secrets-vault MCP | — | ✓ |
| License & priority support | community | ✓ |

> The engine is the whole engine — the free tier is not a demo. Pro adds the fleet orchestrator
> and bundled MCPs. [Get Atlas Pro →](https://atlas-ai.au/pro)

---

## 4. Pricing page — atlas-ai.au/pro

Single column, dev-tool register. One tier, one CTA.
```
            Ship the whole task graph at once.
   The prd-taskmaster engine is free and MIT, forever.
   Atlas Pro adds the fleet that executes it in parallel.

  ┌───────────────── ATLAS PRO ─────────────────┐
  │   $29 / month per developer                 │
  │   14-day refund, cancel anytime             │
  │   Everything in Free, plus:                 │
  │   ✓ Atlas Fleet — parallel multi-session    │
  │     execution across Claude, Codex, Gemini  │
  │   ✓ Browser-verification MCP                │
  │   ✓ Secrets-vault MCP                       │
  │   ✓ License key + priority support          │
  │   [ Get your license key ]                  │
  │   then: curl …/install-pro | bash           │
  └─────────────────────────────────────────────┘

  WHAT'S OPEN, WHAT'S NOT
  Open (MIT, free forever): discovery, PRD validation, task graph,
  solo verified execution. 508★ on GitHub — read every line.
  Closed (Pro): atlas-launcher fleet orchestrator + bundled MCPs.
  Your code never touches our servers — the fleet runs entirely on
  your machine; the license key is the only thing that phones home.

  FAQ
  ▸ Will the free engine stay free?  Yes — MIT, and the engine repo
    will never require a key. In writing.
  ▸ What happens if I cancel?  Fleet locks again; everything free
    keeps working. Your specs/tasks are plain files in your repo —
    nothing is held hostage.
  ▸ Does it need my API keys?  It uses the model CLIs you already
    have. No new keys.
  ▸ Team licenses?  pro@atlas-ai.au (volume from 5).
```
Checkout → Stripe → success page shows the license key **and** the install one-liner together.

---

## 5. Onboarding & install UX

### Free — `curl | bash`
```
$ curl -fsSL https://atlas-ai.au/install | bash
  atlas — turn any goal into shipped code
  ✓ Claude Code detected (v2.4)
  ✓ Plugin installed: prd-taskmaster
  ▸ Peer dependency: task-master-ai … not found
    installing (npm install -g task-master-ai) … ✓ 12s
  ✓ Self-test: skill resolves, script.py preflight OK
  Done in 24s.
  ┌─ first run ───────────────────────────────────┐
  │ Open any project in Claude Code and type:     │
  │   /atlas                                      │
  │ …or just say "I want to build <anything>".    │
  └───────────────────────────────────────────────┘
```
Failure states each name the problem, give ONE copy-pasteable fix, and exit nonzero.

### Paid — license-key installer
```
$ curl -fsSL https://get.atlas-ai.au | bash -s -- --key ATLAS-7Q2M-XXXX-XXXX
  atlas pro installer
  ✓ License valid — seat: hayden@…, renews 2026-07-11
  ✓ Free engine present (prd-taskmaster)
  ✓ Installed: atlas-launcher (fleet orchestrator)
  ✓ Installed MCPs: atlas-browser · atlas-vault
  ✓ tmux 3.4 detected (Fleet requirement)
  ▸ Fleet self-test: spawning throwaway worker … ✓ killed clean, 4s
  Atlas Pro is active.
  Fleet now appears in every /atlas handoff — and you have a
  handoff waiting in ~/projects/myapp (14 tasks, 3 waves).
  Resume it: open that project and type /atlas
```
Offline grace: validates online at install + re-checks weekly with a **14-day offline grace**;
degraded state prints once per session, never blocks mid-run; never kill a running fleet over a
license check.

---

## 6. Canonical vocabulary (resolves the live naming collision)

| Concept | Canonical name | Kills / demotes |
|---|---|---|
| Brand / company | **Atlas AI** (atlas-ai.au) | — |
| Public repo | **prd-taskmaster** (keep — 508★ + SEO) | — |
| Free product / plugin / npm | **prd-taskmaster** ("the engine") | `atlas-go` |
| User command | **`/atlas`** (alias of the orchestrator skill) | `/prd-taskmaster-v2` user-facing |
| Subscription | **Atlas Pro** ($29/mo) | "premium tier" |
| Flagship paid feature | **Atlas Fleet** | "Atlas-Auto", "atlas-loop", **"Mode D"** user-facing |
| Pipeline phases | **Preflight → Discovery → Generate → Handoff** (1/4…4/4) | — |
| Execution modes | **Verified Loop** (=C, recommended free) · **Auto-Execute** (=B) · **Plan & Drive** (=A) · **Atlas Fleet** (=D, Pro) | letters survive only in code/tests |
| External tools | **"Use another tool…"** single sub-option | a ten-option flat list |
| Manual path | a *flag* ("manual"), not a mode | "Mode M" |
| Fleet units | **worker** (a session), **wave** (parallel batch), **checker** (gate agent) | "phoenix" |
| Quality output | **grade**, **gate**, **evidence** | raw JSON gate dumps |

Rules: one URL per intent — every upgrade path points to `atlas-ai.au/pro` (the
`#waitlist` anchor dies). "Mode D" never reaches a user's eyes. The vocabulary users must learn
is exactly seven words: *goal, discovery, spec, grade, tasks, handoff, fleet*.

---

## 7. Visual / brand direction (terminal + markdown)

| Symbol | Meaning | ASCII fallback |
|---|---|---|
| `✓` | done / passed | `[ok]` |
| `✗` | blocked / failed (blockers only) | `[x]` |
| `⚠` | warning, non-blocking | `[!]` |
| `○` | optional / not present / queued | `[ ]` |
| `▶` | running now | `[>]` |
| `▸` | selectable option / next action | `>` |
| `▰▱` | progress bar | `[###-]` |
| `🔒` | Pro-locked (the only emoji in terminal output) | `[PRO]` |
| `★` | Pro-active / recommendation accent | `*` |

No other emoji in terminal output. Color (green/yellow/red) only reinforces ✓/⚠/✗; respect
`NO_COLOR`; every screen reads in monochrome. Light box-drawing for phase frames only, ≤64 cols
inside. Tone: calm, factual, first-person-tool, zero exclamation marks in the terminal; the
README may be warmer, the pricing page plainspoken-bold. Accessibility: every state = symbol +
word; progress bars carry numerals; links printed as full URLs.

---

## 8. Prioritized UX gaps the redesign fixes

**P0 — blocks selling**
1. **Naming chaos** across live surfaces (prd-taskmaster / atlas-go / Atlas-Auto / Mode D / two
   waitlist URLs). → §6 vocabulary + single `/pro` URL.
2. **Storefront sells the wrong product** — the live README describes the v1 question-asker; none
   of the v2/v4 engine is visible to the 508★ audience. Highest-leverage fix. → §3 replacement.
3. **Dead-end paywall** — the Mode D teaser ends at "watch the repo"; must become a purchasable
   path that resumes the handoff. → §2 + installer resume.

**P1 — damages first-run trust**
4. **Handoff gate fails on first entry by design** (gate demands evidence HANDOFF produces). Fix
   before launch; UI must never print gate JSON.
5. **Contradictory mode-recommendation logic** in two shipped docs. One source of truth.
6. **Choice overload** at handoff (up to 11 flat options). → 3 free names + 1 locked Fleet +
   collapsed "use another tool…".
7. **Illegible validation output** (grades with no scale, warnings counted not quoted, JSON
   gates). → §1 Moment 3 scorecard.

**P2 — polish / conversion friction**
8. **Three competing install paths** with no canonical. → curl one-liner primary, marketplace
   secondary; git-clone path deleted from README.
9. **Unspecified failure states** surface as raw tool errors. → fixed `✗ + Fix:` grammar.
10. **Inconsistent output register** (v1 emoji-heavy vs v2 minimal). → §7 symbol system.

**P3 — nice to have**
11. Debrief scaffold noise leaks an internal ritual into customer projects — make it opt-in/silent
    outside the dev repo.
12. No documented `atlas fleet status` re-entry command — the walk-away promise needs a
    walk-back-in command.
