# Atlas Pro Worker Runbook

## Local Setup

From the repository root:

```sh
cd workers
npm install
cp .dev.vars.example .dev.vars
```

Fill `.dev.vars` with local-only values. Never commit `.dev.vars`.

## Secrets

Production secrets are managed with Wrangler and must not be committed:

```sh
cd workers
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put STRIPE_API_KEY
npx wrangler secret put ED25519_PRIVATE_KEY
npx wrangler secret put RESEND_API_KEY
```

Use the Stripe CLI webhook secret for local replay, the Dashboard webhook secret
for the production endpoint, a Stripe API key scoped to subscription reads, a
32-byte Ed25519 seed encoded as lowercase hex, and a Resend API key scoped to
the verified `atlas-ai.au` sending domain.

## Stripe Webhook Replay

Local replay needs real Stripe test credentials in `workers/.dev.vars`:

- `STRIPE_WEBHOOK_SECRET` from `stripe listen`
- `STRIPE_API_KEY` for subscription retrieval during checkout and refresh flows
- `ED25519_PRIVATE_KEY` as a 32-byte lowercase hex seed

Run the Worker locally:

```sh
cd workers
npm run d1:migrate:local
npm run dev -- --port 8787
```

In another shell, forward Stripe events:

```sh
stripe listen --forward-to localhost:8787/stripe/webhook
```

Use the printed `whsec_...` value as `STRIPE_WEBHOOK_SECRET`, restart the
Worker, then trigger the local events:

```sh
stripe trigger checkout.session.completed
stripe trigger invoice.paid
stripe trigger customer.subscription.deleted
```

Verify local D1 state after replay:

```sh
cd workers
npx wrangler d1 execute LICENSE_DB --local --command "SELECT lid, plan, stripe_subscription_id, expires_at, cancelled_at FROM licenses ORDER BY created_at DESC LIMIT 5"
npx wrangler d1 execute LICENSE_DB --local --command "SELECT event_id, processed_at FROM processed_events ORDER BY processed_at DESC LIMIT 5"
```

Duplicate replay should return `200` with no additional license mutation because
Stripe event ids are stored in `processed_events`. A request without a Stripe
signature should return `400`:

```sh
curl -i -X POST http://localhost:8787/stripe/webhook \
  -H 'content-type: application/json' \
  --data '{"id":"evt_unsigned","object":"event","type":"customer.created"}'
```

This environment has no Stripe API key or webhook secret, so the live Stripe CLI
replay was skipped and recorded as blocked in `FLEET-LOG-BACKEND.md`. The local
Vitest suite verifies signed payloads, forged signatures, idempotency, license
issuance, invoice renewal, and cancellation against local D1.

## Resend License Email Delivery

The Worker sends license emails directly with `fetch` to Resend's Email API:
`POST https://api.resend.com/emails`. The payload includes the full license key,
CLI activation command, Claude Code `/license-activate` command, activation docs,
and `support@atlas-ai.au`.

Production setup:

```sh
cd workers
npx wrangler secret put RESEND_API_KEY
```

Resend must have the `atlas-ai.au` sending domain verified before production
traffic uses `Atlas AI <licenses@atlas-ai.au>`. Keep the API key scoped to email
sending for that domain.

Manual resend procedure:

1. Look up the license row by `lid` in D1.
2. Reconstruct or refresh a signed key through the Stripe webhook replay or the
   `/license/refresh` endpoint.
3. Send to the customer address from Stripe, not from D1, because D1 stores only
   `sub_hash` and never the raw customer email.
4. Confirm Resend delivery in the dashboard and record the `lid`, Resend message
   id, and operator initials in the incident notes. Do not log raw license keys.

Safe test-mode delivery, when a real `RESEND_API_KEY` exists locally:

```sh
cd workers
# Trigger a checkout webhook through Stripe CLI with the customer email set to delivered@resend.dev.
npm run dev -- --port 8787
```

Then confirm the Resend dashboard shows delivery comfortably inside the
2-minute acceptance window. This environment has no `RESEND_API_KEY`, so the live
Resend test-mode send was skipped and recorded as blocked in
`FLEET-LOG-BACKEND.md`. The Vitest suite mocks Resend success, 5xx retries,
retry exhaustion, 4xx fail-fast behavior, and webhook failure isolation.

## License Refresh Endpoint

`POST https://api.atlas-ai.au/license/refresh` accepts:

```json
{"lid":"lic_example"}
```

Responses:

- `200 {"ok":true,"key":"ATLAS-..."}` when the D1 license exists and Stripe
  reports the subscription as `active` or `trialing`.
- `400 {"ok":false}` for invalid JSON or a missing/non-string `lid`.
- `403 {"ok":false,"reason":"license_not_found"}` for unknown lids.
- `403 {"ok":false,"reason":"subscription_cancelled"}` for D1-cancelled rows or
  Stripe subscriptions outside `active`/`trialing`.
- `429 {"ok":false,"reason":"rate_limited"}` after 10 refresh requests per lid
  per UTC day.

CORS is intentionally narrow:

- `Access-Control-Allow-Origin: https://atlas-ai.au`
- `Access-Control-Allow-Methods: POST, OPTIONS`
- `Access-Control-Allow-Headers: content-type`

Local seeded check:

```sh
cd workers
npm run d1:migrate:local
npx wrangler d1 execute LICENSE_DB --local --command \
  "INSERT OR REPLACE INTO licenses (lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id, issued_at, expires_at, cancelled_at) VALUES ('lic_local_refresh', 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', 'pro-monthly', 'cus_local', 'sub_test_from_stripe', unixepoch(), unixepoch() + 3600, NULL)"
npm run dev -- --port 8787
curl -i -X POST http://localhost:8787/license/refresh \
  -H 'content-type: application/json' \
  --data '{"lid":"lic_local_refresh"}'
```

The local seeded check requires `STRIPE_API_KEY` to retrieve the test-mode
subscription. This environment has no Stripe API key, so the seeded live Stripe
integration was skipped and recorded as blocked in `FLEET-LOG-BACKEND.md`. The
Vitest suite verifies active, trialing, cancelled, unknown, rate-limited, CORS,
and method-guard behavior against local D1 with mocked Stripe responses.

## Telemetry Endpoint

`POST https://api.atlas-ai.au/telemetry` accepts exact JSON with
`install_id`, `event`, `version`, and `os`. Valid events are `install`,
`atlas_invoked`, `reach_execute`, and `ship_check_ok`. Valid requests return
`204`; invalid schema returns `400`; non-POST methods return `405`.

Telemetry storage has two sinks:

- D1 table `telemetry_events`, the primary store for exact KPI queries.
- Workers Analytics Engine binding `TELEMETRY`, used for cheap event counters.

Run local migrations and tests:

```sh
cd workers
npm run d1:migrate:local
npm test -- test/telemetry.test.ts
```

KPI SQL and smoke-test curls are documented in
`docs/ops/telemetry-queries.md`. Production deployment and public smoke testing
were intentionally skipped in this environment per the mission guardrail; the
blocked item is recorded in `FLEET-LOG-BACKEND.md`.

## D1

The Worker binds D1 as `LICENSE_DB`. Local migrations are safe to run with:

```sh
cd workers
npm run d1:migrate:local
```

Production deployment applies remote D1 migrations before deploying the Worker:

```sh
./scripts/deploy-worker.sh
```

The script refuses to run when `workers/.dev.vars` exists so local secrets cannot
accidentally sit in the deployment context. For build validation without a live
deploy, run:

```sh
DRY_RUN=1 ./scripts/deploy-worker.sh
```

The public custom-domain routes are:

- `https://api.atlas-ai.au/stripe/webhook`
- `https://api.atlas-ai.au/license/refresh`
- `https://api.atlas-ai.au/telemetry`

## Secret Scanning

Worker-specific secret scanning lives in `.github/workflows/worker-secret-scan.yml`
and checks `workers/**`, `scripts/deploy-worker.sh`, and the workflow file for
Stripe, Resend, and Ed25519 private-key material. Run the same local check with:

```sh
stripe_key='sk_(live|test)_'
stripe_webhook='wh''sec_[A-Za-z0-9]+'
resend_key='re_[A-Za-z0-9]{20,}'
pem_key='-----BEGIN [A-Z ]*PRIVATE KEY-----'
ed_key='ED25519_PRIVATE_KEY=[0-9a-fA-F]{64}'
secret_pattern="(${stripe_key}|${stripe_webhook}|${resend_key}|${pem_key}|${ed_key})"
git ls-files workers scripts/deploy-worker.sh .github/workflows/worker-secret-scan.yml \
  | xargs grep -nE "${secret_pattern}"
```

The command should exit non-zero with no matches.
