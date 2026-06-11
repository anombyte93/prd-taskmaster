CREATE TABLE IF NOT EXISTS licenses (
  lid TEXT PRIMARY KEY,
  sub_hash TEXT NOT NULL,
  plan TEXT NOT NULL,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  issued_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  cancelled_at INTEGER,
  created_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_licenses_sub_hash
  ON licenses (sub_hash);

CREATE INDEX IF NOT EXISTS idx_licenses_stripe_subscription_id
  ON licenses (stripe_subscription_id);

CREATE TABLE IF NOT EXISTS processed_events (
  event_id TEXT PRIMARY KEY,
  processed_at INTEGER NOT NULL
);
