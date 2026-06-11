#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKERS_DIR="$ROOT_DIR/workers"

if [[ -f "$WORKERS_DIR/.dev.vars" ]]; then
  echo "Refusing to deploy while workers/.dev.vars exists; move local secrets out of the bundle context first." >&2
  exit 1
fi

cd "$WORKERS_DIR"

npm run typecheck
npm test

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  npx wrangler deploy --dry-run --outdir dist
  exit 0
fi

npx wrangler d1 migrations apply LICENSE_DB --remote
npx wrangler deploy
