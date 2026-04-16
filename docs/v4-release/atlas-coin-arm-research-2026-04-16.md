# Atlas-Coin Arm — Research Synthesis (2026-04-16)

Compiled from 3 Explore agents + 10 WebSearches + earlier inevitability-audit findings.
Feeds into the Codex phoenix's ralph-loop-prompt so it inherits the answers.

## Core design question for this arm

> "How do I know what I built — at each moment of action — is what I actually wanted?" (inherited from main plugin)

**Plus the Codex-arm specific question:**

> "Does wrapping the execute-task loop in an atlas-coin economic layer change the AI's work quality?"

The motivational hypothesis: AI agents under loss-aversion pressure (can LOSE coins, not just fail to gain them) produce different quality than AI agents under pure gain-only points.

## What atlas-coin actually is (verified)

- Production-ready TypeScript monorepo at `/home/anombyte/Atlas/den/dual-dev/atlas-coin/`
- HTTP service at `localhost:3000` (configurable via `ATLASCOIN_URL`)
- MCP surface already exposed: `mcp__atlas-session__contract_*` (7 tools)
- SQLite state at `.atlas-coin/atlas.db` — bounties, balances, challenges, claims
- Contract lifecycle: `draft → active → submitted → verified → settled | forfeited`
- Stake mechanic: claimant stakes `escrow * 0.1` on submission — loses it on failed verification
- Verification is DETERMINISTIC (shell / context / file / git checks) — no AI judgment

## Key research findings applied

### From 2026 AI economy research

- **AI reward functions CAN be designed to prevent shirking** (Hadfield & Koh, NBER, 2025-2026) — atlas-coin's deterministic criteria ARE the reward-function layer. No monitoring needed if verification is unfakable.
- **Market making as safety** (arxiv 2511.17621, 2026): "truth-seeking becomes an equilibrium property that emerges from rational agent behavior." atlas-coin's stake mechanic IS market making for task completion.

### From Kahneman loss-aversion applied to AI

- **CRITICAL FINDING**: "In the loss domain, AI has a MARKEDLY STRONGER risk-seeking tendency than humans." (Nature, 2023 + 2024 management study)
- Implication: Codex-with-atlas-coin may over-commit, spam submissions, or take on tasks beyond its capability. Design mitigations:
  - Per-iteration stake cap (max 1 AC staked per iteration)
  - Daily AC budget ceiling (max 50 AC risked per calendar day)
  - Forced cool-down after 2 consecutive forfeits (stepback + research before next stake)
- Contrast: the Claude arm (points-only, no loss) does NOT trigger this risk-seeking bias. That's the motivational-hypothesis test.

### From Codex CLI best practices (OpenAI, 2026)

- gpt-5.4 is the correct model (not gpt-5-codex which fails with ChatGPT-account auth — incident 2026-04-16)
- **Codex can run autonomously for 7+ hours** on hard tasks
- **CRITICAL anti-pattern**: "remove all prompting for the model to communicate an upfront plan, preambles, or other status updates during the rollout" — causes abrupt stops
- **Reasoning effort**: medium for general coding, high/xhigh for hardest tasks
- **Compaction enables multi-hour reasoning** without context limits
- `apply_patch` implementation is a major lever for performance

### From reward-hacking research (2026)

- Deterministic enforcement layers are the 2026 consensus (NIST guidance)
- "Actions should be executed through constrained tools with strict schemas, policy checks, and deterministic validation"
- atlas-coin's `contract_verify` IS the deterministic enforcement layer

### From plugin-to-plugin architecture

- Claude Code plugin system supports nested subagents + hooks + MCP
- Cursor 2.5 (Feb 2026) introduced async subagents that spawn nested subagents
- OpenClaw 2026.3 via npm unifies Claude Code + Codex + Gemini + Cursor via a single gateway
- The "plugin decorating a plugin" pattern (our Option Z) is structurally valid

## Codex-arm architecture decisions

### Package

`@atlas-ai/atlas-coin` — distinct npm package, decorator of `@atlas-ai/prd-taskmaster`

### Integration surface

Layer 3: consumes prd-taskmaster's execute-task loop events via PostToolUse hook. When execute-task fires `set_task_status="done"`:

1. Hook catches the event
2. Creates an atlas-coin contract from the task (contract_draft_criteria → contract_create)
3. Runs the task's testing_plan as criteria (contract_run_tests)
4. Submits with stake (contract_submit, 10% escrow)
5. Verifies (contract_verify)
6. If pass: settle, earn coin, continue
7. If fail: forfeit stake, ROLLBACK task.status to "in-progress", force re-work (with mandatory stepback before retry)

### Worktree + branch

- Dir: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-plugin-coin/`
- Branch: `main` (fresh repo)
- Remote: TBD (org-account decision deferred)

### SHIP_CHECK_OK terminal condition (augmented from main arm)

Same as main arm PLUS:
- All tasks must have settled contracts (no forfeited, no failed_verification)
- Total coins earned >= pre-registered threshold (set at soul time based on task complexity sum)
- atlas-coin service healthy throughout run (contract_health passed every gate)

### Anti-risk-seeking guards (counter the loss-domain bias)

- Max stake per iteration: 1 AC
- Daily stake ceiling: 50 AC
- After 2 consecutive forfeits in same task class → mandatory `/stepback` + `/research-before-coding` + `/question` before ANY new submission
- No retry on same vector (inherited pentest-loop escalation ladder)

## Open questions (surface to Hayden during build)

1. What's the pre-registered coin threshold for SHIP_CHECK_OK? (Depends on task count × complexity; phoenix should calculate on first iteration, write to `.atlas-ai/coin-threshold.json`, surface to parent for approval.)
2. Should contract settlement trigger an inbox_send to parent? (Yes — every coin earned is a progress signal.)
3. Does the atlas-coin service support multiple concurrent clients? (If yes, Claude arm + Codex arm can both settle contracts against the same instance; if not, Codex arm needs isolated atlas-coin deployment.)

## Sources (abbreviated)

[1] OpenAI Developers docs — Using GPT-5.4, Codex best practices
[2] OpenAI Community — "Best Practices for using Codex" 
[3] Nature — Predicting loss aversion with ML methods (2023); Management Science — AI task delegation loss aversion (2024)
[4] Anthropic research on reward hacking; NIST adaptive evaluation guidance
[5] Enderfga/openclaw-claude-code GitHub; Cursor 2.5 async subagents announcement Feb 2026
[6] Yu-Kai Chou gamification studies; "Gamified currencies beyond transaction points" LinkedIn
