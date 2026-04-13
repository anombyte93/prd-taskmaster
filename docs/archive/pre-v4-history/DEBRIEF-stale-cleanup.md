# Debrief: Stale prd-taskmaster Copies — Consolidation to Single Source of Truth

**Session**: prd-tm-v4
**Date**: 2026-04-12
**Authority**: User approval relayed via troubleshooting orchestrator: *"happy for it to cleanup that and just have the single source of truth."*
**Canonical**: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-v2-handoff-overhaul` (branch: `handoff-overhaul`, force-renamed to `master` after cleanup)

## What was found

The orchestrator handshake mentioned "5 stale prd-taskmaster copies." A filesystem-wide audit found **7 stale working copies** outside the canonical worktree, plus a stale `master` worktree of the canonical repo itself. All seven plus the worktree are documented and resolved here.

### Audit results

| Tag | Path | Git state | Disposition |
|---|---|---|---|
| A | `~/Projects/in-progress/prd-taskmaster-skill` | git init, no commits, untracked v3 PRD work + .taskmaster/ | **Harvested + deleted** |
| B | `~/Hermes/Projects/tools/prd-taskmaster` | clean tracked + 11 untracked v3→v4 transition draft .md files | **Harvested + deleted** |
| C | `~/shade_gen/Projects/prd-taskmaster-v2` (lowercase) | not a git repo, 320K of v4 source brainstorm/spec/research docs | **Harvested + deleted** |
| D | `~/Projects/repos/improve-batch/prd-taskmaster` | clean checkout, master @ 717efbf, no local work | **Deleted** |
| E | `~/Hermes/current-projects/prd-taskmaster-v2` | symlink wrapper (`repo -> ~/.claude/skills/prd-taskmaster`) | **Deleted** |
| F | `~/Hermes/Projects/archive/debugging/prd-taskmasterIssue3` | empty directory | **Deleted** |
| G | `~/Atlas/den/prd-taskmaster` | clean checkout, master @ f2437f0, no local work | **Deleted** |
| W | `~/Shade_Gen/Projects/prd-taskmaster-v2` | git worktree of canonical, branch `master` (v3 12-step) | **Removed via `git worktree remove`** |

### Left alone (not stale top-level copies)

- `~/Projects/projects/Deployed - Internal/{redacted-project}/prd-taskmaster` — nested checkout inside a different (private) project's repo, not a stand-alone prd-taskmaster copy.
- `~/.claude/skills/prd-taskmaster-v2/` — live skill install, kept (deployed by `install.sh`).
- `~/.codex/skills/prd-taskmaster-v2/` and `~/.agents/skills/prd-taskmaster-v2/` — alternate-runtime skill installs, kept.
- `~/.claude/archive/skills/prd-taskmaster` — explicit archive, kept.
- `~/.cache/claude-cli-nodejs/...` — Claude CLI session caches, untouched.

## What was harvested

All unique content from A, B, and C was copied into `docs/archive/pre-v4-history/` in the canonical repo, prefixed with the source tag. 16 files preserved:

**From A (v3 PRD source):**
- `A-v3-prd-spec.md` — full v3.0 PRD spec authored before the v4 rewrite

**From B (v3→v4 transition planning):**
- `B-SKILL_UPDATE_DRAFT.md` — major update draft with mandatory MCP/CLI rules, user testing cadence, autonomous execution prompts
- `B-TOP_5_ADDITIONS.md` — proposed additions including real datetime tracking
- `B-IMPLEMENTATION_COMPLETE.md`
- `B-INTEGRATION_PLAN.md`
- `B-USER_EXPERIENCE_EXAMPLE.md`
- `B-CHANGES_SUMMARY.md`
- `B-DEPLOYMENT_SUMMARY.md`

**From C (v4 brainstorm + research history):**
- `C-FINAL-SPEC-v2.md` — final spec doc (not present in canonical before harvest)
- `C-v4-spec-detailed.md` — longer/earlier v4 spec with traction metrics, executive summary, detailed referral data; differs from the trimmed `docs/v4-spec.md` already in canonical
- `C-DEBRIEF-brainstorm.md` — brainstorm session debrief
- `C-DEBRIEF-v4-spec-session.md` — v4 spec session debrief
- `C-RESEARCH-cdd-subagent-sync.md` — research notes on CDD/sub-agent sync
- `C-RESEARCH-writing-plans.md` — research notes on writing-plans pattern
- `C-SESSION-FINDINGS.md`
- `C-PARENT-CONTEXT-DUMP.md`

`docs/v4-spec.md` (the trimmed one already in canonical) was kept as-is; the longer C version is preserved alongside it for diff/history.

## Master branch retirement

After cleanup, the canonical line was force-renamed:

1. `git worktree remove ~/Shade_Gen/Projects/prd-taskmaster-v2` — removed the stale v3 master worktree
2. `git branch -D master` — deleted the obsolete v3 master branch locally
3. `git branch -m handoff-overhaul master` — renamed canonical line to `master`
4. `git push --force-with-lease origin master` — force-pushed (future cloners get the canonical line)
5. `git push origin --delete handoff-overhaul` — removed the now-redundant feature branch on GitHub

The repo is now single-worktree, single-branch, single-source-of-truth.

## Follow-ups (deferred per user)

- **v4 test rewrites** — `tests/test_user_e2e.py` and `tests/test_critical_paths.py` reference the v3 12-step shape and need rewrites for the 5-phase architecture. Filed as a separate issue; not blocking consolidation.

## Verification commands

```bash
# Confirm only one worktree exists
git -C ~/Shade_Gen/Projects/prd-taskmaster-v2-handoff-overhaul worktree list

# Confirm the 7 stale dirs are gone
for d in \
  ~/Projects/in-progress/prd-taskmaster-skill \
  ~/Hermes/Projects/tools/prd-taskmaster \
  ~/shade_gen/Projects/prd-taskmaster-v2 \
  ~/Projects/repos/improve-batch/prd-taskmaster \
  ~/Hermes/current-projects/prd-taskmaster-v2 \
  ~/Hermes/Projects/archive/debugging/prd-taskmasterIssue3 \
  ~/Atlas/den/prd-taskmaster; do
  [ -e "$d" ] && echo "STILL EXISTS: $d" || echo "gone: $d"
done

# Confirm canonical is on master
git -C ~/Shade_Gen/Projects/prd-taskmaster-v2-handoff-overhaul branch --show-current
```
