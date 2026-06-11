# KPI Snapshot Runbook

## Purpose

`scripts/ops/kpi-snapshot.sh` prints the release KPI snapshot for:

| KPI | Event | Meaning |
|---|---|---|
| A1 installs | `install` | installer completed |
| A3 weekly actives | `atlas_invoked` | user started Atlas in the last 7 days |
| AC1 reach_execute | `reach_execute` | pipeline reached execution |
| AC2 ship_check_ok | `ship_check_ok` | release gate emitted `SHIP_CHECK_OK` |
| C1 conversion | `license_activate` | free-to-Pro conversion |

Rows are reported for `last-7d`, `last-30d`, and `all-time`.

## Run Locally

```bash
bash scripts/ops/kpi-snapshot.sh
```

Without analytics credentials the script exits 0 and prints `not configured`
for A1/A3/AC1/AC2. C1 prints `n/a (license telemetry not deployed)` until the
license-activation telemetry path is deployed.

## Fixture Mode

Use fixture mode for tests or release dry-runs:

```bash
KPI_FIXTURE_JSON='{"A1":{"last_7d":7,"last_30d":30,"all_time":300}}' \
LICENSE_TELEMETRY_DEPLOYED=1 \
bash scripts/ops/kpi-snapshot.sh
```

## Query Command Hook

Operators can provide a command that accepts `<metric> <bucket>` and prints one
value:

```bash
KPI_QUERY_CMD='scripts/ops/query-worker-kpi.sh' bash scripts/ops/kpi-snapshot.sh
```

The hook receives metric IDs (`A1`, `A3`, `AC1`, `AC2`, `C1`) and buckets
(`last_7d`, `last_30d`, `all_time`). This keeps the snapshot script stable
while Worker Analytics Engine or D1 query details evolve.

## Cloudflare Setup

Expected environment for a Worker Analytics implementation:

```bash
export CF_ACCOUNT_ID=...
export CF_API_TOKEN=...
export ATLAS_D1_DB=...        # optional D1 fallback
```

Recommended event filters:

- A1: count `install`
- A3: count distinct install IDs with `atlas_invoked`
- AC1: count `reach_execute`
- AC2: count `ship_check_ok`
- C1: count `license_activate` divided by A1 installs for the same range

## Weekly Review

1. Run `bash scripts/ops/kpi-snapshot.sh`.
2. Save the output in the release notes or evidence doc.
3. Check A1 and A3 for install and retention movement.
4. Check AC1 and AC2 for funnel drop-off.
5. Treat C1 as `n/a` until license activation telemetry is deployed.
