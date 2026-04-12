# Research: writing-plans Skill Audit

## Source Skill
`~/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/skills/writing-plans/SKILL.md` (150 lines)

## KEEP
1. No-placeholder rule — forces concrete steps
2. Exact file paths in every task
3. Self-review checklist (spec coverage + placeholder scan + type consistency)
4. Bite-sized steps (2-5 min each)
5. Execution handoff (subagent vs inline)
6. Plan document header with goal/architecture/stack

## DISCARD
1. Mandatory TDD — make optional per task
2. Software-only assumptions (pytest, git commit, etc.)
3. Rigid 5-step Red-Green-Refactor format
4. Hardcoded save path (docs/superpowers/plans/)
5. Worktree assumption

## ADD
1. Domain-agnostic task templates (pentest, business, learning, not just code)
2. Progressive refinement option (light plan + refine during execution)
3. YAML frontmatter on plan docs (id, scope, priority, prerequisites)
4. Complexity-adaptive granularity (simple=1-2 steps, complex=5+)
5. CDD integration point (tasks reference CDD cards)

## DEPENDENCIES TO REPLACE
- superpowers:subagent-driven-development → our own execution skill
- superpowers:executing-plans → our own inline executor
- superpowers:brainstorming → prd-taskmaster handles discovery
- Git worktree → optional, works anywhere

## CONTRARIAN ADDITIONS (from agent audit)
6. Rollback handling — if decomposition was wrong mid-execution, need "replan from here" escape
7. Risk matrix — plans should call out "hard parts" and "riskiest assumptions"
8. Task dependency map — flag which tasks can run in parallel
9. Self-review as gate, not suggestion — block on placeholder/consistency issues
10. Spec validation — detect if input is a real spec vs rambling goal, handle both

## RESEARCH HIGHLIGHTS
- TDD-first: devs skip it. Make it opt-in, not forced.
- Plan granularity: 2-5 min steps maximize follow-through (research confirms)
- Format: YAML frontmatter + Markdown body is best for agent consumption
- Non-software plans: need WBS phases, stakeholder sections, not just code tasks
- Progressive > upfront: hybrid light-plan-then-refine beats detailed-upfront for uncertain goals
