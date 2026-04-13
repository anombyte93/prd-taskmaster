# Parent Session Context Dump

> Everything the child session needs that ISN'T in the debrief.
> This is the research, findings, architecture decisions, and exact data from 2+ hours of work.

---

## REAL GITHUB TRAFFIC DATA (from GitHub API, 2026-04-08)

```
Repo: anombyte93/prd-taskmaster
Stars: 179 | Forks: 18 | Watchers: 0 | Open Issues: 0
Created: 2025-10-21 | Last pushed: 2026-02-16
Language: Python | License: MIT

Star history (monthly):
  2025-10: 9   2025-11: 6   2025-12: 13
  2026-01: 46  2026-02: 44  2026-03: 54  2026-04: 7 (partial)
  ACCELERATING: 9→6→13→46→44→54/month

Traffic (last 14 days):
  Views: 2,136 total / 1,013 unique visitors
  Clones: 341 total / 220 unique cloners

Top referrers:
  Google:       999 views, 595 uniques (ORGANIC SEARCH)
  Reddit:       421 views, 185 uniques
  ChatGPT:       64 views, 16 uniques (AI recommending the tool!)
  GitHub:        62 views, 23 uniques
  Brave Search:  25 views, 11 uniques
  DuckDuckGo:    22 views, 10 uniques
  MS Teams:      17 views, 9 uniques (ENTERPRISE TEAMS SHARING IT)
  Bing:          12 views, 4 uniques
  Claude.ai:     11 views, 2 uniques
  Perplexity:     8 views, 7 uniques
```

---

## CONTRARIAN AGENT REPORT (full text, delivered successfully)

### 7 Risk Vectors

1. **Stars ≠ users (HIGH)** — 179 stars but traffic data DISPROVES "zero users" claim. 220 cloners in 14d is real usage.
2. **All-in-one graveyard (HIGH)** — Yeoman, Grunt→Gulp→Webpack→Vite pattern. Solution: strip to core, compose everything else.
3. **PRD-first vs vibe coding (MED-HIGH)** — Anti-PRD movement is real. Solution: position as "PRD Lite that executes itself."
4. **Dependency chain fragility (HIGH)** — 4 deps (Claude Code, TaskMaster, Perplexity, superpowers). Solution: detect-capabilities with graceful fallback at every link.
5. **Config hell / cold-start (HIGH)** — 3+ prerequisites. Solution: zero-config auto-detect everything.
6. **Platform risk — Anthropic builds it (CRITICAL)** — The moat is NOT PRD generation (Anthropic will build this). The moat IS the verification pipeline (CDD + doubt + visual testing + ralph-loop). Anthropic will never build that.
7. **15-minute claim (MEDIUM)** — Real time is 25-45 min for practiced user, 60-120 for new user. Solution: honest marketing.

### Contrarian's Key Quote
> "The tool's value is not the output (the PRD, the tasks) but the CONVERSATION — the progressive discovery process that forces a developer to articulate what they actually want to build. That cognitive forcing function has genuine value that Anthropic cannot trivially replicate."

---

## AGENT B: ZERO-CONFIG FEASIBILITY (from TaskMaster source code analysis)

Agent B read TaskMaster v0.43.1 compiled source at `/usr/lib/node_modules/task-master-ai/dist/`.

**Full provider list (hardcoded in source):**
```
anthropic, openai, google, zai, zai-coding, perplexity, xai, groq, mistral,
azure, openrouter, bedrock, ollama, openai-compatible, claude-code, mcp,
gemini-cli, grok-cli, codex-cli
```

**Perplexity baseURL is overridable:**
```js
getClient(e) {
  let { apiKey: t, baseURL: n } = e;
  return F({ apiKey: t, baseURL: n || `https://api.perplexity.ai`, ... })
}
```
Resolution: config `baseURL` → `PERPLEXITY_BASE_URL` env var → default API.

**Auto-generated .taskmaster/config.json:**
```json
{
  "models": {
    "main": { "provider": "anthropic", "modelId": "claude-sonnet-4-5", "maxTokens": 64000 },
    "research": { "provider": "perplexity", "modelId": "sonar-pro", "baseURL": "http://localhost:{redacted-proxy-port}" },
    "fallback": { "provider": "anthropic", "modelId": "claude-haiku-4-5", "maxTokens": 32000 }
  }
}
```

**Graceful degradation tiers:**
1. Local perplexity proxy alive → route research through it (free)
2. PERPLEXITY_API_KEY set → use official API (~$0.01/session)
3. Neither → use Anthropic for research too (works, no web search)

**Official Perplexity API cost:** ~$0.01 per 10-task PRD session. Negligible.

**Critical:** User needs ZERO new API keys. ANTHROPIC_API_KEY already exists from Claude Code.

---

## DANGLING AGENT: LEGAL + COMPETITOR INTEL

### COMMONS CLAUSE RISK (CRITICAL — must address)
TaskMaster uses MIT + Commons Clause. Forbids "competing products based on Task Master" and hosted services.

**Resolution: keep ALL TaskMaster integration in the FREE tier.**
- Free tier drives users TO TaskMaster (symbiotic, not competitive)
- Premium tier (CDD + doubt + visual testing) doesn't touch TaskMaster at all
- Premium = independent methodology that works with ANY task source
- Contact eyaltoledano for explicit partnership/blessing before launch

### TaskMaster already has a PRD template
`.taskmaster/templates/example_prd.txt` — but it's a static example, not an AI-guided discovery conversation. Our value is the PROCESS, not the template.

### Plugin marketplace spec is unstable
Ship BOTH: install.sh (proven, works now) + marketplace.json (future-proofing).

---

## ARCHITECTURE: THE 4 EXECUTION MODES

```
prd-taskmaster v4 generates: PRD + tasks.json
                    │
                    ▼
         ┌──────────────────────────────────────┐
         │         HANDOFF: Choose Mode          │
         │                                       │
         │  FREE TIER:                           │
         │  A) superpowers pipeline              │
         │     brainstorm → plans → subagents    │
         │  B) TaskMaster native auto-execute    │
         │  C) Manual control (commands + go)    │
         │                                       │
         │  PREMIUM (Atlas-Auto):                │
         │  D) ★ ATLAS-AUTO — Autonomous Dev     │
         │     PRD → CDD cards → ralph loop →    │
         │     self-research → implement →       │
         │     doubt agents → visual-test →      │
         │     proof report                      │
         │     (user walks away)                 │
         └───────────────────────────────────────┘
```

### Mode D (Atlas-Auto) Full Chain:
```
PRD → /cdd cards → /ralph-loop → /question research → superpowers:subagent-driven-dev →
/cdd GREEN verify → 3x doubt + finality → /atlas-user-test visual gate → OUTPUT
```

### Premium Addons (runtime-detected, gracefully degraded):
| Addon | Skill | Tier |
|-------|-------|------|
| Deep Research | /question | Premium |
| CDD Cards | /cdd | Premium |
| Walk-Away Loop | /ralph-loop | Premium (Atlas-Auto) |
| Visual Testing | /atlas-user-test | Premium (Atlas-Auto) |
| Doubt Pipeline | Built-in | Premium (Atlas-Auto) |
| Pattern Library | RAG (hosted) | Premium |
| Pattern Library | RAG (BYO) | Free (BYO) |
| Telemetry | Built-in | Free (opt-in) |
| MOLL-E Discord | Bot | Premium (Atlas Infra) |
| Insight Mode | Hosted | Premium (Atlas Infra) |

---

## ONBOARDING: ANTI-WIZARD

**Zero questions on first run.** Auto-detect everything. Start discovery immediately.

```
FIRST RUN:
$ /prd-taskmaster "I want to build a habit tracking app"

  ✓ Detected: Claude Code (Anthropic API)
  ✓ Detected: TaskMaster MCP
  ✓ Detected: Perplexity MCP (research enabled)
  ✓ Auto-configured: .taskmaster/config.json
  
  Ready. Let's discover what you're building.
  
  What problem does this solve? Who feels the pain?
  > _
```

**Post-value "Capabilities Unlocked" (after PRD generated):**
```
  ✅ PRD Generated: .taskmaster/docs/prd.md (EXCELLENT - 57/60)
  ✅ 24 tasks parsed with dependencies
  
  ┌─────────────────────────────────────────────┐
  │  Your capabilities:                          │
  │                                              │
  │  ✅ TaskMaster auto-execute      [ready]     │
  │  ✅ Superpowers pipeline         [ready]     │
  │  ✅ Deep research per task       [ready]     │
  │  ○  CDD verification cards      [install →] │
  │  ○  Visual browser testing      [install →] │
  │                                              │
  │  ★ ATLAS-AUTO available                     │
  │    Walk away. Come back to proof.            │
  │    Requires: CDD + ralph-loop               │
  │    [Learn more →]                            │
  └─────────────────────────────────────────────┘
```

---

## FILE STRUCTURE

```
skills/prd-taskmaster/
├── SKILL.md                       (<150 lines — router + auto-detection)
├── script.py                      (refactored)
│   Commands: preflight, detect-taskmaster (FIXED), detect-capabilities (NEW),
│   detect-providers (NEW), load-template, validate-prd (+ placeholder detection),
│   calc-tasks, prd-to-cards (NEW), output-contract (NEW), rag-query (NEW),
│   rag-init (NEW), telemetry (NEW), backup-prd
│   REMOVED: gen-scripts, gen-test-tasks, read-state, log-progress
├── phases/
│   ├── DISCOVER.md    (<120 lines — brainstorming-style progressive, 4 Qs, one at a time)
│   ├── GENERATE.md    (<120 lines — PRD gen + hybrid validation + task parse + optional research)
│   └── HANDOFF.md     (<120 lines — 4 modes composed, detect-capabilities drives display)
├── templates/
│   ├── prd-comprehensive.md  (domain-agnostic, AI generates examples, <500 lines)
│   ├── prd-minimal.md        (unchanged)
│   └── CLAUDE.md.template    (multi-workflow, TDD OPTIONAL not mandatory)
├── reference/
│   ├── validation-checklist.md
│   ├── taskmaster-guide.md
│   └── provider-config.md    (NEW: zero-config provider setup)
├── companion-skills/
│   └── expand-tasks/         (refactored: Perplexity MCP, not localhost proxy)
└── install.sh                (with SHA256 + auto-detect TaskMaster install)
```

---

## TELEMETRY (opt-in, GDPR)

Homebrew pattern. First run prompt. Schema:
```json
{"event": "prd_generated", "tool_version": "4.0.0", "os": "linux", "grade": "EXCELLENT",
 "task_count": 24, "mode_chosen": "A", "capabilities": ["superpowers", "perplexity"]}
```
No PII, no IP, no code. Config: `~/.config/prd-taskmaster/telemetry.json`.

---

## RAG PATTERN LIBRARY

Hosted (Atlas AI): Qdrant Cloud, pre-populated with Hayden's proven patterns.
BYO: User connects their own vector DB.
3 integration points: DISCOVER (domain questions), GENERATE (PRD patterns), HANDOFF (mode recommendations).
Graceful: no RAG → skill works fine, just no pattern recommendations.

---

## MOLL-E: Manager Overseeing Large Language Execution

Discord bot. Fleet management from your phone. Bidirectional:
- Monitor active Claude Code sessions
- Receive notifications on task completion/errors/checkpoints
- Approve/reject Atlas-Auto checkpoints FROM DISCORD
- Dispatch new work to idle sessions
- Insight Mode: see patterns across projects
1-shot install into your Discord server (Atlas Infra feature).

---

## STRIPE

$29/month Atlas-Auto. License key flow:
1. Stripe Checkout via atlas-ai.au/pricing
2. Webhook → generate license key → email
3. `script.py activate --license ATLAS-XXXX-XXXX`
4. `detect-capabilities` checks license → unlocks premium
5. atlas-session MCP has Stripe tools (stripe_create_checkout, stripe_validate_customer, etc.)

---

## WEBSITE: atlas-ai.au

Complete rewrite. Google Stitch for design. Pantone brand palette.
Pages: / (hero), /prd-taskmaster, /atlas-auto, /pricing, /docs, /blog, /community.
SEO targeting: "AI PRD generator", "TaskMaster setup", "Claude Code PRD".
AI SEO: ChatGPT + Claude.ai already refer users — optimize README for LLM readability.

---

## DEVIN COMPARISON (user's words)

"Isn't my system Devin but better? All Devin does is abstract away complexity and make it FEEL good."

What Devin has: $500M marketing, managed cloud VMs, Slack-native UX, brand recognition.
What we have: Multi-agent (better), CDD verification (unique), open architecture (unique), $29 not $500.

User's response to "what Devin has that you don't":
1. Landing page → Google Stitch copies their polish
2. Managed cloud → "not hard, add it"
3. Slack-native → Discord-native via MOLL-E
4. Brand → "How is MOLL-E NOT brandable?"

---

## GROWTH SEQUENCING

Phase 1 (weeks 1-4): Ship free v4 core. Convert to plugin. Seed issues. Demo video.
Phase 2 (weeks 5-12): Submit to awesome-lists. Reddit/HN launch. Grow to 1000 stars.
Phase 3 (weeks 13+): Launch premium ONLY when 2000+ cloners/month. CDD + ralph-loop as paid companion.
DO NOT build premium before Phase 2 is complete. Design now, build later.

---

## 20-ITEM AUDIT FINDINGS (from /question)

1. Validation passes on template placeholders — ADD placeholder detection
2. Zero GitHub issues — SEED issues, enable Discussions
3. 12-question discovery wall — REDUCE to 4, progressive
4. No tests for script.py — ADD pytest
5. Tracking scripts unused — MOVE to companion
6. curl|bash no signatures — ADD SHA256
7. TDD mandate unrealistic — MAKE optional
8. Codex untested claim — REMOVE or test
9. TaskMaster catching up — DIFFERENTIATE
10. Regex validation is theatre — ADD AI semantic validation
11. No version pinning — CREATE GitHub Releases
12. expand-tasks requires local proxy — FIX to use Perplexity MCP
13. Upgrade overwrites customizations — BACK UP entire directory
14. Template 2FA bias — MAKE domain-agnostic
15. Blind validator circular — REPLACE with execution-based
16. MCP detection wrong paths — FIX (add ~/.claude.json, ~/.claude/settings.json)
17. No discoverability — SUBMIT to awesome-lists, demo video
18. script.py doesn't scale — PACKAGE as proper Python module
19. Crash recovery passive — REMOVE from core
20. Skill wants to be platform — SPLIT into core + companions

---

## SUPERPOWERS PIPELINE COMPOSITION

Confirmed by reading plugin source at `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/`:

brainstorming → writing-plans → subagent-driven-development → finishing-a-development-branch

This is the PROVEN pipeline for Mode A. PRD feeds into brainstorming as the design doc.
Critical instruction: subagents MUST use TaskMaster MCP to mark tasks started/complete.

---

## PREMIUM COMMAND BUNDLE (Atlas Infra)

| Command | What It Does |
|---------|-------------|
| /atlas-auto | Autonomous execution pipeline |
| /atlas-research | Deep Perplexity research per task |
| /atlas-verify | CDD + visual testing gate |
| /atlas-insight | View cross-project patterns |
| /atlas-fleet | MOLL-E fleet management |
| /atlas-validate | AI semantic validation |

Free users install individual companions manually.
Atlas Infra users get everything as one plugin + license key.

---

## SIDE-BY-SIDE PROOF (for selling premium)

WITHOUT /question:           WITH /question:
Task 5: "Implement auth"    Task 5: "Implement auth"
  subtasks:                    subtasks + research_notes:
  - Set up auth routes         - bcrypt cost factor 12
  - Add middleware             - Rate limit: express-rate-limit
  - Write tests                - Session: Redis w/ connect-redis
                               - OWASP auth cheat sheet compliance

Mode C (Manual):             Mode D (Atlas-Auto):
"Here are 26 tasks. Go."    "Here are 26 tasks. I'll handle it."
  User does everything         CDD + doubt + visual = proof

---

*This file contains everything from the 2+ hour parent session that cannot be reconstructed from the debrief alone.*
