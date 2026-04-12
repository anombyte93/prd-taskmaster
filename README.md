# prd-taskmaster

> **Goal-to-tasks engine for Claude Code.** Takes any goal, guides discovery, generates a validated PRD, and parses it into TaskMaster tasks — then hands off to execution.

[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://github.com/anombyte93/prd-taskmaster)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/anombyte93/prd-taskmaster/blob/master/LICENSE)
[![Status: Beta](https://img.shields.io/badge/Status-Beta-orange)](https://github.com/anombyte93/prd-taskmaster)
[![v4: Coming Soon](https://img.shields.io/badge/v4-coming_soon-blue)](#-coming-soon-v4-the-5-phase-rewrite)

---

## 🚧 Coming soon: v4 (the 5-phase rewrite)

**This README describes the v4 architecture, which is in active development on the `handoff-overhaul` branch and has not yet been merged to `master`.** What you install today with the curl command below is the stable v3 release (12-step workflow). v4 lands when the `handoff-overhaul` branch is merged — watch the repo for release notes.

**What v4 changes:**
- **Install story rewrite** — v4 ships as a **Claude Code plugin** (primary) and an **npm package** (secondary). The legacy `curl | bash` install stays available as an optional path for people who want it, but it's no longer the recommended way in.
- 5 phases with explicit gates (SETUP → PREFLIGHT → DISCOVER → GENERATE → HANDOFF) instead of v3's 12-step linear workflow
- Zero-config setup — TaskMaster and provider detection are automatic; no API key required for Claude Max users (`claude-code` provider default)
- TaskMaster's native `analyze-complexity` and `expand_task` replace the v3 custom task classification
- Adaptive discovery via `superpowers:brainstorming` (one question at a time) replaces v3's fixed 12+ question script
- Handoff recommends **one** execution mode based on detected capabilities, not four equal choices
- Domain-agnostic — works for software, pentest, business planning, learning plans, anything

**If you want the current stable v3 behaviour**, install with the curl command below and ignore everything below the "5-Phase Pipeline" section until v4 ships. If you want to try v4 early, clone the `handoff-overhaul` branch directly (see [Early access](#early-access-v4-in-development)).

---

## Install

### v4 install paths (when it ships)

v4 will be installable three ways, in recommended order:

**1. Claude Code plugin (recommended)** — installs into Claude Code's native plugin system so activation, updates, and uninstall are managed by the tool you're already using. Command signature (final name TBD when published):

```
/plugin install prd-taskmaster
```

**2. npm package** — if you're already in a Node toolchain, or want lockfile-pinned installs in a project:

```bash
npm install -g @anombyte93/prd-taskmaster
prd-taskmaster install
```

**3. curl | bash (legacy, optional)** — kept around for people who want the old one-liner. Not recommended; no lockfile, no plugin integration, no uninstall story:

```bash
curl -fsSL https://raw.githubusercontent.com/anombyte93/prd-taskmaster/main/install.sh | bash
```

### Stable (v3, shipped today)

Until v4 ships, the stable install path is still curl-pipe-bash:

```bash
curl -fsSL https://raw.githubusercontent.com/anombyte93/prd-taskmaster/master/install.sh | bash
```

Installs the current stable release to `~/.claude/skills/prd-taskmaster/`. Re-run the same command to upgrade.

### Early access (v4, from source)

Want to try v4 before it's released? Clone the development branch directly:

```bash
git clone -b main https://github.com/anombyte93/prd-taskmaster.git \
  ~/.claude/skills/prd-taskmaster-v2
```

This installs v4 alongside the stable v3 at a different skill name (`prd-taskmaster-v2`) so the two don't collide. **No upgrade path guarantees** — v4 may rename, change config shape, or break on you without notice until it's officially released.

---

## How to Use It

1. Install (above).
2. Open Claude Code in any project directory: `claude`
3. Say any of these — the skill auto-activates:
   - `"I want a PRD for adding dark mode"`
   - `"Build me a spec for Stripe integration"`
   - `"PRD for a pentest engagement against example.com"`
4. Answer the discovery questions Claude asks (one at a time — adaptive, not a fixed form).
5. When it finishes you have `.taskmaster/docs/prd.md` and a parsed `tasks.json` in your project, plus **one** specific recommendation for how to execute them.

**You don't invoke `script.py` yourself. You don't pick a workflow mode upfront. You don't set any API keys.** The skill drives the conversation; everything else is auto-detected.

> Not working? Verify `SKILL.md` exists at `~/.claude/skills/prd-taskmaster-v2/SKILL.md` and restart Claude Code.

---

## Standalone by default — works great without anything else

`prd-taskmaster-v2` is a **free, standalone** Claude Code skill. No subscription, no account, no Atlas pipeline, no paid add-ons. Say "I want a PRD for X" in any Claude Code session, answer the discovery questions, get `.taskmaster/docs/prd.md` and `tasks.json`. That's the whole product. Use the output however you want — `task-master next` to begin implementation, hand the PRD to a teammate, feed it into a custom workflow, whatever.

The only hard dependency is `task-master-ai` (install with `npm install -g task-master-ai`), and v4's Phase 0 SETUP gate walks you through it with zero questions. For Claude Max users, the provider chain defaults to `claude-code` (free, no API key).

### Handoff — one recommendation, not four

At Phase 4 HANDOFF the skill scans your environment and recommends **one** execution mode that fits what you actually have installed:

| Mode | Tier | Requires | What it gives you |
|---|---|---|---|
| **A** Plan Only | Free | `superpowers` plugin | `/writing-plans` turns your tasks into a plan, you drive execution |
| **B** TaskMaster Auto-Execute | Free | `task-master-ai` only | `task-master next` → implement → `set-status done` loop |
| **C** Plan + Ralph Loop *(recommended free)* | Free | `superpowers` + `ralph-loop` | `/writing-plans` plan + ralph-loop wraps execution with doubt gates |
| **D** Atlas Loop | Premium | `atlas-loop` + `atlas-cdd` | Tier-S browser verification, `/question` deep research per task, atlas-gamify scoring, walk-away-and-come-back-to-proof |

Most users land on Mode A or Mode C. Mode D only triggers if you explicitly have the `atlas-loop` and `atlas-cdd` skills installed — the skill does not push you toward anything paid.

### Optional: fits into larger pipelines

If you're building with an ecosystem of skills (e.g., the Atlas skill set), `prd-taskmaster-v2` composes at the "goal → tasks" step of a `bootstrap → PRD → plan → execute → wrap up` flow. Nothing in the skill assumes a larger pipeline exists. **`atlas-go`, `atlas-plan`, and `atlas-loop` are separate skills — they're not this one.** If you hear about them and want to know where this skill fits: right before planning, right after bootstrapping a session.

---

## The 5-Phase Pipeline (what happens when you invoke it)

The skill runs 5 phases with explicit gates between each. You only talk to it during Phase 2.

| Phase | Name | What it does | You see |
|---|---|---|---|
| 0 | **SETUP** | Verifies TaskMaster is installed, project initialized, AI provider configured. Defaults to `claude-code` provider — no API key needed for Claude Max users. | Nothing unless something is broken. |
| 1 | **PREFLIGHT** | Auto-detects existing PRDs, crash state, taskmaster install. Zero setup questions. | Nothing unless it finds work-in-progress and needs to ask resume/replace. |
| 2 | **DISCOVER** | Adaptive brainstorming via `superpowers:brainstorming`. One question at a time, branching on your answers. Domain-agnostic (app, pentest, business, learning). | Conversation. |
| 3 | **GENERATE** | Writes `prd.md`, runs 13 validation checks (including placeholder detection for `{{mustache}}`, TBD, TODO), parses into `tasks.json` using TaskMaster's native `analyze-complexity` and `expand_task`. | Summary + validation grade. |
| 4 | **HANDOFF** | Scans your environment with `detect-capabilities`, recommends **one** execution mode that fits what you actually have installed. | One recommendation — not four equal choices. |

**Gate discipline:** the skill won't advance past a phase until that phase's gate is satisfied. If it's stopped, read what it's asking — it's at a gate, not stuck.

**Phase files are Read explicitly at runtime** (see `phases/SETUP.md`, `DISCOVER.md`, `GENERATE.md`, `HANDOFF.md`). Nothing is auto-loaded, so the skill only pays the context cost of phases it actually enters.

---

## What You Get

When the skill finishes, your project has:

```
.taskmaster/
├── docs/
│   └── prd.md          # Validated PRD (13 checks, letter grade)
├── tasks/
│   └── tasks.json      # Parsed tasks with subtasks + complexity
└── ...
```

The PRD covers Executive Summary, Problem Statement, Goals & Metrics, User Stories, Functional Requirements, Technical Considerations, Dependencies, and Out of Scope. Tasks come with complexity estimates and dependency mapping courtesy of TaskMaster's native tooling.

**Quality validation** — 13 automated checks ensure: all required sections present, requirements are testable, success metrics are SMART, architecture is addressed, dependencies are mapped, no placeholder litter. Grade scale: EXCELLENT (91%+), GOOD (83–90%), ACCEPTABLE (75–82%), NEEDS_WORK (<75%). GOOD or better is required to pass Phase 3's gate.

---

## Architecture: the Codification Pattern

The skill enforces a three-way split between **AI judgment**, **procedural recipes**, and **deterministic operations**:

```
SKILL.md (131 lines)     phases/*.md                  script.py (1132 lines)
  The index:             The recipes:                  The mechanics:
  phase gates,           decision trees,               file I/O, JSON output,
  when to Read a phase,  prompt templates,             13 validation checks,
  what counts as "ready" tool-call sequences           TaskMaster calls
```

- **`SKILL.md`** — short by design. Tells Claude which phase file to Read next and what gate must pass before proceeding. No file I/O, no calculations, no inlined phase content.
- **`phases/*.md`** — procedural recipes, Read explicitly at runtime. Inlining them into `SKILL.md` would break the architecture.
- **`script.py`** — every subcommand outputs JSON on stdout so the AI parses it predictably. If an operation doesn't need AI judgment, it lives here.

v4 deliberately removed custom task classification in favour of TaskMaster's native `analyze-complexity` and `expand_task`. If you're tempted to reintroduce custom complexity scoring or subtask generation in `script.py`, the answer is "call TaskMaster instead."

### `script.py` subcommands

| Command | Purpose |
|---|---|
| `preflight` | Detect environment state (existing PRD, crash recovery, taskmaster install) |
| `detect-taskmaster` | Find MCP or CLI installation |
| `detect-capabilities` | Scan for available skills / MCP tools / plugins (drives handoff) |
| `init-taskmaster` | Initialize `.taskmaster/` directory |
| `load-template` | Load PRD template (comprehensive or minimal) |
| `validate-prd` | Run 13 quality checks + placeholder detection, return score and grade |
| `calc-tasks` | Calculate recommended task count from requirements |
| `gen-test-tasks` | Generate USER-TEST checkpoint definitions |
| `gen-scripts` | Create tracking scripts |
| `log-progress` | Record task completion with timing data |
| `backup-prd` | Backup existing PRD before replacement |
| `read-state` | Read crash recovery state |

All commands emit JSON on stdout — pipe through `jq` to debug. Never add human-readable output; it would break the `SKILL.md` parsing contract.

---

## Advanced

### Using with TaskMaster directly

The skill auto-detects and prefers MCP over CLI. Order of preference:

1. **MCP Task-Master-AI** (if installed in Claude Code) — seamless, direct function calls.
2. **CLI** (`task-master-ai` npm package) — fallback.
3. **Blocked with install instructions** if neither is present.

If you want to drive TaskMaster manually after the PRD is generated:

```bash
npm install -g task-master-ai
cd your-project
taskmaster parse-prd --input .taskmaster/docs/prd.md
taskmaster expand-all --research
taskmaster next-task
```

### Customising templates

Templates live in `templates/`:
- `taskmaster-prd-comprehensive.md` — full 12-section PRD (default)
- `taskmaster-prd-minimal.md` — quick template for small features
- `CLAUDE.md.template` — TDD workflow guide written into downstream projects

Edit them in place. The skill reads them at runtime.

### Re-running validation on an existing PRD

```bash
python3 ~/.claude/skills/prd-taskmaster-v2/script.py validate-prd \
  --input .taskmaster/docs/prd.md | jq
```

### Companion skill: `expand-tasks`

`companion-skills/expand-tasks/` ships alongside the main skill and launches parallel Perplexity research agents per task. Run it after PRD parsing, before implementation, to enrich each task with domain research.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Skill doesn't activate when you mention PRD | Check `~/.claude/skills/prd-taskmaster-v2/SKILL.md` exists; restart Claude Code |
| Phase 0 (SETUP) blocks on TaskMaster | Install it: `npm install -g task-master-ai` or install the MCP server |
| Phase 0 blocks on missing provider | If you're on Claude Max, the default `claude-code` provider should work out-of-box. If not, check `~/.taskmasterconfig` |
| PRD validation fails (<75%) | The skill will list which checks failed; re-run Phase 2 with more detail in your answers |
| `script.py` output looks weird | It emits JSON; pipe through `jq`. Never edit it to be human-readable — that breaks the SKILL.md contract |

---

## FAQ

**Do I need TaskMaster?** The generated PRD is useful on its own, but Phase 0 requires TaskMaster so the handoff to execution is meaningful. Install it once; forget about it.

**Does it work for non-software goals?** Yes — v4 is explicitly domain-agnostic. It's been used for pentest engagement specs, business planning, and learning plans.

**How long does it take?** 5–15 minutes depending on how detailed your answers are. Discovery is the only time-consuming phase.

**Can I edit the PRD after generation?** Yes — it's a plain markdown file. Re-run validation if you want to re-check quality.

**What if validation fails?** The skill will tell you which checks failed. You can fix the PRD manually and re-validate, or re-run Phase 2 with more context.

**What's the difference between `prd-taskmaster-v2` and `atlas-prd`?** `atlas-prd` is an older, intermediate version of this same skill that hasn't received the v4 5-phase overhaul. If you have both installed, `prd-taskmaster-v2` is the canonical one.

---

## Contributing

Beta status — feedback from real-world use is the most valuable thing you can send. Open issues or PRs:

- **Issues:** https://github.com/anombyte93/prd-taskmaster/issues
- **PRs:** fork, branch, test against real projects, submit with what/why/how-tested

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines. Tests live in `tests/` — fixtures use real files in temp dirs and invoke `script.py` as a real subprocess. Don't introduce mocks; they invalidate the JSON contract the skill depends on.

Run the full suite:
```bash
pytest
pytest tests/test_script.py                # one file
pytest tests/test_script.py::test_name -v  # one test
```

---

## Version History

- **v4** (in development — `handoff-overhaul` branch, **not yet released**) — 5-phase rewrite
  - Replaced v3's 12-step linear workflow with 5 phases + explicit gates (SETUP, PREFLIGHT, DISCOVER, GENERATE, HANDOFF)
  - Added Phase 0 SETUP to verify TaskMaster + AI provider before anything else
  - Removed custom task classification (`_classify_task`, `enrich-tasks`, `detect-providers`) in favour of TaskMaster's native `analyze-complexity` and `expand_task`
  - Default provider is `claude-code` — zero API key required for Claude Max users
  - Handoff recommends **one** execution mode based on `detect-capabilities`, not four equal choices
  - Discovery via `superpowers:brainstorming` — one question at a time, adaptive, domain-agnostic
  - Phase files (`phases/*.md`) are Read explicitly to minimise context cost
  - Companion skill `expand-tasks/` for parallel Perplexity research per task

- **v3.0** (2025-02-12) — Codification refactor
  - Extracted deterministic operations into `script.py`
  - SKILL.md reduced from 1,343 lines to ~300 lines
  - All script commands output JSON
  - Added `install.sh` with curl one-liner installer

- **v2.0** (2025-02-05) — Feature expansion (datetime tracking, rollback, crash recovery, execution modes, USER-TEST checkpoints, MCP-first detection)

- **v1.0** (2025-01-22) — Initial public release (comprehensive PRD generation, taskmaster integration, automated validation)

---

## License

MIT. Use freely, modify as needed, share improvements if you want.

---

*Planning is 95% of the work. Start with a solid PRD.*
