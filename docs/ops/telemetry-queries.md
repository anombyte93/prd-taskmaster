# Atlas Telemetry Queries

Telemetry is accepted at `POST https://api.atlas-ai.au/telemetry` with:

```json
{"install_id":"install_123","event":"install","version":"1.2.3","os":"linux"}
```

Allowed events:

- `install`
- `atlas_invoked`
- `reach_execute`
- `ship_check_ok`

The Worker writes every valid event to D1 table `telemetry_events` and also emits
cheap counters to Workers Analytics Engine with:

- `blobs = [event, version, os]`
- `doubles = [1]`
- `indexes = [install_id]`

Use D1 for unique-install KPIs. Analytics Engine SQL is useful for sampled count
queries, but it is not the source of truth for exact unique-install metrics.

## D1 KPI Queries

A1 unique installs:

```sql
SELECT COUNT(DISTINCT install_id) AS unique_installs
FROM telemetry_events
WHERE event = 'install';
```

A3 weekly active installs:

```sql
SELECT COUNT(DISTINCT install_id) AS weekly_active_installs
FROM telemetry_events
WHERE event != 'install'
  AND timestamp > datetime('now', '-7 days');
```

AC1 reach executions:

```sql
SELECT COUNT(*) AS reach_execute_count
FROM telemetry_events
WHERE event = 'reach_execute';
```

AC2 successful ship checks:

```sql
SELECT COUNT(*) AS ship_check_ok_count
FROM telemetry_events
WHERE event = 'ship_check_ok';
```

C1 free-to-pro conversion is forward-looking until license activation telemetry
exists. The intended query needs an activation/pro event joined or correlated by
`install_id` after that event is added.

## Wrangler Examples

```sh
cd workers
npx wrangler d1 execute LICENSE_DB --remote --command \
  "SELECT COUNT(DISTINCT install_id) AS unique_installs FROM telemetry_events WHERE event = 'install'"

npx wrangler d1 execute LICENSE_DB --remote --command \
  "SELECT COUNT(DISTINCT install_id) AS weekly_active_installs FROM telemetry_events WHERE event != 'install' AND timestamp > datetime('now', '-7 days')"
```

## Analytics Engine Count Query

Analytics Engine can answer count-style checks through the Cloudflare SQL API.
Use it for inexpensive directional counters, not exact unique-install KPIs:

```sh
curl -sS "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/analytics_engine/sql" \
  -H "authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  --data-binary "SELECT blob1 AS event, SUM(double1) AS events FROM telemetry_events WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY blob1"
```

## Smoke Test

After deploy, a valid event should return `204`:

```sh
curl -i -X POST https://api.atlas-ai.au/telemetry \
  -H 'content-type: application/json' \
  --data '{"install_id":"smoke_install","event":"install","version":"1.0.0","os":"linux"}'
```

An invalid event should return `400`:

```sh
curl -i -X POST https://api.atlas-ai.au/telemetry \
  -H 'content-type: application/json' \
  --data '{"install_id":"smoke_install","event":"unknown","version":"1.0.0","os":"linux"}'
```
