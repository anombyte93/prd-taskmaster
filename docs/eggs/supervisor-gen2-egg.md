# Supervisor Gen2 Egg

**Source ash:** `docs/DEBRIEF-claude-prd-taskmaster-ash.md`
**Source soul:** `docs/eggs/supervisor-gen2-soul.md`
**Wake state:** EGG — do not hatch until Hayden explicitly says so.

---

## Focus order (what to do in this order on hatch)

### Turn 1 — orient
- Read `docs/eggs/supervisor-gen2-soul.md` in full
- Read `docs/DEBRIEF-claude-prd-taskmaster-ash.md` for context
- Skim `.claude/supervisor-loop-prompt.md` for operational rules
- Do NOT re-read the 793-line `session-context/supervisor-log.md` — it's historical

### Turn 2 — verify fleet state
- `mcp__atlas-launcher__session_list()` to see all managed sessions
- `mcp__atlas-launcher__session_status(gen2)` + `(coin)` to confirm backends alive
- Daemon sweep — check smart + spam on all 6 managed
- atlas-coin health: `curl -sf http://localhost:3000/health`
- Inbox: `sqlite3 /home/anombyte/.claude/state/messages.db` for unread to `claude-prd-taskmaster` OR the new session name

### Turn 3 — announce
- Ntfy Hayden: "supervisor-gen2 hatched, fleet state: <summary>, resuming loop"
- Invoke `/atlas-ralph-loop:ralph-loop --max-iterations 100 --completion-promise SUPERVISOR_COMPLETE "See .claude/supervisor-loop-prompt.md"`

### Turn 4+ — normal supervisor loop per supervisor-loop-prompt.md

## Operating rules (reminder)

1. Observation first. Don't act until you understand what the arms are doing.
2. Deep capture (-50 lines) default. Tail -20 misses subagent activity.
3. Jobs Lens: fix-don't-cut. Three proposed fixes + Hayden decides. Deletion = last resort with sign-off.
4. ntfy-only for Hayden. ASCII. No em-dash.
5. Never ash children without sign-off.
6. Never loosen contract criteria to chase broken verifier — fix the verifier.

## Done-when

`SUPERVISOR_COMPLETE` ONLY when BOTH:
1. Claude arm final gen emits `SHIP_CHECK_OK` + `npm publish` succeeds for `@atlas-ai/prd-taskmaster`
2. Codex arm emits `SHIP_CHECK_OK` + `npm publish` succeeds for `@atlas-ai/atlas-coin`

## Hatch instructions (for whoever hatches this egg)

When Hayden says "hatch supervisor-gen2":
```bash
# Spawn via atlas-launcher session_create
# session_name: supervisor-gen2 (or claude-prd-taskmaster-gen2)
# directory: /home/anombyte/Shade_Gen/Projects/prd-taskmaster-v2-handoff-overhaul
# backend: claude
# model: opus
# initial_prompt: "/start — hatch supervisor-gen2 egg. Read docs/eggs/supervisor-gen2-soul.md then docs/eggs/supervisor-gen2-egg.md then execute focus order."
# auto_enter_duration: 6hr
```

Then add smart + spam daemons for the new session.

## What this egg deliberately does NOT auto-do

- Does NOT auto-invoke ralph-loop — hatch turn does that per focus order turn 3
- Does NOT modify the live managed sessions (let them keep going)
- Does NOT ash the current supervisor session — Hayden decides the transition moment
