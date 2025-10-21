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

## Quick Start

### Installation

1. **Install as a Claude Code skill:**
   ```bash
   # Clone to your Claude Code skills directory
   cd ~/.claude/skills
   git clone https://github.com/anombyte93/prd-taskmaster.git
   ```

2. **Verify installation:**
   ```bash
   # Open Claude Code and type:
   # "I want a PRD for adding dark mode"
   ```

### Basic Usage

Just tell Claude you want a PRD:

```
"I want a PRD for [your feature/product]"
```

**Examples:**
- "I want a PRD for adding two-factor authentication"
- "Create product requirements for a user dashboard"
- "Write a PRD for integrating with Stripe payments"

The skill will:
1. Ask you questions (be as detailed as you can!)
2. Analyze your codebase (if applicable)
3. Generate a comprehensive PRD
4. Set up taskmaster integration
5. Validate everything
6. Show you what to do next

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

```bash
# After PRD is generated:
npm install -g task-master-ai
cd your-project
taskmaster init
taskmaster generate    # Uses your PRD
taskmaster start       # Begin implementation
```

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
