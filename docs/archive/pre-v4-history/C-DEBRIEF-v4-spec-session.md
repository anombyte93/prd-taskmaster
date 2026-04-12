# DEBRIEF: prd-taskmaster v4 Spec Session

**Date:** 2026-04-08
**Session:** discord-fleet-p1-continue
**Duration:** ~2 hours of deep research + architecture

## What Was Done

### Complete v4 Spec Generated at `docs/v4-spec.md`

An 882-line comprehensive product spec for prd-taskmaster v4.0 ("The TaskMaster On-Ramp") was created through:

1. **20-item audit** of the existing v3 codebase — identified fundamental flaws, broken features, and 10x improvements
2. **40+ Perplexity research queries** across: viral growth patterns, competitor landscape, onboarding UX, PRD backlash, zero-config feasibility
3. **5 sub-agents dispatched:**
   - Contrarian Agent #1 (3 attempts, 2 failed due to 529 overload, discussed in context)
   - Contrarian Agent: "Why this WON'T go viral" — delivered devastating 7-risk report
   - Agent B: TaskMaster source code analysis — confirmed zero-config is feasible
   - Dangling: kill the onboarding dream — found Commons Clause legal risk + competitor intel
   - (1 additional priming agent)
4. **GitHub Traffic API data pulled** — CRITICAL finding:
   - 220 unique cloners in 14 days
   - 1,013 unique visitors
   - 595 from Google organic
   - 185 from Reddit
   - 64 from ChatGPT (AI recommending the tool!)
   - Stars accelerating: 9→6→13→46→44→54/month
5. **Skill Forge audit** completed (forge score: 90, full mode)

### Spec Covers

- Architecture: Core (free) + Composed Addons (premium)
- 4 Execution Modes: A/B/C free + Atlas-Auto (D) premium
- Premium Features: /question, /cdd, /ralph-loop, /atlas-user-test, doubt pipeline, RAG, MOLL-E, Insight Mode
- Zero-Config: confirmed from TaskMaster v0.43.1 source (Anthropic + Perplexity first-class providers)
- Onboarding: anti-wizard, zero questions on first run, post-value "Capabilities Unlocked"
- Telemetry: opt-in, GDPR, anonymous, Homebrew pattern
- RAG Pattern Library: hosted (Atlas AI Qdrant) + BYO vector DB
- Website: atlas-ai.au complete rewrite with Google Stitch
- Stripe: $29/month Atlas-Auto, license key flow
- Legal: Commons Clause mitigation (free tier = TaskMaster funnel, premium = independent methodology)
- Contrarian mitigations for all 7 identified risks
- Growth sequencing: free v4 first → grow 10x → launch premium

### STILL NEEDS TO BE ADDED TO SPEC (session ran out of working directory)

The following were researched but NOT yet written into v4-spec.md:

1. **Value props with market proof** — 10 features each with multi-million dollar company comparisons (Devin $10.2B, Notion $10B, Perplexity $9B, Vercel $250M ARR, etc.) and "why ours is different"
2. **MOLL-E: Manager Overseeing Large Language Execution** — Discord bot for fleet management, bidirectional commands, checkpoint approval from phone
3. **Insight Mode** — cross-project learning, pattern promotion to RAG, requires Atlas Infra
4. **Premium Command Bundle** — /atlas-auto, /atlas-research, /atlas-verify, /atlas-insight, /atlas-fleet, /atlas-validate
5. **Atlas Infra early access** — hosted environment subscribers get new features first
6. **Hook for AI prompting** — plugin includes a hook that enhances the AI's behavior
7. **Devin comparison table** — what Devin does vs what Atlas-Auto does (we're architecturally superior, they have better packaging)

The content for items 1-6 is FULLY WRITTEN in this session's context (was about to be inserted when the shell broke). The child session should grab it from the parent's research.

## Key Decisions Made

1. **Strip to core** — PRD generation + validation + TaskMaster setup is the free tier
2. **Compose, don't build** — execution modes compose with existing skills (superpowers, /cdd, /ralph-loop)
3. **Atlas-Auto brand** — premium autonomous mode branded separately, feels exclusive
4. **Zero-config** — auto-detect everything, user provides only their idea
5. **Anti-wizard** — no setup questions on first run, show capabilities AFTER value delivered
6. **Commons Clause safe** — free tier funnels users TO TaskMaster, premium tier is independent methodology
7. **Growth before premium** — ship free v4, grow 10x, THEN launch paid
8. **Plugin format** — convert from skill to plugin for marketplace distribution (dual-path with install.sh)
9. **MOLL-E** — Manager Overseeing Large Language Execution — Discord bot for fleet management
10. **Insight Mode** — cross-project learning, hosted only (requires Atlas Infra)

## What's Next

1. **Add remaining sections to v4-spec.md** (value props, MOLL-E, Insight Mode, premium bundle, Devin comparison)
2. **Run /stepback on the completed spec** — future-proofing gate
3. **Convert spec to TaskMaster tasks** (use prd-taskmaster itself! Dog-food it)
4. **Begin BUILD phase** of skill-forge (SKILL.md + phases + script.py refactor)
5. **Set up Google Stitch** for atlas-ai.au website design
6. **Set up Stripe products** for Atlas-Auto pricing

## Files Created/Modified

- `docs/v4-spec.md` — 882-line product spec (MAIN ARTIFACT)
- `.mcp.json` — Google Stitch MCP config (needs auth setup)
- `/tmp/question-parent-results.json` — research context for agents
- `/tmp/insights/discord-fleet-p1-continue.md` — published insights (3 rounds)
- `/tmp/forge-session-log.json` — skill forge tracking

## Critical Context for Child Session

- The spec file is at `docs/v4-spec.md` — READ IT FIRST
- Google Stitch MCP needs `! npx google-stitch-mcp setup` to authenticate
- The repo was cloned into this directory from `gh repo clone anombyte93/prd-taskmaster`
- The installed skill at `~/.claude/skills/prd-taskmaster/` has DIVERGED from the GitHub repo (422 lines vs 303)
- TaskMaster v0.43.1 source was analyzed at `/usr/lib/node_modules/task-master-ai/dist/`
- Traffic data: 220 cloners/14d, 1013 visitors, stars accelerating
