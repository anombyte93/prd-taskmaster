CREATE TABLE IF NOT EXISTS telemetry_events (
  id INTEGER PRIMARY KEY,
  install_id TEXT NOT NULL,
  event TEXT NOT NULL,
  version TEXT NOT NULL,
  os TEXT NOT NULL,
  timestamp TEXT NOT NULL
);
