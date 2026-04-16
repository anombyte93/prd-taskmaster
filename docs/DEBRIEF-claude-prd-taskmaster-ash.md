# Ash Debrief — claude-prd-taskmaster (supervisor session)

**Timestamp**: 2026-04-16T10:43:17Z
**Role**: Supervisor/orchestrator over Claude + Codex phoenix arms during plugin build
**Status at ash**: Live, mid-supervision, 40 iterations in. Parent restarted once for MCP tool deployment. Both managed phoenixes still productive.

---

## What this session was

The parent orchestrator for the `@atlas-ai/prd-taskmaster` + `@atlas-ai/atlas-coin` plugin builds. Ran `/atlas-ralph-loop:ralph-loop --max-iterations 100 --completion-promise SUPERVISOR_COMPLETE` with duties defined in `.claude/supervisor-loop-prompt.md`.

## What it actually did (highest-signal deliverables)

### Capabilities added to the platform
- **atlas_session verifier DSL fix** — `_evaluate_pass_when` now supports bare-substring pass_when (fallback to literal `needle in haystack` with ANSI-strip + trim). Both authoritative + mirror source edited. 81/81 tests pass, 5 regression tests added. Deployed live.
- **atlas_session create_bounty template fix** — atlas-coin API requires `template` ∈ `{ci, test_coverage, github, manual}`. Adapter was sending `soul_purpose`. Changed to `manual` + preserved soul_purpose in description/metadata. Schema now accepts. Settle still blocked on wallet `session-lifecycle` = 0 AC (separate issue).
- **atlas-launcher session_respawn + mcp_reload tools** — new MCP tools at `atlas_launcher/server.py`. `session_respawn(session_name, backend, resume=True, model, ready_timeout)` captures cwd, kills tmux, relaunches with resume flag. `mcp_reload` auto-detects backend. Empirically tested both Claude + Codex preserve context. DEPLOYED post-parent-restart.
- **codex-send.sh** — `/home/anombyte/bin/codex-send.sh SESSION "MSG"` — reliable Codex delivery handling (1) bash variable expansion (literal send-keys), (2) Codex "Working" state Tab-to-queue, (3) post-send fingerprint verification with auto-retry.
- **auto-enter daemon regex extended** — added Codex patterns (`Reviewing approval request`, `Approve?`, `(y/n)`, `[y/N]`, `Allow command`, `Do you trust`, `waiting for approval`) + `SKIP_REGEX` for past-tense approvals. Chezmoi source + target both synced. Self-test flag added.

### Patterns validated in live use
- **Adversarial contract drafting** across 11+ contracts settled. Dominant failure modes caught: bare-substring pass_when (server bug), metachar sandbox rejections (`;`, `[`, `(`, `>=`), template-enum mismatch.
- **Per-arm in-process adversarial drafter** — eliminates cross-session contamination. Codex arm pattern: Darwin → Cicero → Socrates named subagents (deprecated due to 2-5min MCP boot). Evolved to Hayden's **Claude-precision-for-Codex** pattern: Codex spawns dedicated Claude Opus 1M precision session whose only job is `inevitability-auditor` dispatches for criteria drafting. Cross-backend challenge preserved, boot overhead eliminated.
- **Belt-and-suspenders auto-enter** — smart daemon (regex-matched) + spam daemon (blind Enter every 3s) on every managed session. Covers both Claude and Codex UX quirks.
- **Triple-verify parent pings** — codex-send.sh handles delivery fingerprint check + Tab-to-queue during Codex "Working" state.
- **Shell-flag session respawn** — `claude --continue` and `codex resume --last` preserve context across process restart; foundation for the new `session_respawn` tool.
- **Self-handoff at ctx threshold** — gen1 Claude arm self-triggered `/atlas-handoff` at ~65% ctx, wrote `docs/DEBRIEF-gen1.md`, spawned `atlas-prd-plugin-builder-gen2` via tmux-first ordering (auto-enter daemon before Claude process). Zero parent intervention needed. This is the behaviour soul files were supposed to produce.

### Blockers surfaced + partially resolved
- atlas-launcher MCP intermittent disconnects (~3 in ~4hr) — session_respawn is the recovery path, not auto-reconnect (upstream client limitation)
- Sandbox metachar scanner naive — still rejects `;` `[` `(` inside quoted python -c. NOT FIXED. Workaround: drafters emit metachar-free single commands; adversarial drafters instructed to apply rule on every future draft.
- Implementer subagent overconfidence in DONE reports — Claude arm QA debrief flagged, gen2 mandate: pre-flight contract_run_tests inside implementer before returning DONE. NOT propagated to Codex arm yet.
- Bounty wallet `session-lifecycle` = 0 AC → remote settle blocked. NOT FIXED. Both arms operating on `contract_status=active_local` pending wallet top-up.

## Contract tally at ash

**11 contracts settled build-wide:**
- Claude arm: F3.2, F3.3, F3.4, F3.5, F3.6, F4.0, F4.1, F4.2 (gen1) = 8
- Codex arm: P1 (18/18), C1 (15/15), C2 (26/26) = 3

Claude arm gen1 progress at handoff: 15/40 tasks (38%). Gen2 picking up at F4.3.
Codex arm: 3 tasks settled in Wave 1 + early Wave 2. Currently on C3 (taskmaster_bridge.py) via precision lane.

## What's intentionally left out of the successor soul

- 40 iterations of tmux captures + inbox ack/read activity (all in `session-context/supervisor-log.md` — archive, not standing rule)
- Specific issue lists from earlier days (sandbox metachar, EDQUOT transient, Codex UX surprises) — these are now documented patterns, not open live issues
- Named-drafter pattern (Darwin/Cicero/Socrates) — superseded by Claude-precision-for-Codex
- Pre-restart MCP drop anxieties — now handled by session_respawn

## What successor must inherit verbatim

See successor soul file. Distilled to the minimum that still preserves correct behavior.

## Git state at ash

Branch `main`, clean-ish — only untracked files are session-context artifacts + this run's docs:
- `.env.example`, `.taskmaster/config.json`, `.taskmaster/docs/prd-backup-*.md`, `.taskmaster/templates/`
- `docs/v4-release/atlas-coin-arm-research-2026-04-16.md`
- `session-context/CLAUDE-soul-purpose.md`, `session-context/supervisor-log.md`

HEAD: `cb3f13e docs: pin atlas-ralph-loop (patched fork) as canonical over base ralph-loop`

## Live managed sessions at ash

| Session | Role | Ctx % | Daemons (smart/spam) |
|---|---|---|---|
| atlas-prd-plugin-builder | gen1 Claude arm (QUIESCENT, soul fulfilled post-handoff) | 54% frozen | 1/1 |
| atlas-prd-plugin-builder-gen2 | gen2 Claude arm (LIVE, on F4.3) | 14% | 1/1 |
| atlas-prd-plugin-builder-coin | Codex arm (LIVE, on C3 research) | compacted | 1/1 |
| atlas-prd-plugin-builder-coin-precision | Codex's Claude precision drafter (LIVE) | ~72-74% | 1/1 |
| prd-taskmaster-adversarial-contract-phoenix | gen1's drafter phoenix (scope-locked to gen1, now archive candidate) | unused | 1/1 |
| precision-agent | parent's own Codex precision (unused this session) | unused | 1/1 |

## Pending tasks at ash

- **#32** — Synthesize combined QA feedback from both arms (Claude arm debrief in, Codex arm debrief in). Not yet written.
- **#23** — Chezmoi secrets scrub egg (out of scope, carried forward)
- **#7** — Manuscript template for chezmoi CLAUDE.md (out of scope, carried forward)
- **#21** — Monitor AtlasLauncher-PersistentPhoenix-Tools-Phoenix to pytest completion (peer session, not my child, but pending)
- **#27** — Auto-approve daemon for gen1 (stale — gen1 is now quiescent)

## Parent notification plan

Hayden is ntfy-only. Will notify on:
- Ash complete + successor egg parked
- Path to successor soul + egg for review
- No auto-hatch per skill rule #5
