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
