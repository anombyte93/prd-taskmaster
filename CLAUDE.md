# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repo **is** the `prd-taskmaster-v2` Claude Code skill — not a consumer of it. When users run `install.sh`, this directory is copied to `~/.claude/skills/prd-taskmaster-v2/` and activated by Claude Code when users say "PRD", "I want to build X", or any goal-driven phrase.

You are working on the **v4 5-phase rewrite** on the `handoff-overhaul` branch — the canonical line. The `master` branch is the obsolete v3 12-step architecture; do not port code from it without checking against the rewrite's intent.

## Critical: branch and worktree layout

This repo has two git worktrees on the same `.git`:

| Worktree | Branch | Status |
|---|---|---|
| `prd-taskmaster-v2` (folder named "v2" but really v3) | `master` | **Stale.** v3 12-step. Kept only for reference / git history. |
| `prd-taskmaster-v2-handoff-overhaul` (this folder) | `handoff-overhaul` | **Canonical.** v4 5-phase. All new work happens here. |

When in doubt, run `git worktree list`. Never commit v4 work to master.

## v4 architecture: 5-phase pipeline

The skill is a thin orchestrator that reads phase files and executes them. SKILL.md defines the gates between phases; each phase's procedure lives in its own file under `phases/`. Trigger phrases live in `SKILL.md`'s YAML frontmatter `description` field — editing when the skill activates means editing that block.

```
Phase 0: SETUP       → phases/SETUP.md      Verify TaskMaster installed, project initialized, AI pipeline works
Phase 1: Preflight   → script.py preflight  Zero-config detection — no setup questions
Phase 2: DISCOVER    → phases/DISCOVER.md   Adaptive brainstorming via superpowers:brainstorming
Phase 3: GENERATE    → phases/GENERATE.md   Spec + validation + parse to tasks (uses TaskMaster native tools)
Phase 4: HANDOFF     → phases/HANDOFF.md    Detect capabilities, recommend ONE execution mode
```

**Phase files are Read explicitly**, not auto-loaded — this is intentional and load-bearing. SKILL.md tells the AI when to `Read phases/X.md` and what gate must pass before proceeding. Don't inline phase content into SKILL.md "for convenience"; the split exists so phases can evolve independently and so Claude doesn't burn context loading phases it won't use.

## What v4 deliberately replaced from v3

These are not refactors-in-waiting — they were ripped out on purpose:

- **12-step linear workflow** → 5 phases with explicit gates
- **Custom Python task classification** (`_classify_task`, `_ai_classify_tasks`, `_get_ai_model_config`, `enrich-tasks`, `detect-providers`, `_generate_acceptance_criteria`) → **TaskMaster's native `analyze-complexity` and `expand_task`**. If you find yourself reinventing complexity scoring or subtask generation in `script.py`, stop — call TaskMaster.
- **API-key-required providers as default** → `claude-code` provider is default (zero API key for Claude Max users)
- **Custom provider detection** → `detect-capabilities` (a single subcommand that scans for skills/tools/plugins)
- **Four-equal-choices handoff menu** → HANDOFF recommends **ONE** mode based on detected capabilities

If a v3 pattern shows up in a PR, the bar to bring it back is "TaskMaster genuinely cannot do this," not "the old code did it."

## The codification pattern (preserved from v3)

Strict split — preserve when editing:

- **`SKILL.md`** — AI judgment only. Phase gates, when to ask vs proceed, what counts as "ready". No file I/O, no calculations.
- **`script.py`** — All deterministic operations. **Every subcommand outputs JSON on stdout** so SKILL.md can parse it predictably.
- **`phases/*.md`** — Procedural recipes the AI follows once SKILL.md tells it to Read them. These contain decision trees, prompt templates, tool-call sequences.

If an operation doesn't require AI interpretation, it belongs in `script.py`. If it does, it belongs in a phase file. SKILL.md should stay short — it's the index, not the content.

Run `python3 script.py --help` for the current subcommand list. Note: `calc-tasks` is context-aware — it accepts `--team-size`, `--scope-phase` (greenfield/brownfield/final_phase), and `--thematic-groups` alongside `--requirements`. Phase files pass these; don't call it with just `--requirements` unless you've already gathered the context upstream.

## Companion skills

`companion-skills/expand-tasks/` ships alongside the main skill (same SKILL.md + script.py codification). It reads `tasks.json` and launches parallel Perplexity research agents per task. Use after PRD parsing, before implementation.

## Testing

Tests in `tests/` were originally written against v3 and ported into v4. **Critical convention** (from `tests/conftest.py`): fixtures create REAL files in temp directories — there is no mocking. Tests invoke `script.py` as a real subprocess and parse its JSON output. Preserve this; mocks would invalidate the JSON contract being tested.

Test files split into two groups: **script-contract** (`test_script.py`, `test_contract.py`, `test_install.py`, `test_expand_tasks.py`, `test_edge_cases.py`) — pin subcommand JSON shapes and should stay green through v4 changes; **workflow-shape** (`test_user_e2e.py`, `test_critical_paths.py`) — were written against the v3 12-step flow and partially ported. Run the full suite before editing either group; don't assume a failing workflow test means broken code without checking the assertion against the 5-phase intent.

```bash
pytest                                       # Full suite
pytest tests/test_script.py                  # One file
pytest tests/test_script.py::test_name -v    # One test
pytest -k "validate_prd"                     # By keyword
pytest --collect-only -q                     # Discovery only (sanity check)
```

## Running script.py directly

```bash
python3 script.py <subcommand> [args]        # Every command emits JSON
python3 script.py preflight                  # Detect environment state
python3 script.py validate-prd --input .taskmaster/docs/prd.md
python3 script.py detect-capabilities        # Scan for skills/tools/plugins
```

Pipe through `jq` when debugging — never add human-readable output that would break the SKILL.md parsing contract.

## Install / update flow

`install.sh` is the public entry point (`curl | bash`). It clones/updates into `~/.claude/skills/prd-taskmaster-v2/` and supports `--check-update`. The script writes all status output to **stderr** (not stdout) so it remains visible when invoked via a pipe — preserve this when editing logging.

When changing install behavior, update `tests/test_install.py` in the same change.

## Editing guidelines specific to this repo

- **Templates in `templates/`** are user-facing output. `CLAUDE.md.template` is the file the skill *generates for downstream projects*; do not confuse it with this CLAUDE.md.
- **`reference/`** (`taskmaster-integration-guide.md`, `validation-checklist.md`) is read at runtime by phase files. Edits here change skill behavior.
- **13 validation checks** in `script.py validate-prd` are the quality bar. Adding/modifying a check requires updating `reference/validation-checklist.md` to match.
- **Placeholder detection** (mustache `{{}}`, TBD, TODO patterns) is enforced by `validate-prd` and is intentional — generated PRDs that contain template literals should fail. Don't loosen this.
- **USER-TEST checkpoint cadence** (every N tasks, configured via `gen-test-tasks --total`) is load-bearing for execution modes downstream. Don't remove without checking what consumes it.

## Provider default and why

`claude-code` is the default provider. This is deliberate: Claude Max users have no API key, and v3's default of requiring an API key broke first-run for most users. If you add a new provider, do not make it the default unless it has the same zero-config story.

## Pipeline context

This skill sits in a larger Atlas pipeline:

```
atlas-start → prd-taskmaster-v2 → atlas-plan → atlas-loop → atlas-sync
```

It also works standalone — input is any goal, output is `prd.md` + `tasks.json` in `.taskmaster/`. When editing handoff behavior, remember both consumers exist: the next pipeline stage (atlas-plan) and a human running the skill on its own.

## Session-context convention

`session-context/` is gitignored working state for Claude sessions on this repo. Not part of the shipped skill — don't include it in `install.sh`.
