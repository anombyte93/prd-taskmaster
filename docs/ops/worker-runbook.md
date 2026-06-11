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
npx wrangler secret put ED25519_PRIVATE_KEY
npx wrangler secret put RESEND_API_KEY
```

Use the Stripe CLI webhook secret for local replay, the Dashboard webhook secret
for the production endpoint, a 32-byte Ed25519 seed encoded as lowercase hex, and
a Resend API key scoped to the verified `atlas-ai.au` sending domain.

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
git ls-files workers scripts/deploy-worker.sh .github/workflows/worker-secret-scan.yml \
  | xargs grep -nE '(sk_live_|sk_test_|whsec_[A-Za-z0-9]+|re_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ED25519_PRIVATE_KEY=[0-9a-fA-F]{64})'
```

The command should exit non-zero with no matches.
