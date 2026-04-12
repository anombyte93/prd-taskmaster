# prd-taskmaster v4 — demo recording scripts

These scripts produce terminal recordings that can be embedded in the README
or shared to demonstrate how each phase behaves.

## Why recordings, not static screenshots

v4's value is in the **flow** between phases — SETUP gives you fix commands,
PREFLIGHT auto-detects state, DISCOVER is adaptive, GENERATE scores quality,
HANDOFF recommends a mode. A static screenshot captures none of that. A
~30-second terminal recording shows the full loop.

## Why scripts, not pre-recorded videos

- Recordings get stale fast as the skill evolves.
- Users want to reproduce what they see, not trust a polished demo.
- `asciinema` recordings are text files — diffable, embeddable, and can be
  replayed at any speed by the viewer.
- The scripts themselves are the best documentation of the happy path.

## Prerequisites

```bash
# Install asciinema
sudo pacman -S asciinema          # Arch
brew install asciinema            # macOS
pip install asciinema             # pip fallback

# (Optional) For MP4/GIF conversion:
npm install -g svg-term-cli       # asciicast → SVG
# OR
pip install asciinema-animate     # asciicast → GIF
```

## The scripts

Each phase has its own recording script. Run them individually, then upload
the resulting `.cast` files to asciinema.org or convert to GIF/SVG for the
README.

| Script | What it records |
|---|---|
| `record-phase-0-setup.sh` | Fresh tmp dir → `validate-setup` → fix commands → re-run → ready |
| `record-phase-1-preflight.sh` | `preflight` on various project states (fresh, initialized, with PRD) |
| `record-phase-3-generate.sh` | `load-template` → fill → `validate-prd` → `parse-prd` |
| `record-phase-4-handoff.sh` | `detect-capabilities` → mode recommendation + alternatives |
| `record-customise-workflow.sh` | `/customise-workflow` end-to-end answer flow |
| `record-provider-swap.sh` | `task-master models --set-main` Gemini ↔ Claude Code swap, same command works |
| `record-full-pipeline.sh` | The complete Phase 0 → 4 flow end-to-end (longest, ~2-3 min) |

## Usage

```bash
cd scripts/demo
./record-phase-0-setup.sh
# Creates recordings/phase-0-setup.cast
# Upload: asciinema upload recordings/phase-0-setup.cast
# Or convert to GIF: asciinema-animate recordings/phase-0-setup.cast phase-0-setup.gif
```

## Embedding in the README

```markdown
[![asciicast](https://asciinema.org/a/YOUR_ID.svg)](https://asciinema.org/a/YOUR_ID)
```

## Why Claude can't run these autonomously

The recording scripts spawn a TTY, capture keystrokes and output, and produce
a time-indexed `.cast` file. Claude's bash tool doesn't have a TTY —
`asciinema rec` detects `stdout.isatty() == False` and refuses to record.

Running these scripts is a **manual step** the user performs once after
merging v4. The outputs get committed under `scripts/demo/recordings/`.

## Alternative: ttyrec + ttygif (offline)

If asciinema isn't available, `ttyrec` + `ttygif` produces a GIF directly:

```bash
ttyrec recordings/phase-0-setup.ttyrec bash -c './record-phase-0-setup.sh'
ttygif recordings/phase-0-setup.ttyrec
# Produces tty.gif in the current directory
```
