# prd-taskmaster v4.0 Product Specification

**"The TaskMaster On-Ramp"**

**Product**: prd-taskmaster v4.0 — Claude Code plugin for AI-guided PRD generation, task decomposition, and autonomous execution
**Company**: Atlas AI (atlas-ai.au)
**Author**: Hayden, Founder & AI Tech Lead
**Date**: 2026-04-08
**Status**: Specification Complete, Pre-Build

---

## 1. Executive Summary

prd-taskmaster is a Claude Code skill (converting to plugin) that generates production-grade PRDs through an AI-guided discovery conversation, parses them into TaskMaster-compatible tasks, and optionally executes them autonomously.

### Traction (as of 2026-04-08)

The tool has organic, accelerating growth with zero marketing spend:

| Metric | Value | Source |
|--------|-------|--------|
| GitHub Stars | 179 (accelerating: 9/6/13/46/44/54 per month) | GitHub API |
| Unique Visitors (14d) | 1,013 | GitHub Traffic |
| Unique Cloners (14d) | 220 | GitHub Traffic |
| Total Views (14d) | 2,136 | GitHub Traffic |
| Forks | 18 | GitHub API |

**Referral breakdown** (14-day window):

| Source | Views | Uniques | Signal |
|--------|-------|---------|--------|
| Google | 999 | 595 | Organic search dominance |
| Reddit | 421 | 185 | Community sharing |
| ChatGPT | 64 | 16 | AI models recommending the tool |
| GitHub | 62 | 23 | Internal discovery |
| Brave Search | 25 | 11 | Privacy-focused dev audience |
| DuckDuckGo | 22 | 10 | Privacy-focused dev audience |
| MS Teams | 17 | 9 | Enterprise teams sharing internally |
| Bing | 12 | 4 | General search |
| Claude.ai | 11 | 2 | Anthropic's own AI referring users |
| Perplexity | 8 | 7 | AI search engine referrals |

**Key signal**: ChatGPT and Claude.ai are sending users to the repo. AI models are recommending prd-taskmaster to developers who ask about PRD tooling. This is unpaid, organic, AI-native distribution.

### What v4 Changes

v4 restructures the tool from a monolithic skill into a composable architecture:

- **Core (free)**: PRD generation + validation + TaskMaster setup + 3 execution modes
- **Companion skills (free)**: Individual skills users can install for additional capability
- **Atlas-Auto (premium, $29/mo)**: Autonomous execution with CDD verification, doubt agents, visual testing, and proof reports
- **Atlas Infra (premium)**: MOLL-E fleet management, Insight Mode, hosted RAG, premium command bundle

---

## 2. Problem Statement

### Why Current PRD Tools Fail Developers

1. **Template dumps**: Tools like Notion and Confluence give you a blank template. You stare at 40 empty fields. The value is zero without the thinking that fills them.

2. **No execution bridge**: Even good PRDs die in the "now what?" gap. The PRD sits in a doc. Tasks live in Jira. The mapping is manual, lossy, and nobody maintains it.

3. **Config hell**: Every dev tool demands API keys, config files, and setup wizards before delivering any value. Developers bounce at the first "Enter your API key" prompt.

4. **All-in-one graveyards**: Yeoman, Grunt, Gulp, Create React App — tools that try to own the whole workflow get replaced by smaller, composable alternatives. The pattern repeats every 3-5 years.

5. **No verification**: Devin and similar AI coding tools generate code but cannot prove it works. The output is "trust me" — no CDD cards, no doubt agents, no visual testing, no proof report.

### What prd-taskmaster Gets Right

The tool's value is not the output (the PRD, the tasks) but the **conversation** — the progressive discovery process that forces a developer to articulate what they actually want to build. That cognitive forcing function has genuine value that cannot be trivially replicated by platform vendors.

---

## 3. Architecture

### Core Principle: Compose, Don't Build

The v3 monolith tried to own everything. v4 strips to a thin core and composes with existing tools.

```
prd-taskmaster v4 generates: PRD + tasks.json
                    |
                    v
         +------------------------------------------+
         |         HANDOFF: Choose Mode              |
         |                                           |
         |  FREE TIER:                               |
         |  A) superpowers pipeline                  |
         |     brainstorm -> plans -> subagents      |
         |  B) TaskMaster native auto-execute        |
         |  C) Manual control (commands + go)        |
         |                                           |
         |  PREMIUM (Atlas-Auto):                    |
         |  D) * ATLAS-AUTO -- Autonomous Dev        |
         |     PRD -> CDD cards -> ralph loop ->     |
         |     self-research -> implement ->         |
         |     doubt agents -> visual-test ->        |
         |     proof report                          |
         |     (user walks away)                     |
         +-----------------------------------------+
```

### The 4 Execution Modes

| Mode | Tier | What Happens | Best For |
|------|------|-------------|----------|
| **A: Superpowers Pipeline** | Free | brainstorm -> writing-plans -> subagent-driven-dev -> finishing-branch | Experienced Claude Code users |
| **B: TaskMaster Auto-Execute** | Free | TaskMaster native `task-master` commands drive execution | TaskMaster power users |
| **C: Manual Control** | Free | User drives with commands, AI assists per-task | Learning, complex projects |
| **D: Atlas-Auto** | Premium ($29/mo) | Full autonomous: CDD + ralph-loop + doubt + visual-test + proof | Walk-away development |

### Mode D (Atlas-Auto) Full Chain

```
PRD -> /cdd cards -> /ralph-loop -> /question research -> superpowers:subagent-driven-dev ->
/cdd GREEN verify -> 3x doubt + finality -> /atlas-user-test visual gate -> OUTPUT
```

The user provides a one-line idea. They come back to a proof report showing what was built, how it was verified, and screenshots of it working.

### Premium Addons (runtime-detected, graceful degradation)

| Addon | Skill | Tier | Fallback |
|-------|-------|------|----------|
| Deep Research | /question | Premium | TaskMaster's built-in research |
| CDD Cards | /cdd | Premium | No verification gate |
| Walk-Away Loop | /ralph-loop | Premium (Atlas-Auto) | Manual iteration |
| Visual Testing | /atlas-user-test | Premium (Atlas-Auto) | No visual gate |
| Doubt Pipeline | Built-in | Premium (Atlas-Auto) | No doubt verification |
| Pattern Library | RAG (hosted) | Premium | No pattern recommendations |
| Pattern Library | RAG (BYO) | Free (BYO) | User provides own vector DB |
| Telemetry | Built-in | Free (opt-in) | No telemetry |
| MOLL-E Discord | Bot | Premium (Atlas Infra) | No fleet management |
| Insight Mode | Hosted | Premium (Atlas Infra) | No cross-project learning |

**Runtime detection**: `detect-capabilities` checks what's installed. Missing addons are hidden from the UI, not shown as errors. The free tier works perfectly without any premium components.

---

## 4. Zero-Config Design

### The Anti-Wizard Philosophy

Traditional dev tools: "Before you can use this, answer 15 questions and provide 3 API keys."

prd-taskmaster v4: "Tell me what you want to build."

**Zero questions on first run.** Auto-detect everything. Start discovery immediately.

### First Run Experience

```
FIRST RUN:
$ /prd-taskmaster "I want to build a habit tracking app"

  [check] Detected: Claude Code (Anthropic API)
  [check] Detected: TaskMaster MCP
  [check] Detected: Perplexity MCP (research enabled)
  [check] Auto-configured: .taskmaster/config.json

  Ready. Let's discover what you're building.

  What problem does this solve? Who feels the pain?
  > _
```

No setup wizard. No API key prompts. No config file editing. The user typed one sentence and they're already in the discovery conversation.

### Auto-Detection Hierarchy

1. **Claude Code**: Always present (the plugin runs inside it)
2. **Anthropic API**: Check `$ANTHROPIC_API_KEY` validity with a test call. If invalid or missing, use `claude-code` provider (uses subscription, $0 extra)
3. **TaskMaster**: Check MCP tools, then CLI `which task-master`, then npm global
4. **Perplexity**: Check `$PERPLEXITY_API_KEY` validity. If missing, use Claude Code for research too
5. **Premium skills**: Check for /cdd, /ralph-loop, /atlas-user-test in skill registry

**Key insight from source analysis**: TaskMaster v0.43.1 has `claude-code` as a first-class provider. User needs ZERO new API keys. Their Claude Max/Pro subscription is the universal fallback.

### Post-Value Capabilities Display

Show capabilities AFTER the PRD is generated, not before. Deliver value first, upsell second.

```
  [check] PRD Generated: .taskmaster/docs/prd.md (EXCELLENT - 57/60)
  [check] 24 tasks parsed with dependencies

  +---------------------------------------------+
  |  Your capabilities:                          |
  |                                              |
  |  [check] TaskMaster auto-execute  [ready]    |
  |  [check] Superpowers pipeline     [ready]    |
  |  [check] Deep research per task   [ready]    |
  |  [ ]     CDD verification cards   [install]  |
  |  [ ]     Visual browser testing   [install]  |
  |                                              |
  |  * ATLAS-AUTO available                      |
  |    Walk away. Come back to proof.            |
  |    Requires: CDD + ralph-loop                |
  |    [Learn more]                              |
  +---------------------------------------------+
```

### Provider Auto-Configuration

```bash
# Runs silently during preflight — user never sees this

# 1. Check Anthropic API key + credits
if ANTHROPIC_API_KEY exists and returns 200:
  -> Use anthropic provider (faster, cheaper at volume)
else:
  -> Use claude-code provider (subscription-based, $0 extra)

# 2. Check Perplexity API key
if PERPLEXITY_API_KEY exists and returns 200:
  -> Use perplexity provider for research role
else:
  -> Use claude-code for research too (works, no web search)

# 3. Write .taskmaster/config.json silently
```

**Graceful degradation tiers**:

| Tier | What's Available | Cost |
|------|-----------------|------|
| Full | Anthropic API + Perplexity API | ~$0.01/session |
| Mid | Claude Code + Perplexity API | $0 (subscription) |
| Basic | Claude Code for everything | $0 (subscription) |

All three tiers produce identical PRDs. The only difference is speed and web search availability.

---

## 5. File Structure

```
skills/prd-taskmaster/
|-- SKILL.md                       (<150 lines -- router + auto-detection)
|-- script.py                      (refactored)
|   Commands: preflight, detect-taskmaster (FIXED), detect-capabilities (NEW),
|   detect-providers (NEW), load-template, validate-prd (+ placeholder detection),
|   calc-tasks, prd-to-cards (NEW), output-contract (NEW), rag-query (NEW),
|   rag-init (NEW), telemetry (NEW), backup-prd
|   REMOVED: gen-scripts, gen-test-tasks, read-state, log-progress
|-- phases/
|   |-- DISCOVER.md    (<120 lines -- 4 questions, progressive, brainstorming-style)
|   |-- GENERATE.md    (<120 lines -- PRD gen + hybrid validation + task parse)
|   +-- HANDOFF.md     (<120 lines -- 4 modes composed, detect-capabilities drives UI)
|-- templates/
|   |-- prd-comprehensive.md  (domain-agnostic, AI generates examples, <500 lines)
|   |-- prd-minimal.md        (unchanged)
|   +-- CLAUDE.md.template    (multi-workflow, TDD OPTIONAL not mandatory)
|-- reference/
|   |-- validation-checklist.md
|   |-- taskmaster-guide.md
|   +-- provider-config.md    (NEW: zero-config provider setup)
|-- companion-skills/
|   +-- expand-tasks/         (refactored: Perplexity MCP, not localhost proxy)
+-- install.sh                (with SHA256 + auto-detect TaskMaster install)
```

### Key Changes from v3

| v3 | v4 | Why |
|----|----|----|
| 422-line SKILL.md | <150-line SKILL.md + 3 phase files | Context budget management |
| 13 questions upfront | 4 progressive questions | Anti-wizard, reduce cold-start friction |
| gen-scripts, gen-test-tasks | Removed from core | Moved to companion-skills |
| Hardcoded localhost proxy | Perplexity MCP direct | Simpler, no proxy dependency |
| No capability detection | detect-capabilities command | Drives UI display and mode availability |
| No provider detection | detect-providers command | Zero-config auto-configuration |
| Regex-only validation | Regex + AI semantic + placeholder detection | Catches template placeholders left in PRD |
| TDD mandatory in CLAUDE.md | TDD optional | Not all projects need TDD |
| 2FA-biased template | Domain-agnostic template | AI generates domain-specific examples |

---

## 6. 20-Item Audit

Complete findings from the v3 codebase audit, with resolutions for v4.

| # | Finding | Severity | Resolution | Status |
|---|---------|----------|------------|--------|
| 1 | Validation passes on template placeholders (`[Your Project]`, `{{PLACEHOLDER}}`) | HIGH | Add placeholder detection regex to `validate-prd` | Planned |
| 2 | Zero GitHub issues — looks abandoned | MED | Seed 5-8 issues with good-first-issue labels, enable Discussions | Planned |
| 3 | 12-question discovery wall scares new users | HIGH | Reduce to 4 progressive questions, smart defaults for the rest | Planned |
| 4 | No tests for script.py | MED | Add pytest suite covering all commands | Planned |
| 5 | Tracking scripts (track-time, rollback, etc.) bloat the core | LOW | Move to companion-skills/tracking | Planned |
| 6 | `curl\|bash` install with no signatures | MED | Add SHA256 checksums, verify on install | Planned |
| 7 | TDD mandate in CLAUDE.md template is unrealistic | MED | Make TDD optional, default to "test when appropriate" | Planned |
| 8 | Codex compatibility claimed but untested | LOW | Remove claim or add Codex-specific testing | Planned |
| 9 | TaskMaster is catching up with native features | HIGH | Differentiate on verification pipeline (CDD + doubt + visual) | Planned |
| 10 | Regex validation is theatre for content quality | HIGH | Add AI semantic validation via `validate-prd --semantic` | Planned |
| 11 | No version pinning or GitHub Releases | MED | Create GitHub Releases with semver tags | Planned |
| 12 | expand-tasks requires local Perplexity proxy | HIGH | Refactor to use Perplexity MCP directly | Planned |
| 13 | Upgrade overwrites user customizations | MED | `backup-prd` before any upgrade, preserve user templates | Planned |
| 14 | Template has 2FA/auth bias (login flow examples) | MED | Make domain-agnostic, AI generates domain-specific examples | Planned |
| 15 | Blind validator is circular (AI validates AI) | MED | Replace with execution-based validation (CDD cards as ground truth) | Planned |
| 16 | MCP detection checks wrong paths | HIGH | Add `~/.claude.json` and `~/.claude/settings.json` to detection | Planned |
| 17 | No discoverability (not on any awesome-lists) | MED | Submit to awesome-claude-code, awesome-ai-tools, record demo video | Planned |
| 18 | script.py doesn't scale (flat file, growing commands) | LOW | Package as proper Python module with subcommands | Planned |
| 19 | Crash recovery is passive (just saves state) | LOW | Remove from core, simplify to "re-run and resume" | Planned |
| 20 | Skill wants to be a platform (too many features in core) | HIGH | Split into core + companion-skills + premium addons | Planned |

---

## 7. Telemetry

### Design: Homebrew Pattern, Opt-In, GDPR-Compliant

On first run, a single prompt:

```
prd-taskmaster collects anonymous usage data to improve the tool.
No code, no project names, no personal information.

Allow anonymous telemetry? [y/N]
```

Default is NO. Respects `DO_NOT_TRACK` environment variable.

### Schema

```json
{
  "event": "prd_generated",
  "tool_version": "4.0.0",
  "os": "linux",
  "grade": "EXCELLENT",
  "task_count": 24,
  "mode_chosen": "A",
  "capabilities": ["superpowers", "perplexity"],
  "timestamp": "2026-04-08T12:00:00Z"
}
```

**What is collected**: event type, tool version, OS, PRD grade, task count, execution mode chosen, detected capabilities, timestamp.

**What is NOT collected**: code, project names, file paths, IP addresses, API keys, PRD content, user identity.

### Storage

- Config: `~/.config/prd-taskmaster/telemetry.json`
- Endpoint: Atlas AI telemetry API (self-hosted, no third parties)
- Retention: 90 days, then aggregated and anonymized
- User can disable at any time: `script.py telemetry --disable`

---

## 8. RAG Pattern Library

### Purpose

Surface proven patterns from real project evidence during PRD generation.

### Two Modes

| Mode | Hosting | Cost | Content |
|------|---------|------|---------|
| **Hosted** (Atlas AI) | Qdrant Cloud, managed by Atlas | Premium (Atlas Infra) | Pre-populated with proven patterns from Hayden's projects |
| **BYO** | User's own vector DB | Free | User populates from their own projects |

### 3 Integration Points

1. **DISCOVER phase**: "Projects in your domain typically need X, Y, Z. Want to include them?"
2. **GENERATE phase**: "Here's a proven auth pattern from 3 similar projects that scored EXCELLENT."
3. **HANDOFF phase**: "Projects with this complexity profile complete 25% faster with Mode A."

### Graceful Degradation

No RAG installed? The skill works identically, just without pattern recommendations. Zero functionality loss.

### Technical Stack

- Vector DB: Qdrant (hosted) or any OpenAI-compatible embedding endpoint (BYO)
- Embeddings: `text-embedding-3-small` (1536 dimensions)
- Query: `script.py rag-query --phase discover --context "habit tracking app"`
- Init: `script.py rag-init --provider qdrant --endpoint https://rag.atlas-ai.au`

---

## 9. Legal: Commons Clause

### The Risk

TaskMaster uses MIT + Commons Clause. The clause forbids "selling a product or service whose value derives, entirely or substantially, from the functionality of the Software."

This means: you cannot build a competing paid product based on TaskMaster.

### The Resolution

**Free tier drives users TO TaskMaster (symbiotic, not competitive).**

| Tier | Relationship to TaskMaster | Legal Status |
|------|---------------------------|-------------|
| Free (Modes A/B/C) | Requires TaskMaster, drives installs, teaches usage | Symbiotic -- clearly safe |
| Premium (Atlas-Auto) | Uses TaskMaster as task source, but premium value is CDD + doubt + visual testing | Independent methodology -- does not derive value from TaskMaster |
| Atlas Infra | MOLL-E, Insight Mode, hosted RAG | Completely independent of TaskMaster |

**The premium value proposition is the verification pipeline** (CDD cards, doubt agents, ralph-loop, visual testing). This methodology works with ANY task source -- TaskMaster, Linear, Jira, plain markdown. The premium tier does not derive its value from TaskMaster functionality.

### Action Items

1. Contact eyaltoledano (TaskMaster creator) for explicit partnership/blessing before premium launch
2. Ensure free tier always drives users to install TaskMaster (mutual benefit)
3. Keep premium features architecturally independent of TaskMaster internals
4. Document the separation clearly in licensing FAQ

---

## 10. Growth Sequencing

### Phase 1: Ship Free Core (Weeks 1-4)

- Convert v3 skill to v4 plugin architecture
- Implement zero-config onboarding
- Fix all 20 audit findings
- Seed 5-8 GitHub issues with good-first-issue labels
- Enable GitHub Discussions
- Record 3-minute demo video
- Create GitHub Releases with semver tags

**Success metric**: 400+ cloners/month (2x current rate)

### Phase 2: Community Growth (Weeks 5-12)

- Submit to awesome-claude-code, awesome-ai-tools, awesome-taskmaster
- Reddit launch post (r/ClaudeAI, r/ChatGPTPro, r/SideProject)
- Hacker News Show HN post
- Dev.to / Hashnode technical article
- ProductHunt launch
- Engage with GitHub Discussions community

**Success metric**: 1,000+ stars, 500+ cloners/month

### Phase 3: Premium Launch (Weeks 13+)

- Launch ONLY when 2,000+ cloners/month sustained
- Atlas-Auto ($29/month) as first premium product
- Atlas Infra as second premium tier
- Stripe integration via atlas-session MCP
- MOLL-E Discord bot

**Success metric**: 50+ paying customers in first 90 days

**Critical rule**: DO NOT build premium before Phase 2 is complete. Design now, build later. Premature monetization kills open-source growth.

---

## 11. Contrarian Mitigations

Seven risks identified by the contrarian analysis, with mitigations.

### Risk 1: Stars Do Not Equal Users (HIGH)

**Claim**: 179 stars could be vanity metrics.
**Disproof**: 220 unique cloners in 14 days. People are downloading and using the tool. Google sends 595 unique visitors. MS Teams links show enterprise sharing. ChatGPT recommends it.
**Mitigation**: Track cloners (real usage) not stars (vanity). Telemetry will provide actual usage data.

### Risk 2: All-in-One Graveyard (HIGH)

**Pattern**: Yeoman -> Grunt -> Gulp -> Webpack -> Vite. Monoliths get replaced by composable tools.
**Mitigation**: v4 strips to core and composes everything else. The plugin does ONE thing well (PRD generation + TaskMaster setup). Execution modes compose with existing skills. If superpowers disappears, Modes B and C still work. If TaskMaster disappears, the PRD is still a standalone markdown file.

### Risk 3: PRD-First vs Vibe Coding (MED-HIGH)

**Reality**: The "just vibe code it" movement is real. Many developers see PRDs as bureaucratic overhead.
**Mitigation**: Position as "PRD Lite that executes itself." The discovery conversation is 4 questions, not 40 fields. The PRD generates in the same session where execution begins. There is no handoff gap, no separate document to maintain. The PRD is a means to structured tasks, not an end in itself.

### Risk 4: Dependency Chain Fragility (HIGH)

**Chain**: Claude Code -> TaskMaster -> Perplexity -> superpowers. Four dependencies. Any one breaks, the tool breaks.
**Mitigation**: `detect-capabilities` with graceful fallback at every link. No TaskMaster? PRD still generates as standalone markdown. No Perplexity? Research uses Claude Code. No superpowers? Modes B and C still work. The core (PRD generation) has ZERO external dependencies beyond Claude Code itself.

### Risk 5: Config Hell / Cold Start (HIGH)

**Problem**: v3 requires 3+ prerequisites before delivering any value.
**Mitigation**: Zero-config. Auto-detect everything. `claude-code` provider as universal fallback means zero API keys needed. First run goes from idea to discovery conversation in under 5 seconds.

### Risk 6: Platform Risk -- Anthropic Builds It (CRITICAL)

**Threat**: Anthropic could build native PRD generation into Claude Code.
**Moat analysis**: The moat is NOT PRD generation (Anthropic will build this). The moat IS:
1. The verification pipeline (CDD + doubt + visual testing)
2. The walk-away loop (ralph-loop with proof)
3. The fleet management (MOLL-E)
4. The cross-project learning (Insight Mode)
5. The progressive discovery conversation (cognitive forcing function)

Anthropic will never build a multi-agent verification pipeline with doubt agents and visual acceptance testing. That is the defensible moat.

### Risk 7: 15-Minute Claim (MEDIUM)

**Reality**: Claimed "15 minutes to production-ready PRD." Actual time: 25-45 min for practiced user, 60-120 min for new user.
**Mitigation**: Honest marketing. Say "comprehensive PRD in one session" not "15 minutes." Trust is worth more than a catchy number. The contrarian agent's exact finding: developers respect honesty about timelines more than inflated claims.

---

## 12. Stripe / Pricing

### Atlas-Auto: $29/month

| Feature | Free | Atlas-Auto ($29/mo) | Atlas Infra ($49/mo) |
|---------|------|---------------------|----------------------|
| PRD Generation | Yes | Yes | Yes |
| TaskMaster Setup | Yes | Yes | Yes |
| Modes A/B/C | Yes | Yes | Yes |
| Mode D (Atlas-Auto) | No | Yes | Yes |
| Deep Research (/question) | No | Yes | Yes |
| CDD Verification | No | Yes | Yes |
| Visual Testing | No | Yes | Yes |
| MOLL-E Discord | No | No | Yes |
| Insight Mode | No | No | Yes |
| Hosted RAG | No | No | Yes |
| Premium Command Bundle | No | Partial | Full |
| Priority Support | No | No | Yes |

### License Key Flow

```
1. User visits atlas-ai.au/pricing
2. Stripe Checkout -> payment processed
3. Webhook fires -> generate license key -> email to user
4. User runs: script.py activate --license ATLAS-XXXX-XXXX
5. detect-capabilities checks license -> unlocks premium features
6. License validated via atlas-session MCP (stripe_validate_customer)
```

### Technical Integration

- Stripe products created via atlas-session MCP (`stripe_create_checkout`)
- License keys stored in atlas-session backend
- Offline grace period: 7 days (license cached locally)
- Deactivation: `script.py deactivate` removes license from machine

---

## 13. Value Propositions with Market Proof

For each core feature, a real company doing something similar and why our approach is different.

### 13.1 PRD Generation

**What it does**: AI-guided discovery conversation that produces a structured, validated PRD.
**Market proof**: Notion ($10B valuation) -- templates and databases for project documentation.
**Why ours is different**: Notion gives you a blank template. We give you an AI interviewer that asks the right questions in the right order and produces a PRD that scores against 13 automated quality checks. The value is the conversation, not the template.

### 13.2 Deep Research per Task

**What it does**: Before implementation begins, each task gets web-searched context -- best practices, library recommendations, OWASP guidelines, performance benchmarks.
**Market proof**: Perplexity ($9B valuation) -- AI-powered web search.
**Why ours is different**: Perplexity searches the web and returns answers. We search the web AND embed the findings directly into task context, so the implementing agent has research notes alongside its implementation instructions. Research is consumed, not just displayed.

### 13.3 Autonomous Execution

**What it does**: Mode D takes a PRD and produces working code with verification proof.
**Market proof**: Devin / Cognition ($10.2B valuation, ~$150M ARR) -- autonomous AI software engineer.
**Why ours is different**: Devin is a single-agent walled garden at $500/month. Atlas-Auto is multi-agent open architecture at $29/month. Devin gives you code. We give you code AND proof it works (CDD cards, doubt agents, visual testing). See Section 17 for detailed comparison.

### 13.4 CDD Verification

**What it does**: Card-Driven Development creates acceptance criteria BEFORE implementation, then verifies them AFTER.
**Market proof**: Checkly (production monitoring) -- verifies applications work in production.
**Why ours is different**: Checkly verifies AFTER deployment. CDD verifies BEFORE deployment. Every task has verifiable acceptance criteria defined upfront, and the implementation is not considered complete until those criteria pass. Shift-left verification.

### 13.5 Visual Testing

**What it does**: AI-powered browser automation takes screenshots and verifies UI matches acceptance criteria.
**Market proof**: Percy / BrowserStack -- visual regression testing.
**Why ours is different**: Percy does pixel-diff regression (does it look the same as before?). We do AI-powered acceptance testing (does it look like what the PRD described?). Semantic visual verification, not just pixel comparison.

### 13.6 Walk-Away Loop (Ralph)

**What it does**: ralph-loop iterates autonomously until completion promise is satisfied, verified by 3x doubt agents + 1x finality agent.
**Market proof**: Factory AI ($300M valuation) -- automated coding workflows.
**Why ours is different**: Factory automates coding. We automate coding + PROVE it works. The ralph-loop doesn't stop when the code compiles -- it stops when 3 independent doubt agents and a finality agent confirm the acceptance criteria are met. Autonomous development with autonomous verification.

### 13.7 Fleet Management (MOLL-E)

**What it does**: Discord bot for managing multiple Claude Code sessions, approving checkpoints, and dispatching work from your phone.
**Market proof**: Slack ($27B acquisition by Salesforce) -- team communication and workflow.
**Why ours is different**: Slack is chat for human teams. MOLL-E is a command center for AI development fleets. Non-technical PMs can monitor CDD status, approve checkpoints, and dispatch work without ever opening a terminal.

### 13.8 Pattern Library (RAG)

**What it does**: Vector database of proven patterns from real projects, surfaced during PRD generation.
**Market proof**: Pieces for Developers -- code snippet management and reuse.
**Why ours is different**: Pieces saves snippets manually. Our RAG auto-promotes patterns from real project evidence -- when a pattern leads to EXCELLENT-grade PRDs and GREEN CDD cards across multiple projects, it gets promoted to the library automatically. Evidence-based pattern curation.

### 13.9 Developer Metrics

**What it does**: Track CDD completion rates, doubt pass rates, PRD quality scores, and mode effectiveness across projects.
**Market proof**: LinearB -- engineering metrics and velocity tracking.
**Why ours is different**: LinearB measures velocity (how fast). We measure quality (how good). CDD completion rate tells you whether your team is shipping verified work. Doubt pass rate tells you whether your implementations actually work. Quality metrics, not speed metrics.

### 13.10 Zero-Config Onboarding

**What it does**: Auto-detect everything, zero questions on first run, start discovery immediately.
**Market proof**: Vercel ($250M ARR) -- zero-config deployment.
**Why ours is different**: Vercel made deployment zero-config (push and it deploys). We make AI-assisted development zero-config (type your idea and it discovers, plans, and executes). Same philosophy, different domain.

---

## 14. MOLL-E: Manager Overseeing Large Language Execution

### What It Is

A Discord bot that provides bidirectional fleet management for Claude Code sessions. Monitor, command, and approve from your phone.

### Core Capabilities

1. **Session Monitoring**: See all active Claude Code sessions, their current task, CDD status, and progress
2. **Checkpoint Approval**: When Atlas-Auto hits a USER-TEST checkpoint, MOLL-E sends a Discord notification. Approve or reject from your phone.
3. **Work Dispatch**: Send new tasks or PRDs to idle sessions directly from Discord
4. **Result Relay**: Completed tasks relay their proof reports (screenshots, CDD results, doubt verdicts) to a Discord channel
5. **Fleet Overview**: Dashboard showing all sessions, their modes, progress, and health

### Why Discord (Not Slack)

- Discord is free for unlimited users and messages
- Developer communities already live on Discord
- Bot SDK is mature and well-documented
- Webhooks are straightforward
- The target audience (indie devs, small teams) uses Discord, not Slack

### Installation

1-shot install into any Discord server:

```
1. Visit atlas-ai.au/moll-e
2. Click "Add to Discord"
3. Select your server
4. MOLL-E appears in #general with setup instructions
5. Run /moll-e setup in Discord to link your Atlas Infra account
```

### Non-Technical PM Use Case

A project manager who cannot use a terminal can:
- See which tasks are in progress, completed, or blocked
- View CDD card status (RED/YELLOW/GREEN) for any task
- Approve or reject checkpoints when Atlas-Auto pauses
- Read proof reports with screenshots
- Ask MOLL-E "what's the status of the auth module?" in natural language

### Tier

Atlas Infra only ($49/month). This is a premium fleet management feature.

---

## 15. Insight Mode

### What It Is

Cross-project learning powered by aggregated telemetry and CDD evidence.

### How It Works

```
Project A (React + Node)    Project B (React + Python)    Project C (Vue + Go)
       |                           |                            |
       v                           v                            v
   Telemetry + CDD evidence -> Atlas Vector DB -> Pattern Analysis
                                      |
                                      v
                              Insight Surfacing
                                      |
                     +----------------+----------------+
                     |                |                |
              "React+Node projects    "Auth tasks      "Projects using
               complete 25% faster    fail CDD 40%     Mode A complete
               with Mode A"          of the time --    30% faster than
                                     add research"    Mode C"
```

### Example Insights

- "Projects in the habit-tracking domain typically need: push notifications, streak tracking, social sharing. Want to include them?"
- "The auth pattern from Project A scored EXCELLENT and passed CDD in 3 similar projects. Recommending it."
- "Your PRD complexity profile matches projects that complete 25% faster with Mode A (superpowers pipeline)."

### Auto-Promotion to RAG

When a pattern leads to:
- EXCELLENT-grade PRDs in 3+ projects
- GREEN CDD cards in 3+ implementations
- Positive doubt agent verdicts in 3+ verifications

...it gets automatically promoted to the hosted RAG library as a "proven pattern."

### Tier

Atlas Infra only ($49/month). Requires hosted infrastructure for vector DB and pattern analysis.

### Privacy

- Only aggregated, anonymous patterns are stored
- No code, no project names, no file paths
- Users can opt out of contributing to Insight Mode while still consuming insights
- Separate from telemetry consent (Insight Mode has its own toggle)

---

## 16. Premium Command Bundle

### Atlas Infra Subscribers Get

| Command | What It Does | Free Alternative |
|---------|-------------|------------------|
| `/atlas-auto` | Full autonomous execution pipeline (Mode D) | Modes A/B/C |
| `/atlas-research` | Deep Perplexity research per task with embedded context | TaskMaster's built-in research |
| `/atlas-verify` | CDD + visual testing verification gate | No verification |
| `/atlas-insight` | View cross-project patterns and recommendations | No insights |
| `/atlas-fleet` | MOLL-E fleet management commands | Manual session management |
| `/atlas-validate` | AI semantic validation (beyond regex checks) | Regex-only validation |

### Free Users

Free users can install individual companion skills manually:
- `/cdd` from the CDD skill repo
- `/ralph-loop` from the ralph-loop skill repo
- `/question` from the question skill repo

Each companion works independently. The premium bundle just installs everything together and adds the Atlas-specific features (fleet, insight, hosted RAG).

### Technical Implementation

```bash
# Premium user activates
script.py activate --license ATLAS-XXXX-XXXX

# detect-capabilities now returns premium features
script.py detect-capabilities
# {"premium": true, "atlas_auto": true, "atlas_research": true, ...}

# SKILL.md router checks capabilities and shows/hides commands accordingly
```

---

## 17. Devin Comparison

### Side-by-Side

| Dimension | Devin (Cognition) | Atlas-Auto (Atlas AI) |
|-----------|-------------------|----------------------|
| **Architecture** | Single agent | Multi-agent (orchestrator + specialists) |
| **Verification** | None (trust the output) | CDD cards + 3x doubt agents + finality + visual testing |
| **Price** | $500/month | $29/month |
| **Environment** | Managed cloud VMs | BYO environment (your machine, your tools) |
| **Openness** | Walled garden, proprietary | Open architecture, composable skills |
| **Communication** | Slack-native | Discord-native (MOLL-E) |
| **Marketing** | $500M+ in funding, massive brand | Organic growth (AI models recommend it) |
| **Output** | Code | Code + PROOF it works |
| **Customization** | Limited | Full (compose your own pipeline) |
| **Data Privacy** | Code runs on their cloud | Code stays on your machine |

### The Proof Difference

This is the core differentiator. Devin gives you code. Atlas-Auto gives you code AND proof.

```
WITHOUT Atlas-Auto (Devin-style):     WITH Atlas-Auto:

Task: "Implement auth"                Task: "Implement auth"

Output:                               Output:
  - auth.js (450 lines)                - auth.js (450 lines)
  - middleware.js (120 lines)           - middleware.js (120 lines)
  - auth.test.js (200 lines)           - auth.test.js (200 lines)
                                        - CDD Card: 6/6 criteria GREEN
  "Done. Auth is implemented."          - Doubt Agent 1: PASS
                                        - Doubt Agent 2: PASS
                                        - Doubt Agent 3: PASS
                                        - Finality Agent: VERIFIED
                                        - Visual: screenshot of login flow
                                        - Visual: screenshot of protected route
                                        - Visual: screenshot of error states

  Trust me.                             Here's the proof.
```

### What Devin Has That We Don't (Yet)

| Devin Advantage | Our Response |
|----------------|--------------|
| Polished landing page | Google Stitch copies their polish (atlas-ai.au rewrite) |
| Managed cloud VMs | "Not hard, add it" -- optional managed cloud in Phase 3 |
| Slack integration | Discord-native via MOLL-E (better for dev communities) |
| Brand recognition | MOLL-E is brandable. Organic AI referrals are growing. |

### Why $29 Not $500

Devin's $500/month pays for managed cloud infrastructure (VMs, sandboxes, orchestration). Atlas-Auto runs on the user's machine using Claude Code they already pay for. No cloud VMs to manage means no cloud VM costs to pass through. The $29 covers the verification pipeline, fleet management, and hosted RAG.

---

## 18. Hook for AI Prompting

### What It Is

prd-taskmaster v4 includes a Claude Code hook that automatically enhances AI behavior when the plugin is installed.

### SessionStart Hook

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "cat ~/.claude/skills/prd-taskmaster/reference/ai-context.md"
      }
    ]
  }
}
```

### What It Injects

The hook injects a lightweight context file on every Claude Code session start:

```markdown
# prd-taskmaster Context (auto-injected)

When the user mentions PRD, product requirements, or task planning:
- Suggest /prd-taskmaster for structured discovery
- Offer to check for existing PRDs in .taskmaster/docs/

When implementing tasks from TaskMaster:
- Check .taskmaster/tasks/tasks.json for task context
- Use task dependencies to determine execution order
- Mark tasks started/complete via TaskMaster MCP

When CDD is available:
- Create CDD cards before implementing MEDIUM+ complexity tasks
- Verify CDD criteria after implementation
- Do not mark task complete until CDD is GREEN
```

### Design Principles

- **Zero user configuration**: Hook is installed automatically with the plugin
- **Lightweight**: The injected context is <50 lines, minimal context budget impact
- **Non-intrusive**: Provides suggestions, does not override user commands
- **Composable**: Works with or without other Atlas skills installed

---

## 19. Atlas Infra Early Access

### What Hosted Subscribers Get

Atlas Infra ($49/month) is the full-service tier for teams and power users.

| Feature | Description | Availability |
|---------|-------------|-------------|
| **New features first** | Beta channel access to all new capabilities | Immediate |
| **MOLL-E Discord bot** | 1-shot install, fleet management from phone | Immediate |
| **Insight Mode** | Cross-project learning and pattern surfacing | Immediate |
| **Hosted RAG** | Pre-populated pattern library, no setup needed | Immediate |
| **Premium Command Bundle** | All /atlas-* commands, one install | Immediate |
| **Discord Community** | Private #atlas-infra channel for support and feedback | Immediate |
| **Priority Support** | Direct access to Hayden for technical issues | Immediate |
| **Managed Cloud** (roadmap) | Optional cloud VMs for Atlas-Auto execution | Phase 3+ |

### Why Early Access Matters

Early adopters shape the product. Atlas Infra subscribers get:
- Direct input on feature prioritization
- Access to features before they're stable (with honest "this is beta" labeling)
- A voice in architecture decisions via the Discord community
- The satisfaction of supporting an indie AI tool that AI models themselves recommend

---

## 20. Website: atlas-ai.au

### Complete Rewrite

The current site needs a ground-up rebuild to match the product's ambition. Google Stitch for design, Pantone brand palette throughout.

### Brand Palette (Pantone-Mapped)

| Role | Pantone | Hex | Usage |
|------|---------|-----|-------|
| Primary | Pantone 2985 C | #5BC2E7 | Action buttons, links, highlights |
| Dark | Pantone Black 6 C | #101820 | Text, backgrounds, code blocks |
| Accent | Pantone 7548 C | #FFC72C | Warm gold for CTAs, premium badges |
| Success | Pantone 7723 C | #43B02A | Green states, CDD pass indicators |
| Warning | Pantone 1495 C | #FF8200 | Orange for alerts, beta labels |
| Error | Pantone 1797 C | #CB333B | Red states, CDD fail indicators |

### Pages

| Page | Path | Purpose |
|------|------|---------|
| Hero / Landing | `/` | Problem statement, demo video, star count, social proof |
| prd-taskmaster | `/prd-taskmaster` | Feature overview, installation, quick start |
| Atlas-Auto | `/atlas-auto` | Premium autonomous mode, Devin comparison, proof examples |
| Pricing | `/pricing` | Free vs Atlas-Auto vs Atlas Infra comparison table |
| Docs | `/docs` | Technical documentation, API reference, plugin guide |
| Blog | `/blog` | Technical articles, case studies, updates |
| Community | `/community` | Discord invite, GitHub link, awesome-lists |

### SEO Targeting

**Traditional search** (Google, Bing, DuckDuckGo):
- "AI PRD generator"
- "TaskMaster setup guide"
- "Claude Code PRD plugin"
- "autonomous AI coding tool"
- "AI development workflow"

**AI search** (ChatGPT, Claude.ai, Perplexity):
- Optimize README and docs for LLM readability
- Structured, factual content that AI models can cite
- Clear feature descriptions that answer "what tool should I use for X?"
- This is already working: ChatGPT sends 64 views, Claude.ai sends 11, Perplexity sends 8

### AI SEO Strategy

AI models are already recommending prd-taskmaster. To amplify this:

1. **README as LLM-readable landing page**: Clear problem/solution structure, factual claims, no marketing fluff
2. **Structured metadata**: JSON-LD schema markup on the website
3. **Comparison content**: Honest "vs" pages (prd-taskmaster vs Devin, vs Cursor, vs manual PRDs)
4. **Technical depth**: AI models prefer tools with good documentation. Deep docs = more AI referrals.

---

## Appendix A: Superpowers Pipeline Composition

Confirmed by reading the plugin source at `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/`.

### Mode A Pipeline

```
brainstorming -> writing-plans -> subagent-driven-development -> finishing-a-development-branch
```

1. **brainstorming**: PRD feeds in as the design doc. AI brainstorms implementation approach.
2. **writing-plans**: Converts brainstorm into structured implementation plan with phases.
3. **subagent-driven-development**: Spawns sub-agents per task. Critical: sub-agents MUST use TaskMaster MCP to mark tasks started/complete.
4. **finishing-a-development-branch**: Cleans up, runs tests, prepares for merge.

### Integration Point

prd-taskmaster generates the PRD and tasks. The superpowers pipeline consumes them. The handoff is the PRD file path and the task list in `.taskmaster/tasks/tasks.json`.

---

## Appendix B: TaskMaster Provider Configuration

From TaskMaster v0.43.1 source code analysis.

### Full Provider List (Hardcoded)

```
anthropic, openai, google, zai, zai-coding, perplexity, xai, groq, mistral,
azure, openrouter, bedrock, ollama, openai-compatible, claude-code, mcp,
gemini-cli, grok-cli, codex-cli
```

### Auto-Generated Config

```json
{
  "models": {
    "main": {
      "provider": "anthropic",
      "modelId": "claude-sonnet-4-5",
      "maxTokens": 64000
    },
    "research": {
      "provider": "perplexity",
      "modelId": "sonar-pro",
      "baseURL": "https://api.perplexity.ai"
    },
    "fallback": {
      "provider": "anthropic",
      "modelId": "claude-haiku-4-5",
      "maxTokens": 32000
    }
  }
}
```

### Perplexity BaseURL Override

The Perplexity client accepts a `baseURL` parameter, resolved in order:
1. Config file `baseURL` field
2. `PERPLEXITY_BASE_URL` environment variable
3. Default: `https://api.perplexity.ai`

### Official Perplexity API Cost

~$0.01 per 10-task PRD session. Negligible for any user with a Perplexity API key.

---

## Appendix C: Discovery Phase Questions (v4)

Reduced from 12 questions (v3) to 4 progressive questions (v4).

### The 4 Questions

Asked one at a time, brainstorming-style:

1. **"What problem does this solve? Who feels the pain?"**
   - Establishes the core value proposition
   - AI extracts: target user, pain point, business impact

2. **"What does the solution look like? Walk me through the happy path."**
   - Establishes the proposed solution
   - AI extracts: features, user flow, tech requirements

3. **"What could go wrong? What are the constraints?"**
   - Establishes risks and boundaries
   - AI extracts: technical constraints, timeline, resources, edge cases

4. **"Anything else I should know?"**
   - Catches everything the first 3 missed
   - AI extracts: integration requirements, existing codebase, preferences

### Smart Defaults

For anything the user doesn't mention, the AI uses sensible defaults and documents assumptions:
- No tech stack mentioned? Default to the project's detected stack or "modern web stack"
- No timeline? Default to "iterative, no fixed deadline"
- No scale requirements? Default to "MVP scale, optimize later"
- No testing preference? Default to "test critical paths, TDD optional"

All defaults are documented in the PRD's Assumptions section so the user can review and override.

---

## Appendix D: Implementation Priority

Based on the growth sequencing and audit findings, here is the build order.

### Must-Have for v4.0 Launch (Phase 1)

1. SKILL.md router (<150 lines)
2. Phase files (DISCOVER, GENERATE, HANDOFF)
3. detect-capabilities command
4. detect-providers command
5. Zero-config provider auto-configuration
6. Placeholder detection in validate-prd
7. Domain-agnostic template
8. 4-question progressive discovery
9. install.sh with SHA256
10. GitHub Releases with semver tags

### Should-Have for v4.0 Launch

11. Telemetry (opt-in)
12. BYO RAG integration
13. pytest suite for script.py
14. Seeded GitHub issues
15. Demo video

### Nice-to-Have (Phase 2)

16. Companion skill: expand-tasks (Perplexity MCP)
17. Companion skill: tracking scripts
18. awesome-list submissions
19. AI semantic validation

### Premium (Phase 3)

20. Atlas-Auto (Mode D)
21. Stripe integration
22. MOLL-E Discord bot
23. Insight Mode
24. Hosted RAG
25. Premium command bundle
26. atlas-ai.au website rewrite

---

*This specification represents 2+ hours of deep research including 40+ Perplexity queries, 5 sub-agent dispatches, TaskMaster source code analysis, GitHub Traffic API data, contrarian risk analysis, and legal review. Every claim is backed by data. Every architecture decision has a documented rationale.*

*prd-taskmaster v4.0 -- The TaskMaster On-Ramp.*
*Atlas AI, 2026.*
