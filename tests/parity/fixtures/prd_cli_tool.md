# PRD: line-count CLI

## Goal
Build `lc`, a CLI that counts lines, words, and bytes in files.

## Requirements
- `lc <file>` prints lines, words, bytes for one file.
- `lc <a> <b>` prints per-file rows plus a total row.
- `--lines-only` flag suppresses word/byte columns.
- Reads stdin when no path is given.

## Acceptance
- Output matches `wc` byte-for-byte on the test corpus.
- Exit 1 with a stderr message on a missing file.
