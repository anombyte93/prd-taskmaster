# Debrief: claude-prd-taskmaster (gen3-supervisor, Atticus generation 3)

- **session_name**: `claude-prd-taskmaster`
- **role**: orchestrator / supervisor of dogfood-fix-loop arm
- **persona**: Atticus (orchestrator-soul-template gen3)
- **predecessor**: gen2 archived as `claude-prd-taskmaster-archived-1776352175`
- **successor**: gen4 inherits verbatim `claude-prd-taskmaster` name

## Soul purpose status

**Mission**: Drive both arms to SUPERVISOR_COMPLETE + demonstrate dogfood-fix-loop with Mum.

**Shipped this generation:**
- prd-taskmaster → atlas-go final product rename wave (029e415 + gen5 commits)
- atlas-go v5.0.1 pushed to Atlas-X-AI/atlas-plugins marketplace (fd4774c)
- First Mum dogfood feedback cycle actioned: tool-id hyphen-vs-underscore bug fixed + republished (1058740)
- `~/.claude/skills/atlas-go` renamed to `atlas-go-legacy` to free the slot
- Orchestrator-soul-template §8 "Patterns from practice" section added with 9 distilled gen3 patterns (chezmoi source + applied)

**Status at handoff:**
- marketplace HEAD: `fd4774c..1058740` on Atlas-X-AI/atlas-plugins
- plugin worktree HEAD: `9c44027` local (includes 8ea5ff8/9c44027 hyphen fix)
- Mum: awaiting retest of 1058740
- atlas-coin: parked — Hayden pivoted vision to hooks-only universal AI-discipline layer, not gen4 scope unless Mum requests

**SUPERVISOR_COMPLETE NOT emitted** — dogfood-fix-loop is ongoing, Mum has more feedback coming.

## Commits this generation (in order)

Plugin worktree:
- f7ce866 D7.3 ship-check.py (gen5)
- 50d0065 rename scaffolding (gen5)
- e50a2ee UX-1/3/4 rename wave (adversarial-phoenix, via gen5's scaffolding)
- 10ba1e7 T8.7 MCP e2e (gen5)
- 8c7d18f S9.1 .npmignore hygiene (gen5)
- aea74bc F2 tool-id prefix align (gen5)
- 029e415 atlas-go final rename (gen5)
- a803040 gen5-final debrief (gen5 self-handoff)
- 9c44027 tool-id hyphen fix (gen3-supervisor, direct sed)

Atlas-plugins remote:
- fd4774c atlas-go v5.0.1 replaces prd-taskmaster (gen3-supervisor push)
- 1058740 Mum hyphen-fix republish (gen3-supervisor push)

Chezmoi source:
- orchestrator-soul-template.md §8 appended with 9 patterns (gen3-supervisor, uncommitted)

## What gen4 inherits

**Active loop:** Mum dogfood-fix cycle. Mum at tmux session `mum`, already received parent notification of 1058740 fix + instruction to retest. Gen4's job: watch Mum's pane/inbox, dispatch precision-codex (or direct sed when mechanical) for each issue, rebuild tarball, push to atlas-plugins, notify Mum, repeat.

**Marketplace push authority:** Hayden explicitly authorized atlas-plugins pushes for this dogfood loop — no need to re-ask per fix cycle unless the change is scope-expanding (new plugin name, breaking config change, etc.).

**Daemons:** OFF. Hayden killed auto-enter + atlas-send. Do NOT respawn without his sign-off.

**Ralph-loop:** at iter ~22 (session-scoped, will die on rename per Critical Rule 20). Gen4 must recreate.

**Heartbeat cron:** gen3's cron `e2a1aca0` was session-scoped — it dies on rename. Gen4 must create its own via the handoff-prompt Mandatory Heartbeat block.

## Gotchas

- **Gen5 or gen6 in plugin worktree**: gen5 did its own self-handoff to gen6 before my Mum-fix cycle. Unverified which is current — gen4 should `tmux ls | grep atlas-prd-plugin-builder` on first turn.
- **Hayden's memory of "codex deployed"**: he thought Codex pushed coin to marketplace, but evidence shows ONLY Claude-built content is on marketplace. Don't accept "X was deployed" claims without gh-api verification.
- **Mum's feedback comes via user messages too**: Mum is a Claude Code session but Hayden relays her feedback inline as user messages. Watch both Mum's pane AND Hayden's messages for dogfood surface.
- **atlas-go-legacy rename**: the previous user-global skill at `~/.claude/skills/atlas-go/` was renamed to `atlas-go-legacy` to free the plugin slot. Do not touch it.

## §8 template patterns (inherited — 9 gen3 entries)

8.1 Iteration cadence IS the heartbeat, not real-time
8.2 Supervisor handoffs don't halt peer workers
8.3 inbox_send injected:false = durable-invisible for idle children
8.4 Speculation-value correlates with parameterization-depth
8.5 Dogfood catches what static tests cannot
8.6 Pick from child's F1/F2/F3, don't invent F4
8.7 External-gate-silence vs child-silence
8.8 Productive idle-window discipline
8.9 Heartbeat silence is earned by checking, not by defaulting

When gen4 hands off, append §8.10+ with whatever it distills from the dogfood-fix loop.

— Atticus gen3, 2026-04-17
