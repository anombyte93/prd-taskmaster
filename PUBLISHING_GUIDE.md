# How to Publish & Share This Skill

Quick guide to get your prd-taskmaster skill out into the world.

## Step 1: Create GitHub Repository

### Option A: Using GitHub CLI (Easiest)

```bash
cd ~/.claude/skills/prd-taskmaster

# Initialize if not already done
git init
git add .
git commit -m "Initial release of prd-taskmaster skill"

# Create GitHub repo (will prompt for public/private)
gh repo create prd-taskmaster --public --source=. --remote=origin --push

# That's it! Your repo is live at:
# https://github.com/anombyte93/prd-taskmaster
```

### Option B: Using GitHub Website

1. Go to https://github.com/new
2. Name: `prd-taskmaster`
3. Description: `AI-powered PRD generation for Claude Code with taskmaster integration`
4. Make it **Public**
5. Don't initialize with README (you already have one)
6. Click **Create repository**

Then in your terminal:
```bash
cd ~/.claude/skills/prd-taskmaster
git remote add origin https://github.com/anombyte93/prd-taskmaster.git
git branch -M main
git push -u origin main
```

## Step 2: Polish the README

Update these placeholders in `PUBLIC_README.md`:

```bash
# Replace anombyte93 with your actual GitHub username
sed -i 's/anombyte93/your-actual-username/g' PUBLIC_README.md

# Move PUBLIC_README.md to be the main README
mv README.md DEVELOPER_README.md
mv PUBLIC_README.md README.md

# Commit changes
git add .
git commit -m "Update README with real GitHub links"
git push
```

## Step 3: Add Topics/Tags on GitHub

On your GitHub repo page:

1. Click the ⚙️ icon next to "About"
2. Add topics:
   - `claude-code`
   - `claude-skills`
   - `prd`
   - `product-requirements`
   - `taskmaster`
   - `ai-development`
   - `requirements-engineering`
   - `product-management`

This helps people discover your skill!

## Step 4: Simple Ways to Share

### Low-Effort Sharing (Start Here)

1. **Reddit Posts**
   - r/ClaudeAI - "I built a Claude Code skill for generating PRDs"
   - r/ProductManagement - "AI tool for generating comprehensive PRDs"
   - r/SideProject - "My Claude Code skill for AI-assisted PRD generation"

   **Template:**
   ```
   Title: Built a Claude Code skill that generates comprehensive PRDs with AI

   I created a skill for Claude Code that generates detailed Product Requirements Documents optimized for AI task breakdown tools.

   It asks ~12 questions about your feature/product, then generates a comprehensive PRD with validation, task breakdown hints, and sets up the directory structure.

   Built using "vibe-coding" methodology - works great for my workflow but still in beta. Would love feedback!

   GitHub: [your repo link]
   ```

2. **Twitter/X Post**
   ```
   Built a @AnthropicAI Claude Code skill that generates comprehensive PRDs optimized for AI dev workflows

   Goes from "I have an idea" → "validated PRD ready for task breakdown" in 5 mins

   Beta release, feedback welcome!

   https://github.com/anombyte93/prd-taskmaster
   ```

3. **Hacker News Show HN**
   ```
   Title: Show HN: Claude Code skill for AI-generated PRDs

   URL: https://github.com/anombyte93/prd-taskmaster

   Comment:
   I built a Claude Code skill that generates detailed Product Requirements Documents optimized for AI task breakdown.

   It extracts requirements through ~12 questions, validates quality with 13 automated checks, and sets up taskmaster integration.

   Built with "vibe-coding" - works well but hasn't been tested extensively. Honest about limitations in the README. Would appreciate feedback!
   ```

4. **Claude Code Community**
   - Check if there's a Claude Code Discord/Slack
   - Share in #show-and-tell or similar channel

### Medium-Effort Sharing

5. **Dev.to or Hashnode Blog Post**

   **Title Ideas:**
   - "How I Built an AI PRD Generator for Claude Code"
   - "From Idea to PRD in 5 Minutes: A Claude Code Skill"
   - "Why Planning Matters: Building a PRD Generator with AI"

   **Outline:**
   ```markdown
   ## The Problem
   - PRDs take hours to write
   - AI task breakdown tools need detailed requirements
   - Vague specs = poor results

   ## The Solution
   - Built a Claude Code skill
   - Automated question-asking
   - Quality validation
   - Taskmaster integration

   ## How It Works
   [Include example output from README]

   ## Lessons Learned
   - Vibe-coding can work
   - Validation is critical
   - Templates are powerful

   ## Try It
   [GitHub link]

   ## Feedback Welcome
   Still in beta, would love to hear what breaks!
   ```

6. **Product Hunt**
   - Wait until you have 2-3 users who've tried it
   - Get them to be "hunters" or early upvoters
   - Launch on a Tuesday/Wednesday
   - Use screenshots from README in your listing

### High-Effort Sharing (Optional)

7. **YouTube Demo**
   - Screen record using the skill
   - Show the full workflow
   - Be honest about limitations
   - 5-10 minute video

8. **Write a Tutorial**
   - "Building PRDs for AI-Assisted Development"
   - Use your skill as the tool
   - Share on Medium/Dev.to

## Step 5: Handle Feedback/Criticism

### If People Criticize

**Remember:**
- You were honest about it being beta
- You disclosed the "vibe-coding" approach
- You invited feedback
- You shared to help, not for validation

**Responses:**

❌ **Defensive:**
> "Well it works for me! You just don't get it."

✅ **Growth-Oriented:**
> "Thanks for trying it! What specifically didn't work? I'd love to make it better."

❌ **Apologetic:**
> "Sorry, I know it's terrible. I shouldn't have shared."

✅ **Confident & Open:**
> "Appreciate the feedback! It's in beta and I'm actively improving it. What would make it more useful for your workflow?"

### If People Love It

- Thank them!
- Ask what they'd like to see next
- Invite them to contribute
- Add their use cases to examples

### If Nobody Cares

- That's fine! You learned and built something useful
- Keep it maintained for yourself
- Share when it becomes more polished
- Consider it practice for the next project

## Step 6: Maintenance Plan

### Minimal Effort
- Check GitHub issues once a week
- Fix critical bugs
- Merge good PRs from others

### Medium Effort
- Add one new feature per month
- Create more templates (API, UI, integration)
- Write blog posts about usage

### High Effort
- Build community
- Create video tutorials
- Integrate with other tools
- Comprehensive documentation

**Choose what fits your time!**

## Quick Checklist

Before you share:

- [ ] GitHub repo is public
- [ ] README has real GitHub URLs (not anombyte93)
- [ ] LICENSE file exists (MIT)
- [ ] .gitignore is set up
- [ ] All files are committed
- [ ] Topics/tags added on GitHub
- [ ] You've tested it works after fresh clone

Optional but nice:
- [ ] Add screenshots to README
- [ ] Create a demo GIF
- [ ] Write a changelog
- [ ] Add contributing guidelines

## The Honest Approach

Your README already does this well, but when sharing:

### Good Framing
✅ "Built this for my workflow, sharing in case it helps others"
✅ "Beta release - works but hasn't been extensively tested"
✅ "Feedback welcome to make it better"
✅ "Vibe-coded but validated against test scenarios"

### Avoid
❌ "Revolutionary PRD tool" (overselling)
❌ "Better than manual PRDs" (subjective claim)
❌ "Production-ready enterprise solution" (it's beta!)
❌ Hiding limitations or development approach

## Where NOT to Share (Yet)

Wait until you have more usage/polish:
- Official Anthropic channels (unless they have "community showcase")
- Enterprise/corporate settings
- As a paid tool
- Academic publications

Wait until v2.0 or after real user testing!

## Success Metrics

Don't expect:
- Thousands of stars
- Viral success
- Immediate adoption

Do hope for:
- 5-10 people try it
- 2-3 pieces of constructive feedback
- 1 person finds it genuinely useful
- Learning what resonates with users

**That's a successful v1.0 release!**

## Need Help?

If you get stuck:
- GitHub has great docs: https://docs.github.com
- Reddit communities are usually helpful
- Claude can help you write sharing posts
- Just start small - one post, one platform

---

**Remember:** You built something useful. Share it with confidence, be honest about limitations, and be open to feedback. That's how good projects grow!

Good luck! 🚀
