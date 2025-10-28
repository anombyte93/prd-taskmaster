# PRD-Taskmaster: AI-Generated Product Requirements Documents

> **Comprehensive PRD generation optimized for AI-assisted development workflows**

[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![Status: Beta](https://img.shields.io/badge/Status-Beta-orange)]()

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

### Option A: Claude Code CLI (Recommended)

**Prerequisites:**
- Claude Code CLI installed ([installation guide](https://docs.claude.com/en/docs/claude-code/installation))
- Git

**Install the skill:**

```bash
# Clone to your Claude Code skills directory
cd ~/.claude/skills
git clone https://github.com/anombyte93/prd-taskmaster.git
```

**Verify installation:**

```bash
# Start Claude Code in any project
claude

# In the chat, type:
# "I want a PRD for adding dark mode"
```

Claude Code should recognize the skill and activate it automatically!

**Troubleshooting:**
- If skill doesn't activate, check it's in `~/.claude/skills/prd-taskmaster/`
- Verify `SKILL.md` exists in that directory
- Try restarting Claude Code
- Check skill is enabled: Look for the skill description when typing "/help" or similar commands

---

### Option B: Codex (Untested)

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

**Verify installation:**

Ask Codex:
```
What would you do if I told you to generate a PRD?
```

Confirm it outputs something similar to the workflow described in this README.

**Using the generated codex.md:**

When the skill generates a PRD for your project, it will ask if you're using Codex:
- If yes: Creates both `CLAUDE.md` and `codex.md` in your project root
- If no: Creates only `CLAUDE.md`

The `codex.md` file guides Codex to follow TDD workflow, use agents, and maintain quality gates throughout development.

**Troubleshooting:**
- Check you cloned to the correct directory
- Check you ran Codex in the `prd-taskmaster` directory
- Run `/init` to ensure Codex reads `SKILL.md`
- Verify `SKILL.md` exists in the directory

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

The skill will:

1. **Ask you 12+ detailed questions**
   - What problem are you solving?
   - Who's the target user?
   - What are success metrics?
   - What's the tech stack?
   - Any constraints or dependencies?

2. **Analyze your codebase** (if applicable)
   - Scans for related code
   - Identifies integration points
   - References existing patterns

3. **Generate a comprehensive PRD**
   - All essential sections included
   - Task breakdown hints
   - Complexity estimates

4. **Set up taskmaster integration**
   - Creates `.taskmaster/` directory
   - Places PRD in correct location
   - Updates `.gitignore`

5. **Validate everything**
   - 13 automated quality checks
   - Warns about vague language
   - Scores PRD quality

6. **Show you next steps**
   - Summary of what was created
   - Suggestions for taskmaster usage
   - Open questions to address

### First-Time Tips

**Be detailed in your answers!** The more context you provide, the better the PRD.

**Example good answer:**
> "We need 2FA because we're seeing 150 security incidents per month from compromised accounts. Target users are enterprise customers who require SOC2 compliance. Success = reduce incidents to <10/month and meet SOC2 requirements."

**Example too-vague answer:**
> "We need 2FA for security."

**Don't worry about perfect answers** - the skill will ask follow-ups if needed!

## What You Get

### 📄 Comprehensive PRD

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

### 🗂️ Taskmaster Integration

Automatically sets up:

```
.taskmaster/
├── docs/
│   ├── prd.md              # Your generated PRD
│   └── architecture.md     # Placeholder for architecture docs
├── tasks/
│   └── .gitkeep
├── notes/
│   └── .gitkeep
└── .gitignore              # Updated to exclude taskmaster artifacts
```

### 🤖 CLAUDE.md / codex.md - TDD Workflow Guide

Generates a comprehensive workflow file in your project root that guides Claude Code/Codex to:

- **Follow TDD by default** - Write tests first, then implementation
- **Use blind-validator agent** - Validate against PRD without seeing code
- **Execute parallel tasks** - Run independent tasks simultaneously
- **Leverage agents** - For validation, exploration, and context optimization
- **Enforce quality gates** - Automated validation before marking tasks complete
- **Follow taskmaster best practices** - Optimal workflow for AI-assisted development

**Key sections:**
- TDD workflow (RED → GREEN → REFACTOR cycle)
- Agent usage guidelines (when/how to use each agent type)
- Parallel task execution strategies
- Validation & quality gates
- Tool preferences & context optimization
- Project-specific configuration (tech stack, test commands, etc.)

**File naming:**
- **Claude Code:** Creates `CLAUDE.md` (read automatically by Claude Code)
- **Codex:** Creates `codex.md` (read by Codex when initialized with `/init`)
- The skill will ask which tool you're using and create the appropriate file(s)
- Both files have identical content
- Includes instructions for keeping them in sync if you use both tools

This ensures consistent, high-quality development across your entire project!

### ✅ Quality Validation

13 automated checks ensure:
- All required sections are present
- Requirements are testable (not vague)
- Success metrics are SMART
- Technical considerations address architecture
- Task breakdown hints are included
- Dependencies are mapped

### 📊 Example Output

```
📄 PRD Created: .taskmaster/docs/prd.md
🤖 CLAUDE.md Generated: Project root (TDD workflow guide)
   + codex.md (if you're using Codex)

📊 Overview:
  - Feature: Two-Factor Authentication
  - Complexity: Medium
  - Estimated Effort: 26 tasks, ~119 hours
  - Key Goal: Reduce security incidents from 150/month to <10/month

🎯 Key Requirements:
  1. REQ-001: TOTP/SMS 2FA support
  2. REQ-002: Backup codes for recovery
  3. REQ-003: Login flow integration

🔧 Technical Highlights:
  - Architecture: Auth service + Redis for sessions
  - Integration: Twilio for SMS delivery
  - Database: 2 new tables (user_2fa, backup_codes)

⚠️ Quality Validation: 58/60 (EXCELLENT ✅)
  ✅ All required elements present
  ⚠️ 1 minor warning (REQ-007 has vague language)

📋 Suggested Task Breakdown:
  - Phase 1: 3 tasks (foundation)
  - Phase 2: 8 tasks (core features)
  - Phase 3: 5 tasks (testing)

🚀 Next Steps:
  1. Review PRD: .taskmaster/docs/prd.md
  2. Install taskmaster: npm install -g task-master-ai
  3. Initialize: taskmaster init
  4. Generate tasks: taskmaster generate
```

## Who Is This For?

### Perfect For You If:

- ✅ You use AI-assisted development workflows (Claude, Cursor, etc.)
- ✅ You want to use Taskmaster or similar task breakdown tools
- ✅ You're building features/products and need comprehensive specs
- ✅ You prefer detailed planning before coding
- ✅ You're tired of writing PRDs manually

### Maybe Not For You If:

- ❌ You prefer writing PRDs entirely yourself
- ❌ You don't use AI development tools
- ❌ You prefer minimal documentation
- ❌ You work in a strict corporate environment with specific PRD templates

## Features

### 🤖 Intelligent Discovery

Asks smart questions:
- What problem are you solving?
- Who's the user?
- What's the tech stack?
- What are success metrics?
- Timeline expectations?

### 🔍 Codebase-Aware

If you're working in an existing codebase:
- Scans related code
- References specific files
- Ensures consistency with existing patterns
- Identifies integration points

### 📐 Multiple Templates

Choose based on project size:
- **Comprehensive** (default) - Full 12-section PRD
- **Minimal** - Quick template for simple features

### 🎯 Taskmaster-Optimized

Everything taskmaster needs:
- Task breakdown hints
- Complexity estimates
- Dependency mapping
- Acceptance criteria
- Implementation notes

### ✨ Smart Validation

Catches common issues:
- Vague language ("fast", "secure" without specifics)
- Missing acceptance criteria
- Non-testable requirements
- Incomplete technical specs

## How It Works

### The 8-Step Workflow

1. **Discovery** - Ask comprehensive questions
2. **Environment Check** - Look for existing taskmaster setup
3. **Codebase Analysis** - Understand existing code (if applicable)
4. **PRD Generation** - Write comprehensive requirements
5. **Directory Setup** - Create `.taskmaster/` structure
6. **Validation** - Run 13 quality checks
7. **Task Hints** - Suggest breakdowns and dependencies
8. **Presentation** - Show summary and next steps

## Advanced Usage

### Using with Taskmaster

The skill now **automatically detects and prefers MCP** over CLI for seamless integration!

#### Automatic Detection (Recommended)

The skill will automatically:
1. **Detect MCP Task-Master-AI** (if installed in Claude Code)
2. **Fallback to CLI** (if MCP not available but CLI is installed)
3. **Provide installation instructions** (if neither is available)

**With MCP (PREFERRED):**
- ✅ Seamless integration with direct function calls
- ✅ No shell dependency
- ✅ Automatic task initialization, parsing, and expansion
- ✅ Query tasks using MCP tools directly in Claude Code

The skill will automatically:
- Initialize taskmaster project structure
- Parse your PRD to generate tasks
- Expand all tasks into subtasks
- No manual CLI commands needed!

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

**Without Taskmaster:**
- Skill generates manual task files in `.taskmaster/tasks/`
- Provides installation instructions for MCP or CLI
- You can still follow the PRD and task files manually

### Customizing Templates

Edit templates in `templates/` directory:
- `taskmaster-prd-comprehensive.md` - Full template
- `taskmaster-prd-minimal.md` - Quick template

### Manual Validation

Use the validation checklist:
```bash
cat reference/validation-checklist.md
```

## Files & Structure

```
prd-taskmaster/
├── SKILL.md                              # Main skill (480 lines)
├── PUBLIC_README.md                      # This file
├── README.md                             # Developer documentation
├── templates/
│   ├── taskmaster-prd-comprehensive.md   # Full PRD template
│   └── taskmaster-prd-minimal.md         # Quick template
├── scripts/
│   └── setup-taskmaster.sh               # Directory setup script
└── reference/
    ├── taskmaster-integration-guide.md   # Taskmaster best practices
    └── validation-checklist.md           # Quality criteria
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

## License

MIT License - Use freely, modify as needed, share improvements if you want.

## Acknowledgments

**Built with:**
- Claude Code (obviously)
- Research from Product School, Atlassian, Aha.io, Leanware
- Taskmaster AI documentation
- Lessons learned from shipping features

**Philosophy:**
- LEARN → PRACTICE → MASTER methodology
- Impact-weighted decision making
- Evidence-based evaluation
- Quality over speed

## Support & Contact

- **Issues:** [GitHub Issues](https://github.com/anombyte93/prd-taskmaster/issues)
- **Discussions:** [GitHub Discussions](https://github.com/anombyte93/prd-taskmaster/discussions)
- **Questions:** Open an issue with the "question" label

## Version History

- **v1.0** (2025-01-22) - Initial public release
  - Comprehensive PRD generation
  - Full taskmaster integration
  - Automated validation (13 checks)
  - Impact-weighted evaluation methodology

---

**Made with Claude Code** | **Status: Beta** | **Feedback Welcome**

*Planning is 95% of the work. Start with a solid PRD.*

## What's New in v2.0 (Top 5 Enhancements)

### 1. Real DateTime Tracking
- Precise UTC timestamps for all tasks/subtasks
- Automatic duration calculation
- JSON state persistence
- Compare actual vs estimated time

### 2. Instant Rollback Command
- Type "rollback to task X" any time during execution
- Reverts to any checkpoint tag
- Backs up current work before rollback
- Safety confirmations

### 3. Accuracy Learning System
- Analyzes estimated vs actual times
- Calculates adjustment factor
- Recommends estimate improvements
- Learns from your pace

### 4. Security Audit Checklist
- Auto-generated based on your code
- Scans for security patterns
- Standard security checks included
- Automated scan suggestions

### 5. Auto-Resume After Crash
- Detects incomplete work from previous session
- Offers multiple resume points
- Continues exactly where crashed
- No work lost

All enhancements work seamlessly with MCP or CLI integration!

