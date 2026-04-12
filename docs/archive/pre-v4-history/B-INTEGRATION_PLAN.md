# SKILL.md Integration Plan

## Final Structure (1500+ lines)

### Section 1: Header & Metadata (Lines 1-50)
- name, description, allowed-tools
- Core principles
- When to use / not use

### Section 2: Workflow Overview (Lines 51-100)
**NEW**: Updated workflow with 11 steps instead of 9
- Step 0: Enable Plan Mode (NEW)
- Step 1: Detect Taskmaster FIRST (UPDATED - now blocks if missing)
- Step 2: Discovery Questions (same)
- Step 3: Initialize Taskmaster (UPDATED - only via MCP/CLI, never manual)
- Step 4: Generate PRD (same)
- Step 5: Validate PRD (UPDATED - document all 13 checks)
- Step 6: Parse & Expand (UPDATED - combined operation)
- Step 7: Insert USER-TEST tasks (NEW)
- Step 8: Setup Tracking Scripts (NEW - datetime, rollback, etc.)
- Step 9: Generate 4 Execution Prompts (NEW)
- Step 10: Interactive Selection (NEW - AskUserQuestion)
- Step 11: Re-enable Plan Mode (NEW)

### Section 3: Detailed Step Implementations (Lines 101-900)
Each step gets full implementation details

### Section 4: Top 5 Additions (Lines 901-1200)
- B2: DateTime Tracking
- A1: Instant Rollback
- B3: Accuracy Learning
- D2: Security Audit
- A2: Auto-Resume

### Section 5: Common Patterns (Lines 1201-1400)
- API-focused PRD
- UI/UX-focused PRD
- Data migration PRD
- Integration PRD

### Section 6: Reference & Tips (Lines 1401-1500)
- Tips for best results
- Troubleshooting
- File structure

## Integration Strategy

**Option A: Rewrite entire SKILL.md** (cleaner, takes time)
**Option B: Surgical edits to existing** (faster, riskier)
**Option C: Create supplement file** (safest, but split logic)

**Decision: Option A** - Clean rewrite ensures consistency

## Changes Summary

**Additions:**
- 5 new workflow steps
- 5 new features (Top 5)
- DateTime tracking scripts (Python)
- Rollback script (Bash)
- Accuracy learning system (Python)
- Security audit generator (Python)
- Auto-resume state manager (Python)
- 4 execution prompt templates

**Modifications:**
- Step 2 (Environment Check) → Now blocks without taskmaster
- Step 5 (Setup) → Only via taskmaster, never manual mkdir
- Step 6 (Validation) → Document all 13 checks explicitly
- Step 7 (Task Expansion) → Combined parse+expand operation
- All execution prompts → Include git policies, progress logging

**Unchanged:**
- Discovery questions
- PRD generation logic
- Common patterns
- Reference materials

## File Dependencies

New files to be created in `.taskmaster/scripts/`:
1. `track-time.py` - DateTime tracking
2. `rollback.sh` - Git rollback
3. `learn-accuracy.py` - Estimation learning
4. `security-audit.py` - Security checklist generator
5. `execution-state.py` - Crash recovery state

All created automatically during Step 8 (Setup Tracking Scripts)

## Testing Plan

After integration, test with:
1. Small PRD (5 tasks) - verify basic flow
2. Medium PRD (15 tasks) - verify USER-TEST insertion
3. Rollback command - verify git operations
4. Crash recovery - kill mid-task, resume
5. Accuracy learning - complete 10 tasks, check adjustment

## Estimated Integration Time

- Writing new SKILL.md: 30 minutes
- Testing integration: 15 minutes
- Fixes/refinements: 15 minutes
**Total: ~1 hour**

## Current Status

Files ready:
- ✅ SKILL_UPDATE_DRAFT.md (main workflow updates)
- ✅ TOP_5_ADDITIONS.md (feature additions)
- ✅ USER_EXPERIENCE_EXAMPLE.md (for reference)
- ✅ CHANGES_SUMMARY.md (change documentation)

Next: Write complete SKILL.md v2
