# PRD-Taskmaster: AI-Generated Product Requirements Documents

> **Comprehensive PRD generation optimized for AI-assisted development workflows**

[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://github.com/anombyte93/prd-taskmaster)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/anombyte93/prd-taskmaster/blob/main/LICENSE)
[![Status: Beta](https://img.shields.io/badge/Status-Beta-orange)](https://github.com/anombyte93/prd-taskmaster)
[![GitHub stars](https://img.shields.io/github/stars/anombyte93/prd-taskmaster)](https://github.com/anombyte93/prd-taskmaster/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/anombyte93/prd-taskmaster)](https://github.com/anombyte93/prd-taskmaster/commits)
[![GitHub issues](https://img.shields.io/github/issues/anombyte93/prd-taskmaster)](https://github.com/anombyte93/prd-taskmaster/issues)

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/anombyte93/prd-taskmaster/master/install.sh | bash
```

This installs the skill to `~/.claude/skills/prd-taskmaster/`. Run the same command to upgrade -- the installer checks for updates and only overwrites when there are changes.

**Check for updates:**
```bash
bash ~/.claude/skills/prd-taskmaster/install.sh --check-update
```

## What is This?

A Claude Code skill that generates **detailed, engineer-focused Product Requirements Documents (PRDs)** designed to work seamlessly with AI task breakdown tools like Taskmaster.

Think of it as your AI product manager that asks the right questions, writes comprehensive specs, and sets you up for successful implementation.

## Why You Might Want This

### The Problem

You have an idea for a feature or product, but:
- Writing comprehensive PRDs takes hours
- You're not sure what details to include
- You want to use AI task breakdown tools (like Taskmaster) but they need detailed requirements
- Vague specs lead to vague tasks, which lead to poor implementations

### The Solution

This skill:
1. **Asks 12+ detailed questions** to extract everything from your brain
2. **Generates a comprehensive PRD** with all the sections engineers need
3. **Sets up taskmaster integration** with proper directory structure
4. **Validates quality** with automated checks (13 different validations)
5. **Suggests task breakdowns** with complexity estimates and dependencies

**Result:** You go from "I have an idea" to "I have a complete, validated PRD ready for AI task generation" in minutes.

## Installation

This skill works with **Claude Code CLI** and **Codex** (VS Code extension). Choose your tool below:

### Option A: One-Liner (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/anombyte93/prd-taskmaster/master/install.sh | bash
```

The installer handles everything: cloning, updating, and placing files in `~/.claude/skills/prd-taskmaster/`.

### Option B: Manual Clone

```bash
cd ~/.claude/skills
git clone https://github.com/anombyte93/prd-taskmaster.git
```

### Option C: Codex (Untested)

**Prerequisites:**
- Codex ([see](https://github.com/openai/codex/blob/main/README.md))
- Git

**Install the skill:**

```bash
# Clone to where you want to run codex
cd ~/<wherever>
git clone https://github.com/anombyte93/prd-taskmaster.git
cd prd-taskmaster
```

**Configure Codex to find the skill:**

1. Run Codex in the `prd-taskmaster` directory
2. Initialize Codex: `/init`
3. Codex will read `SKILL.md` and understand how to generate PRDs

**Using the generated codex.md:**

When the skill generates a PRD for your project, it will ask if you're using Codex:
- If yes: Creates both `CLAUDE.md` and `codex.md` in your project root
- If no: Creates only `CLAUDE.md`

The `codex.md` file guides Codex to follow TDD workflow, use agents, and maintain quality gates throughout development.

**Verify installation:**

```bash
# Start Claude Code in any project
claude

# In the chat, type:
# "I want a PRD for adding dark mode"
```

Claude Code should recognize the skill and activate it automatically.

**Troubleshooting:**
- If skill doesn't activate, check it's in `~/.claude/skills/prd-taskmaster/`
- Verify `SKILL.md` exists in that directory
- Try restarting Claude Code

---

## Quick Start Guide

### Basic Usage

Once installed, just tell Claude/Codex you want a PRD:

```
"I want a PRD for [your feature/product]"
```

**Activation phrases:**
- "I want a PRD for adding two-factor authentication"
- "Create product requirements for a user dashboard"
- "Write a PRD for integrating with Stripe payments"
- "Generate requirements for building a dark mode feature"

### What Happens Next

The skill runs a 12-step workflow:

1. **Checks for existing work** - Detects previous PRDs and crash state for auto-resume
2. **Offers options** - Execute, update, replace, or review existing PRDs
3. **Detects Taskmaster** - MCP or CLI, blocks if neither is installed
4. **Asks 12+ detailed questions** - Problem, users, metrics, tech stack, constraints
5. **Initializes Taskmaster** - Sets up `.taskmaster/` directory structure
6. **Generates a comprehensive PRD** - From templates, filled with your answers
7. **Validates quality** - 13 automated checks with a letter grade
8. **Parses and expands tasks** - Breaks PRD into actionable tasks with subtasks
9. **Inserts user test checkpoints** - Every 5 tasks, a manual validation point
10. **Sets up tracking scripts** - 5 scripts for time tracking, rollback, accuracy learning, security audit, and execution state
11. **Generates CLAUDE.md** - TDD workflow guide for your project (if one doesn't exist)
12. **Hands off or executes** - Your choice: command reference or autonomous execution in 4 modes

### First-Time Tips

**Be detailed in your answers!** The more context you provide, the better the PRD.

**Example good answer:**
> "We need 2FA because we're seeing 150 security incidents per month from compromised accounts. Target users are enterprise customers who require SOC2 compliance. Success = reduce incidents to <10/month and meet SOC2 requirements."

**Example too-vague answer:**
> "We need 2FA for security."

**Don't worry about perfect answers** - the skill will ask follow-ups if needed!

## What You Get

### Comprehensive PRD

A complete product requirements document with:

- **Executive Summary** - Quick overview
- **Problem Statement** - User pain points & business impact
- **Goals & Metrics** - SMART success criteria
- **User Stories** - With acceptance criteria
- **Functional Requirements** - Detailed, testable specs
- **Technical Considerations** - Architecture, data models, APIs
- **Task Breakdown Hints** - For AI task generation
- **Dependencies** - What depends on what
- **Out of Scope** - What you're NOT building

### Taskmaster Integration

Automatically sets up:

```
.taskmaster/
├── docs/
│   ├── prd.md              # Your generated PRD
│   └── architecture.md     # Placeholder for architecture docs
├── tasks/
│   └── .gitkeep
├── scripts/
│   ├── track-time.py       # DateTime tracking per task
│   ├── rollback.sh         # Rollback to any checkpoint
│   ├── learn-accuracy.py   # Estimate vs actual analysis
│   ├── security-audit.py   # Auto-generated security checks
│   └── execution-state.py  # Crash recovery state
├── notes/
│   └── .gitkeep
└── .gitignore              # Updated to exclude taskmaster artifacts
```

### CLAUDE.md / codex.md - TDD Workflow Guide

Generates a comprehensive workflow file in your project root that guides Claude Code/Codex to:

- **Follow TDD by default** - Write tests first, then implementation
- **Use blind-validator agent** - Validate against PRD without seeing code
- **Execute parallel tasks** - Run independent tasks simultaneously
- **Leverage agents** - For validation, exploration, and context optimization
- **Enforce quality gates** - Automated validation before marking tasks complete
- **Follow taskmaster best practices** - Optimal workflow for AI-assisted development

**File naming:**
- **Claude Code:** Creates `CLAUDE.md` (read automatically by Claude Code)
- **Codex:** Creates `codex.md` (read by Codex when initialized with `/init`)
- The skill will ask which tool you're using and create the appropriate file(s)

### Quality Validation

13 automated checks ensure:
- All required sections are present
- Requirements are testable (not vague)
- Success metrics are SMART
- Technical considerations address architecture
- Task breakdown hints are included
- Dependencies are mapped

Grading scale: EXCELLENT (91%+), GOOD (83-90%), ACCEPTABLE (75-82%), NEEDS_WORK (<75%).

### Example Output

```
PRD Created: .taskmaster/docs/prd.md
CLAUDE.md Generated: Project root (TDD workflow guide)

Overview:
  - Feature: Two-Factor Authentication
  - Complexity: Medium
  - Estimated Effort: 26 tasks, ~119 hours
  - Key Goal: Reduce security incidents from 150/month to <10/month

Key Requirements:
  1. REQ-001: TOTP/SMS 2FA support
  2. REQ-002: Backup codes for recovery
  3. REQ-003: Login flow integration

Technical Highlights:
  - Architecture: Auth service + Redis for sessions
  - Integration: Twilio for SMS delivery
  - Database: 2 new tables (user_2fa, backup_codes)

Quality Validation: 58/60 (EXCELLENT)
  - All required elements present
  - 1 minor warning (REQ-007 has vague language)

Suggested Task Breakdown:
  - Phase 1: 3 tasks (foundation)
  - Phase 2: 8 tasks (core features)
  - Phase 3: 5 tasks (testing)

Next Steps:
  1. Review PRD: .taskmaster/docs/prd.md
  2. Generate tasks: taskmaster generate
  3. Begin implementation: taskmaster next-task
```

## Who Is This For?

### Perfect For You If:

- You use AI-assisted development workflows (Claude, Cursor, etc.)
- You want to use Taskmaster or similar task breakdown tools
- You're building features/products and need comprehensive specs
- You prefer detailed planning before coding
- You're tired of writing PRDs manually

### Maybe Not For You If:

- You prefer writing PRDs entirely yourself
- You don't use AI development tools
- You prefer minimal documentation
- You work in a strict corporate environment with specific PRD templates

## Features

### Intelligent Discovery

Asks smart questions across four categories:
- **Essential (5):** Problem, users, solution, metrics, constraints
- **Technical (4):** Codebase, tech stack, integrations, performance
- **TaskMaster-specific (3):** Experience, complexity, timeline
- **Open-ended (1):** Edge cases, additional context

### Codebase-Aware

If you're working in an existing codebase:
- Scans related code
- References specific files
- Ensures consistency with existing patterns
- Identifies integration points

### Multiple Templates

Choose based on project size:
- **Comprehensive** (default) - Full 12-section PRD
- **Minimal** - Quick template for simple features

### Taskmaster-Optimized

Everything taskmaster needs:
- Task breakdown hints
- Complexity estimates
- Dependency mapping
- Acceptance criteria
- Implementation notes

### Smart Validation

Catches common issues:
- Vague language ("fast", "secure" without specifics)
- Missing acceptance criteria
- Non-testable requirements
- Incomplete technical specs

### Auto-Resume After Crash

- Detects incomplete work from previous session
- Offers multiple resume points (last subtask, current task, last checkpoint, fresh start)
- Continues exactly where you left off
- No work lost

## How It Works

### The 12-Step Workflow

| Step | Name | What Happens |
|------|------|------|
| 1 | Preflight & Resume | Detects existing state, offers crash recovery |
| 2 | Detect Existing PRD | Offers execute/update/replace/review options |
| 3 | Detect Taskmaster | Finds MCP or CLI, blocks if neither installed |
| 4 | Discovery Questions | 12+ questions across 4 categories |
| 5 | Initialize Taskmaster | Creates `.taskmaster/` directory structure |
| 6 | Generate PRD | Fills template with your answers |
| 7 | Validate Quality | 13 automated checks, letter grade |
| 8 | Parse & Expand Tasks | Breaks PRD into tasks with subtasks |
| 9 | Insert User Test Tasks | Manual checkpoints every 5 tasks |
| 10 | Setup Tracking Scripts | 5 scripts for time, rollback, accuracy, security, state |
| 10.5 | Generate CLAUDE.md | TDD workflow guide (skips if exists) |
| 11 | Choose Next Action | Handoff with commands or autonomous execution |
| 12 | Summary & Start | Display summary, begin work or exit |

### Autonomous Execution Modes

If you choose autonomous execution at Step 11, pick a mode:

| Mode | Behavior |
|------|----------|
| **Sequential to Checkpoint** | Tasks one-by-one, stops at each USER-TEST |
| **Parallel to Checkpoint** | Up to 3 concurrent independent tasks, stops at USER-TEST |
| **Full Autonomous** | Up to 5 concurrent, auto-completes USER-TEST checkpoints |
| **Manual Control** | You decide each task: "next task", "task 5", "parallel 3,4" |

All modes include: datetime tracking, git branching per task, checkpoint tags, rollback support, and progress logging.

## Advanced Usage

### Using with Taskmaster

The skill **automatically detects and prefers MCP** over CLI for seamless integration.

#### Automatic Detection (Recommended)

The skill will automatically:
1. **Detect MCP Task-Master-AI** (if installed in Claude Code)
2. **Fallback to CLI** (if MCP not available but CLI is installed)
3. **Block with installation instructions** (if neither is available)

**With MCP (Preferred):**
- Seamless integration with direct function calls
- No shell dependency
- Automatic task initialization, parsing, and expansion
- Query tasks using MCP tools directly in Claude Code

**With CLI (Fallback):**
```bash
# After PRD is generated:
npm install -g task-master-ai
cd your-project
taskmaster init
taskmaster parse-prd --input .taskmaster/docs/prd.md
taskmaster expand-all --research
taskmaster next-task  # Begin implementation
```

### Customizing Templates

Edit templates in `templates/` directory:
- `taskmaster-prd-comprehensive.md` - Full template
- `taskmaster-prd-minimal.md` - Quick template

### Manual Validation

Use the validation checklist:
```bash
cat ~/.claude/skills/prd-taskmaster/reference/validation-checklist.md
```

Or re-run validation on any PRD:
```bash
python3 ~/.claude/skills/prd-taskmaster/script.py validate-prd --input .taskmaster/docs/prd.md
```

## Architecture: The Codification Pattern

v3.0 introduced a clean separation between **AI judgment** and **deterministic operations**:

```
SKILL.md (303 lines)          script.py (37KB)
  AI decides WHAT to do   -->   Script does HOW to do it
  Questions, content,           File I/O, validation,
  decisions, recommendations    calculations, templates
```

**SKILL.md** contains the workflow logic, decision points, and instructions for AI judgment calls -- what questions to ask, how to interpret answers, when to recommend fixes.

**script.py** handles everything deterministic -- preflight checks, template loading, PRD validation (13 checks), task calculations, script generation, progress logging. Every command outputs JSON, making the interface clean and predictable.

This pattern reduced SKILL.md from 1,343 lines to 303 lines (78% reduction) while making the skill more reliable -- deterministic operations don't depend on AI interpretation.

### script.py Subcommands

| Command | Purpose |
|---------|---------|
| `preflight` | Detect existing state, taskmaster, crash recovery |
| `detect-taskmaster` | Find MCP or CLI installation |
| `init-taskmaster` | Initialize `.taskmaster/` directory |
| `load-template` | Load PRD template (comprehensive or minimal) |
| `validate-prd` | Run 13 quality checks, return score and grade |
| `calc-tasks` | Calculate recommended task count from requirements |
| `gen-test-tasks` | Generate USER-TEST checkpoint definitions |
| `gen-scripts` | Create 5 tracking scripts |
| `log-progress` | Record task completion with timing data |
| `backup-prd` | Backup existing PRD before replacement |

**Interested in this pattern?** The codification approach -- extracting deterministic operations from a SKILL.md into a companion script -- is applicable to any Claude Code skill. A companion skill called `codify` automates this extraction process. It's not published separately yet, but the pattern is straightforward: identify every operation that doesn't require AI judgment, move it to a script that outputs JSON, and call it from SKILL.md.

## Files & Structure

```
prd-taskmaster/
├── SKILL.md                              # AI judgment logic (303 lines)
├── script.py                             # Deterministic operations (37KB)
├── install.sh                            # Curl installer with update checking
├── README.md                             # This file
├── SKILL.md.pre-codify                   # Pre-codification backup (1,343 lines)
├── LICENSE                               # MIT
├── CODE_OF_CONDUCT.md                    # Community standards
├── CONTRIBUTING.md                       # Contribution guide
├── .github/
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
├── templates/
│   ├── taskmaster-prd-comprehensive.md   # Full PRD template
│   ├── taskmaster-prd-minimal.md         # Quick template
│   └── CLAUDE.md.template                # TDD workflow template
├── reference/
│   ├── taskmaster-integration-guide.md   # Taskmaster best practices
│   └── validation-checklist.md           # Quality criteria
└── scripts/
    └── setup-taskmaster.sh               # Directory setup script
```

## Development Approach

### Honest Disclosure

This skill was built using an iterative "vibe-coding" approach:
- Designed multiple variations
- Evaluated with evidence-based scoring
- Validated with test scenarios
- Refined based on impact analysis

**Status:** Beta - Works well for the creator's workflow, but hasn't been extensively tested by others.

### Known Limitations

- Primarily tested for web/API projects
- English only
- Assumes taskmaster workflow
- May ask redundant questions for very simple features
- Validation is helpful but not perfect

### Your Feedback Matters

This is a **living skill**. If you:
- Find bugs or issues
- Have suggestions for improvement
- Want additional templates or patterns
- Need different validation rules

**Please open an issue!** Your real-world usage will make this better.

## Why Share This?

### The Philosophy

> "Planning is 95% of the work. A comprehensive, validated PRD is the foundation of successful implementation."

If you're using AI to help build software, the **quality of your requirements** directly impacts the **quality of your results**.

This skill codifies lessons learned from:
- Writing PRDs manually (painful)
- Using AI task breakdown tools (needs good input)
- Iterating on what makes a "good enough" PRD
- Automating the boring parts

### The Hope

Maybe this helps you:
- Save time on PRD writing
- Improve your planning process
- Get better results from AI task tools
- Ship features more successfully

If it does, great! If not, no worries - maybe you'll fork it and make it better for your needs.

## FAQ

### Q: Do I need Taskmaster to use this?

**A:** No. The PRD is useful on its own. Taskmaster integration is optional.

### Q: Will this work for my project?

**A:** Probably? It's designed for web/API projects but adaptable. Try it and see!

### Q: Can I modify the templates?

**A:** Absolutely! That's encouraged. Edit templates to match your needs.

### Q: What if the PRD quality validation fails?

**A:** The skill will warn you about issues. You can still use the PRD - validation is guidance, not enforcement.

### Q: How long does it take?

**A:** 5-15 minutes depending on how detailed your answers are.

### Q: Is this better than writing PRDs manually?

**A:** Different trade-off. Faster and more comprehensive, but less customized. Your call!

## Contributing

### Ways to Help

1. **Use it and report issues** - Real-world usage is invaluable
2. **Share improvements** - Better templates, validation rules, etc.
3. **Add patterns** - More examples for common project types
4. **Documentation** - Clarify confusing parts

### How to Contribute

```bash
# Fork the repo
# Make your changes
# Test with real projects
# Submit PR with:
#   - What you changed
#   - Why you changed it
#   - How you tested it
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

## License

MIT License - Use freely, modify as needed, share improvements if you want.

## Acknowledgments

**Built with:**
- Claude Code (obviously)
- Research from Product School, Atlassian, Aha.io, Leanware
- Taskmaster AI documentation
- Lessons learned from shipping features

**Philosophy:**
- LEARN, PRACTICE, MASTER methodology
- Impact-weighted decision making
- Evidence-based evaluation
- Quality over speed

## Support & Contact

- **Issues:** [GitHub Issues](https://github.com/anombyte93/prd-taskmaster/issues)
- **Discussions:** [GitHub Discussions](https://github.com/anombyte93/prd-taskmaster/discussions)
- **Questions:** Open an issue with the "question" label

## Version History

- **v3.0** (2025-02-12) - Codification refactor
  - Extracted all deterministic operations into `script.py` (37KB)
  - Reduced SKILL.md from 1,343 lines to 303 lines (78% reduction)
  - All script commands output JSON for clean AI-script interface
  - Added `install.sh` with curl one-liner installer and update checking
  - Added community files: CODE_OF_CONDUCT.md, CONTRIBUTING.md, issue templates
  - Preserved SKILL.md.pre-codify as backup reference

- **v2.0** (2025-02-05) - Feature expansion
  - Real datetime tracking with UTC timestamps and duration calculation
  - Instant rollback to any checkpoint tag
  - Accuracy learning system (estimated vs actual time analysis)
  - Security audit checklist auto-generated from code patterns
  - Auto-resume after crash with multiple recovery points
  - 4 autonomous execution modes (sequential, parallel, full auto, manual)
  - User test checkpoints inserted every 5 tasks
  - MCP-first Taskmaster detection with CLI fallback

- **v1.0** (2025-01-22) - Initial public release
  - Comprehensive PRD generation
  - Full taskmaster integration
  - Automated validation (13 checks)
  - Impact-weighted evaluation methodology

---

**Made with Claude Code** | **Status: Beta** | **Feedback Welcome**

*Planning is 95% of the work. Start with a solid PRD.*
