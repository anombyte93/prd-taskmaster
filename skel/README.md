# .atlas-ai/ — Your plugin workspace

This directory is managed by @atlas-ai/prd-taskmaster. Files here layer on top of plugin defaults.

## Structure
- `customizations/` — Your editable customization files. See customizations/README.md.
- `state/pipeline.json` — Pipeline phase state machine
- `references/` — Captured reference heatmap
- `debrief/` — Dogfood debriefs
- `config/atlas.json` — Your workflow preferences (from customise-workflow skill)
- `ship-check.py` — Deterministic completion check used by /atlas-ralph-loop:ralph-loop (Hayden's patched fork of /ralph-loop)

## Reset
Delete this directory to start fresh. Backup first if you care about the state.

TaskMaster project state lives in the normal project-level `.taskmaster/`
directory.
