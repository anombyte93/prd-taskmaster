# v4 Ship Readiness — Discovery Notes

Captured 2026-04-13 during autonomous dogfood run of `/prd-taskmaster-v2` on itself.

## The Goal (from user's /pentest-wtf args)

> "continue until all work is complete and the front facing version is actually decent, then we can properly test the v4 that we want to release, when we are happy and compare it to the v3 version getting lots of upvotes, and we are SURE v4 is better than it BY FAR, like ITS WAY BETTER, then you can actually complete it."

Translated to product terms: **Ship prd-taskmaster v4 to a state where it is unambiguously better than v3 along every axis a v3 user cares about, and has at least one "wow" capability v3 cannot match.**

## Who uses this?

- **Primary audience:** Claude Code users who want AI-generated PRDs → tasks
- **Secondary:** Users of other AI coding tools (Codex, Cursor) who can adapt the PRD
- **Constraint:** v4 is the FREE tier. Atlas pipeline (atlas-plan, atlas-go, atlas-loop) is paid/premium. v4 must work standalone without Atlas skills installed.

## What does v3 do well (must preserve)?

Based on v3 README (the version currently getting upvotes on GitHub):

1. **Single curl install** — low friction entry
2. **Comprehensive PRD template** — 12 sections, engineer-focused
3. **13 automated quality checks** with letter grade
4. **TaskMaster integration** (MCP + CLI fallback)
5. **12+ structured discovery questions** — people feel guided
6. **Auto-resume after crash** — no work lost
7. **Four execution modes** after PRD generated (sequential, parallel, full auto, manual)
8. **USER-TEST checkpoints** every 5 tasks
9. **Tracking scripts** (time, rollback, accuracy, security audit, state)
10. **Generates CLAUDE.md for downstream projects** — TDD workflow guide

Users upvote v3 for these. v4 must not regress any of them.

## What does v4 do that v3 doesn't (differentiators)?

1. **Zero-config** — no setup questions, no API keys for Claude Max users
2. **5 phases with explicit gates** — cleaner mental model than 12 linear steps
3. **TaskMaster native** — `analyze-complexity` and `expand_task` instead of custom classification
4. **Adaptive brainstorming** via superpowers:brainstorming — one question at a time, branching
5. **Domain-agnostic** — works for software, pentest, business, learning, not just web/API
6. **Single mode recommendation** in handoff — not 4 equal choices
7. **Codification pattern** — SKILL.md (judgment) / phases/*.md (recipes) / script.py (mechanics)
8. **Free/premium mode split** — Mode C (free, ralph-loop) vs Mode D (premium, atlas)

## Ship-blocker gaps discovered during this dogfood run

**Must fix before v4 can ship:**

1. **SETUP.md docs `--set-main claude-code`** — wrong syntax. Correct is `--set-main sonnet --claude-code`. First-run users get a cryptic error and bounce.
2. **script.py `_detect_taskmaster_method`** — checks for `task-master-ai` (MCP binary) and `taskmaster` (shell alias, not a real binary). Misses the actual CLI binary `task-master`. Preflight can report `method: "cli"` when the real CLI isn't available.
3. **script.py `cmd_init_taskmaster`** — uses `shutil.which("taskmaster")` which returns None (alias). Even if it found the binary, it calls `["taskmaster", "init", ...]` instead of `["task-master", "init", ...]`. The init subcommand is broken.
4. **Preflight decision table missing row**: `prd_path exists + task_count == 0`. Ambiguous state — user with an empty or stale PRD doesn't get a clear path.
5. **DISCOVER.md has no autonomous-mode path**. If the skill is invoked by a script or in auto-approval mode, it blocks forever waiting for user input.
6. **Mode D capability detection mismatch.** HANDOFF.md says Mode D requires `atlas-loop + atlas-cdd`. script.py's `cmd_detect_capabilities` triggers Mode D on `cdd + ralph-loop`, neither of which is Atlas premium. So free users with the `cdd` skill get misrouted into "premium" recommendation.
7. **Stale v3 PRD at `.taskmaster/docs/prd.md` in this repo** was never cleaned up. Will confuse any future dogfood run. (Fixed mid-run by backup.)
8. **README positioning wrong for free tier.** Current README heavily features "atlas pipeline" as the main context, but v4 is the free standalone. Atlas should be an optional ecosystem callout, not the headline.
9. **`init-taskmaster --method cli` bug** — script calls `task-master init` with flags `--yes --store-tasks-in-git --rules=claude` but we haven't verified these flags work in the current task-master version.
10. **Provider default is claimed as `claude-code`** but this is not what the TaskMaster CLI calls it — users see a model ID of `sonnet` with a `--claude-code` flag. The naming mismatch between "claude-code provider" in our docs and TaskMaster's actual model ID model leaks confusion.

**Should fix before shipping:**

11. **No integration test** that runs a full end-to-end PRD generation on a temp directory to catch regressions like the above.
12. **Phase files reference `~/.claude/skills/prd-taskmaster-v2/`** as an absolute path. If the user installs the skill via `curl | bash` to a different path (e.g., `prd-taskmaster` without `-v2`), every phase file breaks. Should be relative to `$SKILL_DIR`.
13. **Validate-PRD's vague-word list** includes `"simple"` and `"easy"` as always-vague — fires false positives when spec uses those words descriptively ("the UI is simple to use" flagged same as "should be simple").
14. **`calc-tasks` formula is hardcoded** as `ceil(requirements * 1.5) clamped [10, 40]`. The DISCOVER.md scope calibration table says solo=8-12, enterprise=20-30, but calc-tasks doesn't accept a scale parameter.
15. **HANDOFF Step 3 writes to `./CLAUDE.md`** by appending — but there's no dry-run, no backup, and no conflict detection. A user with an existing `CLAUDE.md` gets silent append damage.
16. **No `validate-setup` subcommand.** Users who hit ship-blockers 1-3 have no easy diagnostic path. `script.py validate-setup` should run all setup checks and tell them what's broken.

**Nice to have:**

17. **Template library is thin** — only `comprehensive` and `minimal`. v3 had the same. A `pentest`, `business`, `learning` template would match v4's domain-agnostic claim.
18. **No telemetry/feedback loop** — users hit bugs and never report them. A `/prd-taskmaster-v2 --report-bug` command that opens a pre-filled GitHub issue would close the loop.
19. **README has no comparison table v3→v4**. Users who liked v3 need to see what changes for them on upgrade.
20. **No uninstall script.** v3 has `install.sh`; there's no `uninstall.sh`. When a user wants out, they have to know where files live.

## Constraints captured

- **Tech stack:** Python 3 for script.py, markdown for SKILL.md / phases / templates. No new dependencies.
- **Timeline:** As much as I can complete autonomously overnight (~5.5 hours of auto-approval).
- **Team:** Solo (Claude Opus running autonomously)
- **Budget:** Free tier — claude-code provider only for TaskMaster, no API spend.
- **Integration:** Must not break existing `~/.claude/skills/prd-taskmaster-v2/` installation (user has a live session using it). Dev work happens in this worktree at `prd-taskmaster-v2-handoff-overhaul`.
- **Regulatory:** None.
- **Domain-specific:** This is a skill-building task; v4 must work as both standalone (free tier) and as a stage in the Atlas pipeline (premium tier).

## Scale classification

**Team/startup** — user has a growing user base (v3 has upvotes), treating this like a product release not a hobby project. Task cap 12-20, subtask depth 3-5.

## Approved design

**Self-approved** since user is asleep and explicitly authorized autonomous operation.

**Approach:** Fix the 10 ship-blockers first (critical), then the 6 should-fix items (quality), push to `origin/main`, then leave a handoff document so user can test v4 vs v3 on wake-up.
