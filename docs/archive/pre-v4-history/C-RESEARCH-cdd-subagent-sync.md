# Research: CDD + Subagent-Driven-Dev + Sync Skill Audits

## CDD (/cdd) — Card-Driven Development

### Current Skill: `~/.claude/skills/cdd/SKILL.md`
Phase-based: ROUTE → GREEN → BLUE → PROVE. YAML cards, evidence collection, tier scoring, stop hook enforcement.

### KEEP
1. Phase flow (ROUTE→GREEN→BLUE→PROVE) — clear lifecycle
2. Evidence-first verification — every test needs proof
3. YAML cards as canonical source of truth (not Trello, not JSON)
4. Stop hook enforcement — can't exit without complete evidence
5. Tier scoring for prioritization

### DISCARD  
1. Software-only test assumptions — "tests pass" doesn't apply to pentest/business
2. Overly strict enforcement that causes infinite loops
3. Trello integration complexity (optional projection, not core)
4. TDD mandate in BLUE phase

### ADD
1. Domain-agnostic verification — pentest: "finding confirmed", marketing: "KPI hit", learning: "skill demonstrated"
2. Risk-proportionate evidence — critical cards need more proof than trivial ones
3. Timeout/escape hatch for enforcement — max iterations before escalating
4. Given-When-Then format for machine-verifiable criteria
5. Structured output schema for AI consumption (JSON results with pass/fail + evidence links)

### DEPENDENCIES
- Stop hook (cdd-evidence-gate)
- YAML schema files
- Discord for orchestrator approval
- phases/ directory with 4 phase files
- schemas/ directory

---

## Subagent-Driven-Dev

### Current Skill: `superpowers/5.0.7/skills/subagent-driven-development/SKILL.md`
Fresh subagent per task, two-stage review (spec compliance + code quality), TodoWrite tracking.

### KEEP
1. Fresh context per task — prevents context pollution
2. Two-stage review (spec then quality) — research says 2 passes is optimal
3. Implementer prompt template — well-structured briefing
4. Task independence — each task can be verified alone
5. TodoWrite integration for progress tracking

### DISCARD
1. Code-only focus — "implementer" assumes software
2. Hardcoded reviewer prompts that assume code files
3. Assumption tasks are always independent (some have dependencies)
4. No failure recovery — if subagent fails, no retry/skip/escalate pattern

### ADD
1. Domain-agnostic task dispatch — "executor" not "implementer"
2. Failure recovery: retry (transient) → skip (optional) → escalate (blocked)
3. Dependency-aware execution order — respect task graph
4. Parallel execution where tasks are independent
5. CDD integration — verify against cards after each task
6. Non-code artifact types — reports, findings, documents, not just code files

### DEPENDENCIES
- Agent tool for subagent dispatch
- implementer-prompt.md, spec-reviewer-prompt.md, code-quality-reviewer-prompt.md
- TodoWrite for tracking
- Git for commits (code-focused)
- Plan document as input (from writing-plans)

---

## Sync (/sync)

### Current Skill: `~/.claude/skills/sync/SKILL.md`
Silent save-point: updates session-context files, MEMORY.md, capability inventory. Mutex-protected.

### KEEP
1. Silent execution — zero questions, zero delay
2. Mutex file locking (flock) — prevents concurrent corruption
3. Append-only policy — never delete, mark stale complete
4. Edit-only (not Write) — prevents accidental overwrite
5. Speed over perfection — rough sync beats no sync

### DISCARD
1. atlas-session MCP dependency for capability inventory (`session_capability_inventory`)
2. Overly complex archive structure
3. MEMORY.md update that requires MCP

### ADD
1. Derive what you can from git — don't store what git log tells you
2. Minimal viable state: soul purpose, active tasks, key decisions, blockers
3. Drop full conversation replay — compact summary only
4. Version field in context files for schema evolution
5. Export-friendly: context files should be readable by any tool (pure markdown)

### DEPENDENCIES
- session-context/ directory with 4 files
- MEMORY.md (auto memory system)
- flock for mutex
- atlas-session MCP (TO REMOVE)
- TZ=Australia/Perth for timestamps

---

## Cross-Cutting Findings

### All 3 skills share these issues:
1. **Software-only assumptions** — all assume code/tests/git as the domain
2. **No failure recovery** — none handle "what if this step fails"
3. **No progressive refinement** — all assume upfront-complete input
4. **Dependencies on external systems** — MCP, Trello, specific file paths

### Design principles for ALL forged replacements:
1. Domain-agnostic — work for any goal
2. Failure recovery built-in — retry/skip/escalate
3. Minimal dependencies — no MCP required, no external services required
4. Evidence-proportionate — more proof for high-risk, less for trivial
5. Machine-readable outputs — structured JSON/YAML for pipeline consumption
