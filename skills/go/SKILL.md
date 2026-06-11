---
name: go
description: >-
  Zero-config goal-to-tasks engine. Takes any goal (software, pentest, business, learning),
  runs adaptive discovery, generates a validated spec, parses into TaskMaster tasks, creates an
  implementation plan, and executes with built-in verified execution. Use when user says "PRD",
  "product requirements", "I want to build", or any goal-driven phrase.
user-invocable: true
allowed-tools:
  - Read
  - Skill
  - Bash
  - AskUserQuestion
---

# go (orchestrator)

Pure routing. Reads pipeline state, dispatches to the correct phase skill.

## Flow

1. Call `mcp__plugin_prd-taskmaster_go__preflight()` — get environment state
2. Call `mcp__plugin_prd-taskmaster_go__current_phase()` — get pipeline state
3. Route via Skill tool:
   - current_phase is null or SETUP → invoke `/prd-taskmaster:setup`
   - current_phase is DISCOVER → invoke `/prd-taskmaster:discover`
   - current_phase is GENERATE → invoke `/prd-taskmaster:generate`
   - current_phase is HANDOFF → invoke `/prd-taskmaster:handoff`
   - current_phase is EXECUTE → invoke `/prd-taskmaster:execute-task`

4. After phase skill returns, re-check current_phase. If it advanced, route to the next phase. If not, report the blocker.

## Stateless routing

This skill does NOT hold procedure. Each phase skill owns its own logic. The orchestrator survives context loss because every phase skill reads `current_phase()` on entry.

## Red flags

These thoughts mean STOP, you're rationalising:
- "I know which phase we're in, skip preflight" → NO. Preflight is cheap.
- "The phase skill already ran, I don't need to re-check" → NO. Context might have died.
- "I can just do the work myself" → NO. Dispatch to the phase skill.
