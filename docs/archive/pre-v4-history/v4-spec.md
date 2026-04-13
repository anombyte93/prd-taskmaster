# prd-taskmaster v4.0 Spec — "The TaskMaster On-Ramp" (ARCHIVED)

> **ARCHIVED PRE-V4 PLANNING DOCUMENT.** This spec was written before the v4 ship cycle and contains references to private Atlas infrastructure (local research proxies, private MCP tool names) that are NOT part of the public v4 release. The shipped v4 is **provider-agnostic** — it uses whatever research model or MCP is configured by the user via `task-master models --set-research` or `~/.claude.json`. Do not treat references in this archived spec as configuration recommendations for public users. See `docs/v4-release/` and the repo's `README.md` for the authoritative v4 setup.
>
> Strip to core. Compose everything else. The moat is the verification pipeline.

## Vision

One command. User describes their idea. 10 minutes later: validated PRD, structured tasks, execution pipeline running. No config. No API keys. No setup steps.

## Strategic Position

**FREE tier** = the on-ramp. PRD generation + TaskMaster setup. This is the "top of funnel" that brings users in. Anthropic WILL eventually compete here — accept this.

**PREMIUM tier** = the moat. CDD cards + ralph-loop + doubt agents + visual testing + deep research. This is a *verified autonomous execution methodology*, not a feature. Anthropic will never build this.

**The defensible core** (per contrarian analysis): the progressive discovery conversation that forces articulation of intent. This cognitive forcing function is the true value — not the document it produces.

---

## Architecture: Core + Composed Addons

```
USER: "I want to build X"
         │
         ▼
┌────────────────────────────────┐
│     prd-taskmaster (CORE)      │
│                                │
│  DISCOVER → GENERATE → HANDOFF │
│                                │
│  Auto-detects everything:      │
│  ✓ Claude Code (guaranteed)    │
│  ✓ Anthropic API (user has it) │
│  ✓ Perplexity MCP (if avail)  │
│  ✓ TaskMaster (install if not) │
│  ✓ Superpowers (if installed)  │
│  ✓ Premium skills (if avail)   │
└──────────┬─────────────────────┘
           │
           ▼
┌────────────────────────────────────────┐
│     HANDOFF: Choose Execution Mode     │
│                                        │
│  FREE:                                 │
│  A) superpowers pipeline               │
│  B) TaskMaster native auto-execute     │
│  C) Manual control                     │
│                                        │
│  PREMIUM:                              │
│  D) Autonomous "Walk Away" Loop        │
│     PRD → CDD → ralph-loop →          │
│     research → implement → doubt →    │
│     visual-test → proof               │
└────────────────────────────────────────┘
```

## Premium Addons (runtime-detected, gracefully degraded)

| Addon | Skill | What It Does | Enhances | Tier |
|-------|-------|-------------|----------|------|
| Deep Research | `/question` | Parallel Perplexity research per task. Side-by-side proof. | ALL modes | Premium |
| CDD Cards | `/cdd` | PRD requirements → executable verification contracts | ALL modes | Premium |
| Walk-Away Loop | `/ralph-loop` | Autonomous execution that loops until done | Atlas-Auto | Premium |
| Visual Testing | `/atlas-user-test` | Browser-auto verification with screenshots | Atlas-Auto | Premium |
| Doubt Pipeline | Built-in | 3x doubt agents + 1x finality agent | Atlas-Auto | Premium |
| Pattern Library | RAG (hosted) | Pre-populated patterns from proven projects | ALL phases | Premium |
| Pattern Library | RAG (BYO) | Connect your own vector DB with your patterns | ALL phases | Free (BYO) |
| Telemetry | Built-in | Anonymous opt-in usage analytics | Core | Free (opt-in) |

Each addon: `if skill_available() → use. else → skip with note.`

---

## Contrarian Risk Mitigations

| Risk (from contrarian agent) | Rating | Mitigation |
|-----|--------|-----------|
| Stars ≠ users | HIGH | Add install telemetry (opt-in ping). Measure weekly active installs. Seed GitHub issues. |
| All-in-one graveyard | HIGH | Core does ONE thing (discovery + PRD). Everything else is COMPOSED, not built-in. |
| PRD-first vs vibe coding | MED-HIGH | Position as "PRD Lite that executes itself." 10 min, not 10 days. Living doc, not waterfall. |
| Dependency chain fragility | HIGH | `detect-capabilities` with graceful fallback at EVERY link. Never error, always degrade. |
| Cold-start config hell | HIGH | Zero-config: auto-detect + auto-install TaskMaster. User provides: their idea. Nothing else. |
| Platform risk (Anthropic) | CRITICAL | **Free tier is expendable. Premium tier (CDD + doubt + visual) is the moat Anthropic won't build.** |
| 15-min claim vs reality | MEDIUM | Honest: "Validated PRD in 10 minutes." Don't claim working software. |

---

## File Structure

```
skills/prd-taskmaster/
├── SKILL.md                       (<150 lines — router + auto-detection)
├── script.py                      (refactored)
│   Commands:
│   ├── preflight                  (detect env state)
│   ├── detect-taskmaster          (find MCP/CLI — FIXED paths)
│   ├── detect-capabilities        (NEW: detect ALL available skills/MCPs)
│   ├── load-template              (load PRD template)
│   ├── validate-prd               (13 structural + placeholder detection)
│   ├── calc-tasks                 (recommended task count)
│   ├── prd-to-cards               (NEW: extract REQ-NNN → CDD card YAML)
│   ├── output-contract            (NEW: JSON manifest of what was produced)
│   ├── detect-providers           (NEW: auto-config TaskMaster providers)
│   ├── rag-query                  (NEW: query pattern library)
│   ├── rag-init                   (NEW: initialize BYO vector DB)
│   ├── telemetry                  (NEW: opt-in/out + send events)
│   └── backup-prd                 (timestamped backup)
│   Removed: gen-scripts, gen-test-tasks, read-state, log-progress
│
├── phases/
│   ├── DISCOVER.md                (<120 lines)
│   │   Brainstorming-style progressive discovery
│   │   4 essential questions, one at a time
│   │   AI auto-detects codebase context first
│   │   "Want to go deeper?" for optional follow-ups
│   │
│   ├── GENERATE.md                (<120 lines)
│   │   Load template → fill with discovery answers
│   │   Hybrid validation: script.py structural + AI semantic
│   │   Hard gate: must pass GOOD+ before proceeding
│   │   Parse into tasks via TaskMaster MCP/CLI
│   │   IF Perplexity available: parallel research per task
│   │   IF /cdd available: generate CDD cards from requirements
│   │
│   └── HANDOFF.md                 (<120 lines)
│       detect-capabilities → show available modes
│       Mode A: invoke superpowers pipeline
│       Mode B: invoke TaskMaster auto-execute
│       Mode C: show commands + exit
│       Mode D: invoke premium pipeline (CDD → ralph → doubt → visual)
│       Output contract JSON for downstream consumers
│
├── templates/
│   ├── prd-comprehensive.md       (domain-agnostic, <500 lines)
│   ├── prd-minimal.md             (unchanged, 103 lines)
│   └── CLAUDE.md.template         (multi-workflow, TDD optional)
│
├── reference/
│   ├── validation-checklist.md
│   ├── taskmaster-guide.md
│   └── provider-config.md         (NEW: zero-config provider setup)
│
├── companion-skills/              (optional, separately installable)
│   └── expand-tasks/              (refactored: Perplexity MCP, not localhost)
│
└── install.sh                     (with SHA256 verification)
```

---

## Phase Details

### DISCOVER.md — Progressive Discovery

Pattern: follows superpowers:brainstorming style.

1. **Explore context first** — scan codebase, read existing docs, recent commits
2. **Ask ONE question at a time** — not a wall of 13
3. **4 essential questions:**
   - What problem are you solving? (pain point + who)
   - What's your proposed solution? (high-level)
   - What constraints exist? (tech stack, timeline, scale)
   - What does success look like? (metrics)
4. **AI auto-detects:** tech stack, existing patterns, integration points from codebase
5. **"Want to refine?"** — optional deep-dive for complex projects
6. **Multiple choice when possible** — reduce cognitive load

Hard gate: Discovery answers exist. Proceed to GENERATE.

### GENERATE.md — PRD Generation + Validation + Tasks

1. Load template via `script.py load-template`
2. AI fills template with discovery answers + codebase context
3. Domain-appropriate examples generated by AI (NOT hardcoded 2FA)
4. Run `script.py validate-prd` — structural checks (13 + placeholder detection)
5. AI does semantic validation — is this real content or boilerplate?
6. **Hard gate: GOOD+ grade (≥83%) before proceeding**
7. Parse into tasks via TaskMaster MCP (preferred) or CLI
8. IF Perplexity MCP detected → parallel research expansion per task
9. IF /cdd detected → `script.py prd-to-cards` → CDD YAML from requirements

Hard gate: Tasks exist in tasks.json. Proceed to HANDOFF.

### HANDOFF.md — Execution Mode Selection

1. Run `script.py detect-capabilities` → JSON of what's available
2. Present available modes based on what's detected:

**Always available (FREE):**
- **A) superpowers pipeline** — if superpowers plugin installed
  - PRD feeds into brainstorming (validates design) → writing-plans → subagent-driven-dev
  - Subagents use TaskMaster MCP to mark tasks started/complete
- **B) TaskMaster native** — always available (TaskMaster is required)
  - Hand off to TaskMaster's built-in auto-execution
- **C) Manual** — always available
  - Display task list, commands, dependency order → exit

**If premium skills detected (PREMIUM):**
- **D) Walk-Away Autonomous** — if /cdd + /ralph-loop detected
  - Full chain: CDD cards → ralph-loop → self-research → implement → doubt → visual-test → proof
  - User walks away, comes back to working code + evidence artifacts

3. Run `script.py output-contract` → JSON manifest of everything produced
4. If premium available but not selected, show side-by-side comparison of what they'd get

---

## Zero-Config Architecture

### What the user needs
- Claude Code (they already have it — that's how they're running this)

### What auto-detects
- Anthropic API key (Claude Code has it)
- Perplexity MCP (check if `mcp__{redacted-research-provider}__*` tools exist)
- TaskMaster MCP (check config files at correct paths)
- Superpowers plugin (check skill list)
- Premium skills (check each by name)

### What auto-installs (with user confirmation)
- TaskMaster MCP if not present — offer to install via npm

### TaskMaster provider config (CONFIRMED from source code analysis)

Agent B read TaskMaster v0.43.1 compiled source at `/usr/lib/node_modules/task-master-ai/dist/`.

**Full supported provider list** (hardcoded in source):
```
anthropic, openai, google, zai, zai-coding, perplexity, xai, groq, mistral,
azure, openrouter, bedrock, ollama, openai-compatible, claude-code, mcp,
gemini-cli, grok-cli, codex-cli
```

**Perplexity baseURL is overridable** — the hook for local proxy:
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

**For public distribution:** Official Perplexity API ($0.01/session), not local proxy.
**For personal use:** Local proxy = zero cost.

**Critical: user needs ZERO new API keys.** ANTHROPIC_API_KEY already exists from Claude Code.

---

## Premium Pipeline: Mode D Full Chain

```
PRD (from GENERATE phase)
  │
  ├→ script.py prd-to-cards → CDD card YAML per requirement
  │   Each card: functional_requirements, testing_plan, acceptance_criteria
  │
  ├→ /cdd phases/ROUTE.md → load cards, score tiers, dispatch
  │
  ├→ /ralph-loop → autonomous wrapper (loops until done)
  │   │
  │   ├→ /question → self-research per task (Perplexity parallel)
  │   │
  │   ├→ superpowers:subagent-driven-dev → implement per task
  │   │   - Fresh subagent per task
  │   │   - Two-stage review: spec compliance + code quality
  │   │   - TaskMaster MCP marks tasks started/complete
  │   │
  │   ├→ /cdd phases/GREEN.md → verify each card
  │   │   └→ If RED → /cdd phases/BLUE.md → fix → re-verify
  │   │
  │   ├→ 3x doubt agents + 1x finality → quality gate
  │   │
  │   └→ /atlas-user-test → VISUAL VERIFICATION
  │       - Browser-auto tests running app
  │       - Screenshots captured as evidence
  │       - Scored PASS/FAIL per behavior check
  │       - If FAIL → loop continues
  │
  └→ OUTPUT:
      - Working code (committed, tested)
      - CDD evidence artifacts (per requirement)
      - Visual test screenshots (per behavior)
      - Proof report (what was built, how it was verified)
```

---

## Side-by-Side Proof (selling premium)

### /question research enhancement
```
WITHOUT /question:              WITH /question:
─────────────────              ──────────────
Task 5: "Implement auth"       Task 5: "Implement auth"
  subtasks:                      subtasks:
  - Set up auth routes           - Set up auth routes (JWT + refresh tokens)
  - Add middleware               - Add middleware (passport.js w/ local strategy)
  - Write tests                  - Write tests (jest + supertest, mock Redis)
                                 research_notes:
                                   - bcrypt cost factor 12 for password hashing
                                   - Rate limit: express-rate-limit, 5 req/15min
                                   - Session storage: Redis w/ connect-redis
                                   - OWASP auth cheat sheet compliance points
```

### Mode C vs Mode D
```
Mode C (Manual):               Mode D (Walk-Away):
────────────────               ───────────────────
"Here are 26 tasks. Go."      "Here are 26 tasks. I'll handle it."
  User implements each           CDD cards verify each requirement
  User tests manually           Doubt agents try to break it
  User decides when done        Visual tests prove it works
  No proof it works              Evidence report with screenshots
  Hours of user time             User comes back to proof
```

---

## script.py New Commands

### detect-capabilities
```json
{
  "ok": true,
  "core": {
    "claude_code": true,
    "anthropic_api": true,
    "taskmaster_mcp": true,
    "taskmaster_cli": false
  },
  "free_addons": {
    "superpowers": true,
    "perplexity_mcp": true
  },
  "premium_addons": {
    "cdd": false,
    "ralph_loop": true,
    "question": true,
    "atlas_user_test": false
  },
  "available_modes": ["A", "B", "C"],
  "recommended_mode": "A",
  "premium_modes_if_installed": ["D"],
  "missing_for_premium": ["cdd", "atlas_user_test"]
}
```

### prd-to-cards
Input: PRD path
Output: Array of CDD card YAML objects extracted from REQ-NNN requirements.
Each card includes: card_id, title, source (PRD section ref), functional_requirements (from acceptance criteria), testing_plan (AI-generated from requirements).

### output-contract
Input: none (reads .taskmaster/ state)
Output: JSON manifest of everything produced:
```json
{
  "prd_path": ".taskmaster/docs/prd.md",
  "tasks_path": ".taskmaster/tasks/tasks.json",
  "task_count": 26,
  "validation_score": 55,
  "validation_grade": "EXCELLENT",
  "cdd_cards": ["cdd-cards/PRD-REQ-001.yaml", "..."],
  "claude_md_generated": true,
  "execution_mode": "A",
  "capabilities_detected": { ... }
}
```

---

## Validation Improvements

### Structural (script.py) — keep
- 13 existing checks (section presence, keyword matching)
- NEW: Placeholder detection (penalize `[...]`, `{{}}`, `[placeholder]`, example text)
- NEW: Template fingerprinting (detect if PRD is just the template with examples)

### Semantic (AI judgment) — add
- "Is this executive summary about a REAL project or template boilerplate?"
- "Do these requirements describe THIS project or are they generic?"
- "Are the technical considerations specific to the stated tech stack?"

### MCP Detection — fix
Check these paths (currently missing):
- `~/.claude.json` (primary MCP config)
- `~/.claude/settings.json`
- `.claude/settings.json` (project-local)
- `.mcp.json` (project-local)
- Existing paths kept as fallbacks

---

## install.sh Improvements

1. SHA256 checksum of installed files (verify integrity)
2. Back up ENTIRE skill directory on upgrade (not just SKILL.md)
3. Auto-detect TaskMaster: if not installed, offer `npm install -g task-master-ai`
4. Version pinning: support `--version 4.0.0` flag
5. GitHub Releases: create actual releases (currently none exist)

---

## Template Improvements

### prd-comprehensive.md
- Strip 2FA-specific examples entirely
- Replace with domain-agnostic placeholders:
  ```
  > Example: [AI fills this with a domain-appropriate example based on discovery answers]
  ```
- Reduce from 983 lines to ~400 lines
- AI generates contextual examples at fill time

### CLAUDE.md.template
- TDD as RECOMMENDED, not MANDATORY
- Offer 3 workflow modes:
  1. TDD-first (write tests → implement → refactor)
  2. Test-after (implement → write tests → verify)
  3. Speed mode (implement → manual verification)
- Remove blind-validator references (circular AI-validates-AI)
- Add TaskMaster command reference
- Reduce from 636 lines to ~300 lines

---

## Migration from v3 → v4

### Backwards compatible
- `.taskmaster/docs/prd.md` path unchanged
- `.taskmaster/tasks/tasks.json` path unchanged
- `script.py preflight` still works
- `script.py validate-prd` still works (enhanced, not breaking)

### Breaking changes
- `gen-scripts` removed (tracking scripts not generated)
- `gen-test-tasks` removed (USER-TEST insertion moved to companion)
- `read-state` removed (crash recovery removed from core)
- `log-progress` removed (tracking moved to companion)
- SKILL.md structure completely different (phases, not monolith)

### For downstream consumers (7 skills)
- `output-contract` provides stable JSON interface
- Phase-executor, org-tree, task-executor: update to read output contract
- Expand-tasks: refactor to use Perplexity MCP directly

---

## Success Metrics

| Metric | Current | Target (90 days) |
|--------|---------|-------------------|
| GitHub stars | 179 | 500+ |
| GitHub issues (external) | 0 | 20+ |
| External PRs | 0 | 5+ |
| Install count (tracked) | unknown | 100+ weekly |
| Time to first PRD (new user) | unknown (~60min) | <15 min |
| Discussions enabled | no | yes |
| GitHub Releases | 0 | 3+ |
| Demo video | no | yes (2-min) |

---

---

## Legal: Commons Clause Risk

**TaskMaster uses MIT + Commons Clause.** The clause forbids "competing products based on Task Master" and hosted services.

**Resolution: keep all TaskMaster integration in the FREE tier.**
- Free tier: drives users TO TaskMaster (symbiotic, not competitive)
- Premium tier: CDD + doubt + visual testing — works with ANY task source
- Premium never wraps TaskMaster directly — it wraps the METHODOLOGY
- Contact eyaltoledano for explicit partnership/blessing before launch

**The paid addons don't touch TaskMaster at all:**
- /cdd = verification cards (independent)
- /ralph-loop = autonomous execution (independent)
- /atlas-user-test = visual testing (independent)
- /question = Perplexity research (independent)
- Doubt pipeline = quality gate (independent)

TaskMaster is the free task engine. The premium is the quality/verification layer on top.

---

## Mode D Branding: Atlas-Auto

The premium autonomous execution mode is branded **Atlas-Auto** — not "Mode D."

```
  ★ ATLAS-AUTO — Autonomous Development
    Describe your idea. Walk away. Come back to proof.
    PRD → CDD cards → self-research → implement → doubt → visual-test
    [Requires: atlas-auto companion plugin]
```

Atlas-Auto is the Atlas AI brand's entry into the prd-taskmaster ecosystem. It positions the premium tier as a distinct product, not just a "mode."

---

## Ethical Telemetry (opt-in, GDPR-compliant)

**Problem:** 220 cloners in 14 days but zero feedback. We don't know if they succeeded, failed, or gave up.

**Solution:** Opt-in anonymous telemetry on first run.

```
  prd-taskmaster would like to send anonymous usage data to help improve the tool.
  
  What we collect:
    ✓ PRD generated (yes/no)
    ✓ Validation grade achieved
    ✓ Execution mode chosen
    ✓ Task count
    ✓ OS + Claude Code version
  
  What we NEVER collect:
    ✗ Your code, PRD content, or project details
    ✗ API keys or credentials
    ✗ IP address or identity
  
  [Yes, help improve] [No thanks]
```

**Implementation:**
- First run: single opt-in prompt (Homebrew pattern)
- Config stored in `~/.config/prd-taskmaster/telemetry.json`
- Data sent as anonymous POST to Atlas AI endpoint (or self-hosted PostHog)
- GDPR: no PII, no IP logging, 12-month retention, public schema
- `CLAUDE_CODE_ENABLE_TELEMETRY` env var respected (if disabled globally, skip prompt)
- `script.py telemetry --disable` to opt out any time

**Schema (minimal):**
```json
{
  "event": "prd_generated",
  "tool_version": "4.0.0",
  "os": "linux",
  "grade": "EXCELLENT",
  "task_count": 24,
  "mode_chosen": "A",
  "capabilities": ["superpowers", "perplexity"],
  "timestamp": "2026-04-08T00:00:00Z"
}
```

**What this gives us:**
- Conversion funnel: how many start → generate PRD → choose execution mode
- Quality distribution: what grades are people getting
- Mode popularity: which execution mode do people actually choose
- Capability detection: what's the installed ecosystem look like

---

## RAG Enhancement: Pre-Populated Pattern Library

**The value:** Your 37+ projects have produced PROVEN patterns — discovery questions that work, PRD structures that lead to good tasks, validation approaches that catch real issues, execution strategies that ship. This knowledge is currently locked in your head and your session histories.

**Architecture:**

```
┌────────────────────────────────────────────┐
│         RAG Pattern Library                 │
│                                            │
│  Hosted (Atlas AI):                        │
│    Pre-populated with Hayden's patterns    │
│    - Discovery question sequences          │
│    - PRD section templates by domain       │
│    - Task decomposition strategies         │
│    - Validation rules that caught bugs     │
│    - Execution patterns that shipped       │
│    Updated as more projects succeed        │
│                                            │
│  BYO (user's own vector DB):              │
│    Connect Pinecone/Qdrant/pgvector        │
│    Populate with YOUR project history      │
│    Your patterns, your team's conventions  │
└────────────────────┬───────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  prd-taskmaster v4     │
        │                        │
        │  DISCOVER phase:       │
        │    RAG → "For fintech  │
        │    apps, these 3 extra │
        │    questions matter"   │
        │                        │
        │  GENERATE phase:       │
        │    RAG → "This PRD     │
        │    structure worked    │
        │    for similar scope"  │
        │                        │
        │  HANDOFF phase:        │
        │    RAG → "Projects     │
        │    this size work best │
        │    with Mode A"        │
        └────────────────────────┘
```

**Integration points (3 places RAG enhances the pipeline):**

| Phase | RAG Query | What It Returns |
|-------|-----------|----------------|
| DISCOVER | "What discovery questions work for [domain] projects?" | Domain-specific follow-up questions |
| GENERATE | "What PRD patterns succeeded for [tech stack] + [complexity]?" | Template recommendations, section emphasis |
| HANDOFF | "What execution mode worked for projects with [N tasks] and [complexity]?" | Mode recommendation with evidence |

**Implementation:**
```python
# script.py new command
script.py rag-query --phase discover --context "fintech app, React+Node, 20 tasks"

# Returns:
{
  "ok": true,
  "source": "hosted",  # or "byo"
  "results": [
    {
      "pattern": "fintech-discovery-questions",
      "confidence": 0.92,
      "content": "For fintech: ask about regulatory requirements, PCI compliance scope, and transaction volume estimates",
      "evidence": "Used in 3 successful fintech PRDs, average validation grade: EXCELLENT"
    }
  ]
}
```

**Hosted service (Atlas AI):**
- Qdrant Cloud (cheapest for this scale, ~$25/month for small instance)
- Pre-populated with embeddings from your proven patterns
- API endpoint: `https://rag.atlas-ai.au/v1/query`
- Auth: API key from Atlas AI account (or included with Atlas-Auto subscription)
- Updated monthly as new patterns are validated

**BYO option:**
- User sets `RAG_ENDPOINT` and `RAG_API_KEY` in config
- Any OpenAI-compatible embeddings API works
- `script.py rag-init --provider qdrant --endpoint https://your-db.example.com`
- `script.py rag-populate --source .taskmaster/` — index your own project history

**Graceful degradation (as always):**
1. Hosted RAG available → use it (best experience)
2. BYO RAG configured → use it
3. Neither → skip RAG, skill works fine without it (just no pattern recommendations)

**Pricing tier:**
- Free: no RAG (skill works perfectly without it)
- Atlas-Auto: includes hosted RAG access
- BYO: free to connect your own (no Atlas AI dependency)

---

## Distribution: Dual-Path (install.sh + plugin marketplace)

Plugin marketplace spec is unstable. Ship BOTH:
- `install.sh` — proven, works now, 220 cloners using it
- `marketplace.json` — future-proofing for when marketplace stabilizes
- `/plugin marketplace add anombyte93/prd-taskmaster` — for early adopters
- Don't deprecate install.sh until marketplace is stable

---

## Onboarding: Anti-Wizard (Zero Questions on First Run)

Research confirms 30-75% abandon at API key steps. Devs hate wizards.

**First run: zero config questions.** Auto-detect everything. Start discovery immediately.
**Post-value moment: show "Capabilities Unlocked"** after PRD is generated.
**Mode D: visually separate as ★ AUTONOMOUS MODE** — exclusive, not listed with A/B/C.

Config is WRITTEN automatically by `script.py detect-providers`. User never sees it.
If something can't be auto-detected, ask ONCE at the moment it's needed (just-in-time), not upfront.

---

## Growth Sequencing (informed by real data)

**Current state (proven by traffic data):**
- 220 unique cloners / 14 days
- 1013 unique visitors / 14 days
- 595 organic Google uniques
- Star growth: 9→6→13→46→44→54/month (accelerating)
- ChatGPT + Claude.ai referring users (AI distribution)

**Phase 1: Ship v4 free core (weeks 1-4)**
- Strip to core, compose execution, zero-config
- Convert to plugin format (dual-path)
- Seed GitHub issues + Discussions
- Demo video (2-min "idea → validated PRD → tasks")
- Target: 500 stars, 50+ issues, 500+ cloners/14d

**Phase 2: Grow the base (weeks 5-12)**
- Submit to awesome-claude-code lists
- Reddit/HN launch post with real metrics
- Optimize README for AI readability (LLMs are referring users)
- Target: 1000 stars, 100+ weekly cloners

**Phase 3: Launch premium (weeks 13+, only after base is 10x)**
- Only when 2000+ cloners/month sustained
- CDD + ralph-loop + doubt as premium companion plugin
- Side-by-side proof baked into the free tier (show what premium gives)
- Contact TaskMaster team re: partnership
- Target: 5% conversion = 100+ premium users

**DO NOT build premium before Phase 2 is complete.** Design the architecture now. Build it when the audience is there.

---

## Real Metrics Dashboard (for README)

```
📊 Last 14 days (auto-updated):
  1,013 unique visitors | 220 clones | 54 stars this month
  
  Top referrers: Google (595), Reddit (185), ChatGPT (16)
  Growth: 9→46→54 stars/month (6x acceleration)
```

---

---

## Website: atlas-ai.au Complete Rewrite

**atlas-ai.au becomes the product home for prd-taskmaster + Atlas-Auto.**

Designed with Google Stitch MCP → Claude Code pipeline. Pantone brand palette (from CLAUDE.md).

### Site Architecture

```
atlas-ai.au/
├── / (hero)              — "Idea → Validated PRD → Execution. Zero config."
│                            Demo video embed, install one-liner, star count
├── /prd-taskmaster       — Product page for the free core
│                            Features, how it works, comparison table
├── /atlas-auto           — Premium product page
│                            Walk-away demo, CDD explanation, proof artifacts
│                            Side-by-side: free vs premium results
├── /pricing              — Free / Atlas-Auto / Enterprise
│                            Stripe checkout integration
├── /docs                 — Getting started, API reference, pattern library
│                            Hosted from GitHub or dedicated docs site
├── /blog                 — Launch posts, case studies, pattern recipes
└── /community            — Links to GitHub Discussions, Discord (future)
```

### Brand Palette (Pantone, from CLAUDE.md)

| Role | Pantone | Hex | Usage |
|------|---------|-----|-------|
| Primary | Pantone 2985 C | #5BC2E7 | CTAs, links, highlights |
| Dark | Pantone Black 6 C | #101820 | Text, backgrounds |
| Accent | Pantone 7548 C | #FFC72C | Premium/Atlas-Auto highlights |
| Success | Pantone 7723 C | #43B02A | Checkmarks, validation pass |
| Warning | Pantone 1495 C | #FF8200 | Alerts |
| Error | Pantone 1797 C | #CB333B | Errors |

### Design with Google Stitch

1. Design pages in Stitch with text prompts using brand palette
2. Export DESIGN.md + design tokens
3. Claude Code generates React/Next.js components from tokens
4. Deploy to Vercel (atlas-ai.au already pointed there)

### SEO Strategy

**Target keywords:**
- "AI PRD generator" / "generate PRD with AI"
- "TaskMaster setup" / "task-master-ai PRD"
- "Claude Code PRD" / "Claude Code task management"
- "AI product requirements document"
- "automated PRD generation tool"

**SEO assets:**
- README optimized for LLM readability (AI is a referrer — 64 views from ChatGPT)
- Structured data (JSON-LD) on product pages
- Blog posts targeting long-tail: "How to generate a PRD with Claude Code"
- Open Graph meta for social sharing (Twitter/X, LinkedIn, Reddit)
- Demo video on YouTube (SEO + viral potential)

**AI SEO (new channel):**
- ChatGPT and Claude.ai are already referring users (proven by traffic data)
- Optimize first paragraph of README for LLM consumption
- Add structured "what is this" section that LLMs can quote directly
- Ensure install instructions are copy-pasteable from LLM responses

---

## Stripe Integration: Premium Payments

**Atlas-Auto and premium addons are paid via Stripe Checkout.**

### Pricing Tiers

| Tier | Price | Includes |
|------|-------|---------|
| Free | $0 | Core prd-taskmaster (PRD gen + validation + TaskMaster setup + Modes A/B/C) |
| Atlas-Auto | $29/month | Atlas-Auto execution + CDD + /question research + hosted RAG + telemetry dashboard |
| Enterprise | Custom | BYO vector DB + custom patterns + team analytics + priority support |

### Payment Flow

```
User selects Atlas-Auto on atlas-ai.au/pricing
  │
  ├→ Stripe Checkout session created
  │   - Product: atlas-auto-monthly
  │   - Price: $29/month
  │   - Trial: 7-day free trial
  │
  ├→ On success: Stripe webhook → Atlas AI backend
  │   - Generate license key
  │   - Store in customer record
  │   - Email license key to user
  │
  └→ User enters license key in prd-taskmaster config:
      script.py activate --license ATLAS-XXXX-XXXX
      
      License stored in ~/.config/prd-taskmaster/license.json
      detect-capabilities checks license → unlocks premium skills
```

### License Verification (in script.py)

```python
# script.py new command
script.py verify-license

# Checks:
# 1. ~/.config/prd-taskmaster/license.json exists
# 2. License key format valid
# 3. API call to atlas-ai.au/api/verify (cached 24h)
# 4. Returns: { "valid": true, "tier": "atlas-auto", "expires": "2027-04-08" }

# Graceful degradation: if API unreachable, use cached result
# Never block the user from using free features
```

### Stripe Products (to create)

| Product | Price ID | Mode | Trial |
|---------|----------|------|-------|
| Atlas-Auto Monthly | atlas_auto_monthly | subscription | 7 days |
| Atlas-Auto Annual | atlas_auto_annual | subscription | 14 days |
| Enterprise | custom | invoice | — |

### atlas-session MCP Integration

The `atlas-session` MCP already has Stripe tools:
- `stripe_create_checkout` — create checkout session
- `stripe_validate_customer` — verify customer
- `stripe_webhook` — handle payment events
- `stripe_refresh_license` — refresh license cache

These can power the entire payment flow without building custom Stripe integration.

---

*Generated: 2026-04-08*
*Status: PENDING APPROVAL — All research complete, all agents merged*
*Forge Score: 90 (Full mode)*
*Research: 40+ Perplexity queries, 5 sub-agents, GitHub traffic API, source code analysis*
