# PRD: CSV-to-Parquet ingest pipeline

## Goal
Build a batch pipeline that ingests daily CSV drops and emits partitioned Parquet.

## Requirements
- Watch an input directory for new `*.csv` files.
- Validate each row against a declared schema; quarantine bad rows to a reject file.
- Write valid rows to Parquet partitioned by event date.
- Emit a per-run manifest with row counts (ingested, rejected) and checksums.
- Re-running on the same input is idempotent (no duplicate partitions).

## Acceptance
- A malformed row lands in the reject file, not the Parquet output.
- The manifest row counts equal the input minus rejects.
