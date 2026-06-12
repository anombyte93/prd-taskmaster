# Turn any goal into shipped code.

**prd-taskmaster** by [Atlas AI](https://atlas-ai.au) is an open-source engine for Claude Code
that takes a one-line goal, interviews you like a senior PM, writes a **graded,
placeholder-proof PRD**, compiles it into a **dependency-ordered task graph**, and executes every
task with **verification evidence** — so "done" means proven, not claimed.

Free and MIT, forever.

Atlas has four structural moats:

- **cross-vendor fleet** — Claude, Codex, and Gemini run as separate quota pools instead of one
  brittle model lane.
- **Engine-enforced unfakable gates** — `validate-tasks`, evidence checks, and `SHIP_CHECK_OK`
  make completion a deterministic state, not a claim.
- **persistent vendor-neutral `tasks.json`** — your PRD, task graph, and execution state stay as
  plain repo files that survive vendor swaps.
- **token-economy cost ledger** — every orchestrated model call records routing, exit, latency,
  and escalation so cheap models do cheap work and expensive models justify themselves.

**Atlas speaks TaskMaster natively — but doesn't need it.** Existing TaskMaster projects get a
migration funnel: install `task-master-ai` only when you want the TaskMaster backend, while the
native backend keeps the same validated task graph available without that prerequisite.

```
Grade: GOOD  ▰▰▰▰▰▰▰▰▱▱  49/57 (86%) · 0 placeholders · 14 tasks parsed
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/anombyte93/prd-taskmaster)](https://github.com/anombyte93/prd-taskmaster/stargazers)
[![works with](https://img.shields.io/badge/works_with-Claude%20%C2%B7%20Codex%20%C2%B7%20Gemini-8A2BE2)](https://atlas-ai.au)
[![free engine](https://img.shields.io/badge/engine-MIT%20free%20forever-brightgreen)](#whats-open-whats-not)

---

## How it works

```
goal → discovery interview → graded PRD → dependency-ordered task graph → verified execution
```

1. **Preflight** — detects your environment (native backend, optional TaskMaster backend, model CLIs, research) and configures it. Zero setup questions.
2. **Discovery** — an adaptive, one-question-at-a-time interview captures your real constraints.
3. **Generate** — writes a PRD, scores it against deterministic quality checks (letter grade), then parses it into a task graph with complexity scores and full subtask coverage.
4. **Handoff** — detects what you have installed and recommends one execution mode.
5. **Execute** — a CDD-gated loop implements each task and proves it with evidence, ending in a deterministic `SHIP_CHECK_OK` token.

---

## Quickstart

90 seconds to your first run.

### Path 1 — one-liner (recommended)

```bash
curl -fsSL https://atlas-ai.au/install | bash
# installs the skill + prd_taskmaster package
# TaskMaster install is optional — unlocks the TaskMaster backend
```

### Path 2 — Claude Code plugin

```bash
# add the marketplace, then install the plugin
/plugin marketplace add anombyte93/prd-taskmaster
/plugin install prd-taskmaster

# optional — unlocks the TaskMaster backend
npm install -g task-master-ai
```

### First run

Open any project in Claude Code and type:

```
/atlas      (or /prd-taskmaster, or just say: "I want to build …")
```

Requires Python 3.11+ and Linux / macOS / WSL. The free engine needs **no paid API key** — it
uses the model CLIs you already have, with a local free-research option.

---

## What "verified" means

Most AI coding tools tell you a task is done. This one makes "done" provable:

- **Graded PRDs.** Every spec is scored against deterministic checks (EXCELLENT / GOOD / ACCEPTABLE / NEEDS WORK). Bare placeholders (`TBD`, `{{...}}`, `TODO`) are a hard fail.
- **A real task graph.** Requirements become backend-neutral `tasks.json` tasks with dependencies, complexity scores, and full subtask coverage — not a flat checklist.
- **Evidence-gated execution.** Each task is implemented and must produce execution evidence before it counts as done.
- **A completion token you can trust.** `SHIP_CHECK_OK` is emitted only when every gate passes — and a single non-zero `Exit status` in any evidence file blocks it. It is structurally hard to fake.

```
┌─ atlas ── PHASE 3/4: GENERATE ─────────────────────────────┐
│  Grade: GOOD  ▰▰▰▰▰▰▰▰▱▱  49/57 (86%)                      │
│   ✓ 11 checks passed   structure · testability · metrics   │
│   ⚠ 2 warnings   (quoted + located, not just counted)      │
│   ✓ 0 placeholders     (TBD/TODO/{{...}} scan clean)       │
│  Tasks: 14 parsed · 52 subtasks · dependencies mapped      │
└────────────────────────────────────────────────────────────┘
```

---

## Built for the token-shortage era

Every job runs on the cheapest model that can do it — and escalates only when a validator says
it failed. One setting controls how aggressive that is:

```json
// .atlas-ai/fleet.json
{ "token_economy": "conservative" }   // or "balanced" (default) / "performance"
```

Task decomposition and research run through the selected backend. Native mode works without a
TaskMaster install; installing `task-master-ai >= 0.43.0` unlocks TaskMaster's model-agnostic AI
(any API you configure — Anthropic, OpenAI, Perplexity, Gemini, openai-compatible…) and isolated
workdir expansion when that backend is selected. Complexity 2 scaffolding gets a haiku-class
model; the hardest long-running work gets the frontier model; nothing defaults to expensive.
Local telemetry (`economy-report`) shows your real success-rate and latency per model so the
routing gets smarter on YOUR workload — priors and sources in
[`docs/product/MODEL-ECONOMY.md`](docs/product/MODEL-ECONOMY.md).

## Free vs Atlas Pro

| | Free (MIT) | Atlas Pro — $29/mo |
|---|:---:|:---:|
| Discovery interview (adaptive, one question at a time) | ✓ | ✓ |
| Graded PRD validation + placeholder scan | ✓ | ✓ |
| Dependency-ordered task graph (`tasks.json`) | ✓ | ✓ |
| Verified solo execution — evidence required per task | ✓ | ✓ |
| Model-agnostic: Claude / Codex / Gemini | ✓ | ✓ |
| Parallel research fan-out | ✓ | ✓ |
| **Token economy** — start cheap, escalate only on failure (conservative/balanced/performance) | ✓ | ✓ |
| Optional **TaskMaster backend** expansion — any configured API, isolated workdirs | ✓ | ✓ |
| Local cost telemetry + `economy-report` | ✓ | ✓ |
| Adaptive routing auto-tuning from telemetry | — | ✓ (roadmap) |
| **Atlas Fleet** — parallel waves of isolated workers, checker-gated merges, one final PR | — | ✓ |
| Browser-verification MCP (UI proof, not just logs) | — | ✓ |
| Secrets-vault MCP (keys never in your repo or prompts) | — | ✓ |
| License & priority support | community | ✓ |

The engine is the whole engine — the free tier is **not a demo**. Pro adds the fleet orchestrator
and bundled MCPs. [Get Atlas Pro →](https://atlas-ai.au/pro)

---

## Atlas Fleet (Atlas Pro)

When a build is big enough to want overnight parallelism, **Atlas Fleet** lifts the same engine
from one session to many. It splits your task graph into dependency **waves** of file-disjoint
chunks, spawns model-agnostic workers (Claude / Codex / Gemini) in isolated **git worktrees**,
collects results through a durable inbox rather than trusting an agent's word, and merges waves
sequentially into an integration branch behind a checker gate — never touching `main` until one
final green PR.

It runs entirely on your machine; only the license key phones home. Cancel anytime — your specs
and tasks are plain files in your repo, nothing is held hostage.

[See Atlas Pro →](https://atlas-ai.au/pro)

---

## What's open, what's not

**Open (MIT, free forever):** discovery, PRD validation, the task graph, and solo verified
execution — the entire engine in this repo. Read every line.

**Closed (Atlas Pro):** the `atlas-launcher` fleet orchestrator and the two bundled MCPs
(browser verification, secrets vault). The engine repo will never require a license key.

---

## FAQ

**Will the free engine stay free?** Yes — MIT, and this repo will never require a key.

**What happens if I cancel Pro?** Fleet locks again; everything free keeps working. Your specs
and tasks are plain files in your repo.

**Do I need a paid API key?** No. The engine uses the model CLIs you already have (Claude Code,
Codex, Gemini) and a local free-research option.

**Do I need TaskMaster?** No. Atlas speaks TaskMaster natively but doesn't require it —
Native Mode produces the same validated task graph (validate-tasks + enrich-tasks). Installing
`task-master-ai >= 0.43.0` unlocks the TaskMaster backend: Mode B auto-execute and
native-parallel expansion through TaskMaster's 13-provider model layer.

**Which platforms?** Linux, macOS, and WSL. (Native Windows is not supported — the atomic state
machine uses POSIX file locking.)

---

## Contributing & License

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Product and UX specifications live in
[`docs/product/`](docs/product/).

The engine is **MIT licensed and will always be** — see [LICENSE](LICENSE). Upgrading from v3?
See [CHANGELOG.md](CHANGELOG.md). v3 remains available via `git checkout v3.0.0`.
