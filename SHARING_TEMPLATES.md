# Ready-to-Use Sharing Templates

Copy-paste these templates to share your prd-taskmaster skill!

---

## Reddit - r/ClaudeAI

**Title:**
```
Built a Claude Code skill that generates comprehensive PRDs with AI
```

**Post:**
```markdown
I created a skill for Claude Code that generates detailed Product Requirements Documents optimized for AI task breakdown tools like Taskmaster.

## What it does:
- Asks ~12 questions about your feature/product
- Generates a comprehensive PRD with all the sections engineers need
- Validates quality with 13 automated checks
- Sets up taskmaster directory structure automatically
- Suggests task breakdowns with complexity estimates

**Example:** Say "I want a PRD for adding 2FA" and it takes you from idea → validated PRD in ~5 minutes.

Built using "vibe-coding" methodology - works great for my workflow but still in beta. Honest about limitations in the README.

**GitHub:** https://github.com/anombyte93/prd-taskmaster

Would love feedback from the community! What features would you want in a PRD generator?
```

---

## Reddit - r/ProductManagement

**Title:**
```
AI tool for generating comprehensive Product Requirements Documents
```

**Post:**
```markdown
I built a Claude Code skill that automates PRD creation for technical products.

## The Problem:
- Writing comprehensive PRDs takes hours
- Easy to miss critical details
- Hard to ensure requirements are testable
- AI task breakdown tools need detailed specs

## The Solution:
An AI skill that interviews you about your product/feature, then generates a complete PRD with:
- Executive summary & problem statement
- SMART goals & success metrics
- User stories with acceptance criteria
- Functional & non-functional requirements
- Technical considerations & architecture
- Task breakdown hints for implementation

It also validates the PRD with 13 automated checks to catch vague language and missing details.

**Example output:** From "I want to add two-factor auth" → 10-page validated PRD in 5 minutes

**Status:** Beta release - works well but hasn't been extensively tested yet.

**GitHub:** https://github.com/anombyte93/prd-taskmaster

Curious what PMs think - is this useful or overkill? What would make it better?
```

---

## Twitter/X

**Thread:**
```
Built a @AnthropicAI Claude Code skill that generates comprehensive PRDs optimized for AI dev workflows 🧵

1/ Problem: Writing PRDs takes forever, and AI task breakdown tools need detailed requirements to generate good tasks

2/ Solution: AI skill that asks ~12 smart questions, then generates a complete PRD with validation, task hints, and directory setup

3/ Goes from "I have an idea for 2FA" → "validated PRD ready for taskmaster" in 5 mins

4/ Key features:
✅ 13 automated quality checks
✅ Taskmaster integration
✅ Complexity estimates
✅ Dependency mapping
✅ Honest about being beta

5/ Built with "vibe-coding" - works great for my workflow but sharing publicly for feedback

GitHub: https://github.com/anombyte93/prd-taskmaster

What would you want in an AI PRD generator?
```

**Or Single Post:**
```
Built a Claude Code skill that generates comprehensive PRDs optimized for AI dev workflows

"I want 2FA" → validated PRD with 13 quality checks in 5 mins

Beta release, feedback welcome!

https://github.com/anombyte93/prd-taskmaster
```

---

## Hacker News - Show HN

**Title:**
```
Show HN: Claude Code skill for AI-generated PRDs
```

**URL:**
```
https://github.com/anombyte93/prd-taskmaster
```

**Comment (optional but recommended):**
```
I built a Claude Code skill that generates detailed Product Requirements Documents optimized for AI task breakdown.

The motivation: I use AI tools like Taskmaster to break down projects into tasks, but realized "garbage in, garbage out" - vague PRDs lead to vague tasks. Writing comprehensive PRDs manually takes hours.

This skill:
- Asks ~12 detailed questions to extract requirements
- Generates a complete PRD (problem statement, goals, requirements, technical specs, etc.)
- Validates quality with 13 automated checks (catches vague language, missing acceptance criteria, etc.)
- Sets up taskmaster integration automatically
- Suggests task breakdowns with complexity estimates

Built with "vibe-coding" - works well for my workflow but hasn't been tested extensively by others. I'm honest about limitations in the README rather than overselling it.

Example: "I want to add two-factor authentication" → 5 minutes → validated 10-page PRD ready for AI task generation.

Would appreciate feedback! Is this useful? What's missing? What would you change?
```

---

## Dev.to Blog Post

**Title:**
```
How I Built an AI PRD Generator for Claude Code (and Why Planning Matters)
```

**Tags:**
```
#ai #claude #productivity #productmanagement
```

**Post:**
```markdown
# How I Built an AI PRD Generator for Claude Code

## TL;DR
Built a Claude Code skill that generates comprehensive Product Requirements Documents in 5 minutes. Optimized for AI task breakdown tools. Beta release: https://github.com/anombyte93/prd-taskmaster

## The Problem

I've been using AI-assisted development (Claude, Cursor, etc.) and discovered that **planning is 95% of the work**.

Specifically, I use Taskmaster to break down projects into AI-generated tasks. But I kept hitting the same issue:

**Vague PRD → Vague Tasks → Poor Implementation**

Writing comprehensive PRDs manually takes hours. I'd either:
- Skip it and get bad results
- Write minimal specs and miss critical details
- Spend so long on the PRD that I lost momentum

## The Solution

What if AI could interview me and generate the PRD?

I built a Claude Code skill that:

1. **Asks ~12 detailed questions**
   - What problem are you solving?
   - Who's the user?
   - What are success metrics?
   - What's the tech stack?
   - What are the constraints?

2. **Generates a comprehensive PRD**
   - Executive summary
   - Problem statement with user & business impact
   - SMART goals & metrics
   - User stories with acceptance criteria
   - Functional & non-functional requirements
   - Technical considerations (architecture, APIs, data models)
   - Task breakdown hints
   - Dependencies

3. **Validates quality**
   - 13 automated checks
   - Catches vague language ("fast", "secure" without specifics)
   - Ensures requirements are testable
   - Validates SMART metrics

4. **Sets up taskmaster integration**
   - Creates `.taskmaster/` directory structure
   - Suggests task breakdowns
   - Estimates complexity

**Result:** "I want to add 2FA" → 5 minutes → validated PRD ready for AI task generation

## Example Output

```
📄 PRD Created: .taskmaster/docs/prd.md

📊 Overview:
  - Feature: Two-Factor Authentication
  - Complexity: Medium
  - Estimated Effort: 26 tasks, ~119 hours

🎯 Key Requirements:
  1. REQ-001: TOTP/SMS 2FA support
  2. REQ-002: Backup codes for recovery
  3. REQ-003: Login flow integration

⚠️ Quality Validation: 58/60 (EXCELLENT ✅)
```

## How It Works

The skill follows an 8-step workflow:

1. **Discovery** - Ask comprehensive questions
2. **Environment Check** - Look for existing taskmaster setup
3. **Codebase Analysis** - Scan existing code (if applicable)
4. **PRD Generation** - Write detailed requirements
5. **Directory Setup** - Create `.taskmaster/` structure
6. **Validation** - Run quality checks
7. **Task Hints** - Suggest breakdowns
8. **Presentation** - Show summary & next steps

## Development Approach (Honest Disclosure)

I built this using "vibe-coding":
- Designed multiple variations
- Evaluated with test scenarios
- Validated with impact-weighted scoring
- Refined based on evidence

**Status:** Beta - works great for me, but hasn't been tested extensively by others.

I'm being upfront about this because I'd rather be honest than oversell. The README lists known limitations and invites feedback.

## Why Share This?

If you're using AI for development, the **quality of your requirements directly impacts your results**.

This skill might help you:
- Save time on PRD writing
- Improve planning quality
- Get better results from AI task tools
- Ship features more successfully

Or maybe you'll fork it and make it better for your needs. Either way, I'm curious what the community thinks!

## Get It

**GitHub:** https://github.com/anombyte93/prd-taskmaster

Installation:
```bash
cd ~/.claude/skills
git clone https://github.com/anombyte93/prd-taskmaster.git
```

Usage:
```
Just say: "I want a PRD for [your feature]"
```

## Feedback Welcome

This is a living project. If you:
- Find bugs
- Have suggestions
- Want different templates
- Need additional validations

Please open an issue! Real-world usage will make this better.

---

**What do you think?** Is this useful? What would you change?
```

---

## LinkedIn Post

```
I built an AI tool that generates comprehensive Product Requirements Documents in 5 minutes.

The challenge: When using AI for software development, vague specifications lead to vague results. Writing detailed PRDs manually takes hours.

The solution: A Claude Code skill that interviews you about your product/feature, then generates a complete PRD with automated quality validation.

Key features:
✅ Asks 12+ smart questions to extract requirements
✅ Generates comprehensive PRD (goals, requirements, technical specs)
✅ Validates quality with 13 automated checks
✅ Suggests task breakdowns with complexity estimates
✅ Optimized for AI task breakdown tools

Example: "I want to add two-factor authentication" → 5 minutes → validated 10-page PRD

Status: Beta release - works well but open to feedback

GitHub: https://github.com/anombyte93/prd-taskmaster

#ProductManagement #AI #SoftwareDevelopment #Productivity
```

---

## Discord/Slack (Claude Code Community)

```
Hey everyone! 👋

Built a Claude Code skill I thought might be useful - it generates comprehensive PRDs optimized for AI task breakdown.

**What:** AI-powered PRD generator with quality validation
**Why:** Vague specs → vague AI-generated tasks → poor results
**How:** Asks ~12 questions, generates complete PRD, validates quality

**Link:** https://github.com/anombyte93/prd-taskmaster

Still in beta - works great for my workflow but would love feedback from the community!

Main question: Is this useful or solving a problem that doesn't exist? 😅
```

---

## Email to Friends/Colleagues

**Subject:** Built an AI tool for generating PRDs - feedback?

```
Hey [Name],

I built something I thought you might find interesting (or at least have opinions about 😄).

It's a Claude Code skill that generates comprehensive Product Requirements Documents. You basically tell it your idea, it asks ~12 questions, then generates a complete PRD with quality validation.

I made it because I was using AI task breakdown tools and realized garbage in = garbage out. Vague PRDs lead to vague tasks.

**GitHub:** https://github.com/anombyte93/prd-taskmaster

It's still beta - works well for my workflow but hasn't been tested much by others. Would love your thoughts:
- Is this useful or overkill?
- What's missing?
- What would you change?

No pressure to check it out, but figured you might have interesting perspective given [relevant context about them].

Thanks!
[Your name]
```

---

## Quick Copy-Paste Links

**GitHub Repo:**
```
https://github.com/anombyte93/prd-taskmaster
```

**One-Liner Description:**
```
AI-powered PRD generation for Claude Code with taskmaster integration
```

**Elevator Pitch:**
```
Claude Code skill that generates comprehensive PRDs in 5 minutes with automated quality validation
```

**Keywords for SEO:**
```
Claude Code, PRD generator, Product Requirements Document, AI development, Taskmaster, requirements engineering, product management, AI-assisted development
```

---

## Tips for Sharing

1. **Start small** - Pick 1-2 platforms first (Reddit + Twitter is good)
2. **Be responsive** - Reply to comments/questions within 24 hours
3. **Be humble** - "Beta", "feedback welcome", "still learning"
4. **Be honest** - Don't oversell, acknowledge limitations
5. **Be curious** - Ask what people think, what they'd change
6. **Be grateful** - Thank people who try it or give feedback

Good luck! 🚀
