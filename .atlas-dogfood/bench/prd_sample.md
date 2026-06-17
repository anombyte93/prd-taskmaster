# PRD: Per-API-key rate limiter for the public REST API

## Goal
Add a configurable rate limiter to our public REST API so a single API key cannot
exceed a fixed request budget per rolling window, protecting the service from abuse
and noisy-neighbor overload.

## Requirements
- REQ-001 (P0): Enforce a per-API-key limit of N requests per rolling 60-second
  window (N configurable per key, default 100). Excess requests get HTTP 429 with a
  `Retry-After` header.
- REQ-002 (P0): The limiter state must be shared across all API server instances
  (use the existing Redis cluster), so the limit holds regardless of which instance
  serves the request.
- REQ-003 (P1): Emit a metric (`ratelimit.rejected`) and a structured log line each
  time a request is rejected, including the API key id (hashed) and the current count.
- REQ-004 (P1): Provide an admin endpoint to read and override a key's limit at
  runtime without a deploy. Depends on REQ-001.
- REQ-005 (P2): Fail open — if Redis is unreachable, allow the request and emit a
  `ratelimit.degraded` metric rather than 500ing the caller. Depends on REQ-002.

## Out of scope
- Per-IP limiting, global limits, and billing/quota enforcement.

## Acceptance
- Load test shows the 101st request within a window for a default key returns 429.
- Killing Redis mid-test degrades to fail-open with the degraded metric emitted.
