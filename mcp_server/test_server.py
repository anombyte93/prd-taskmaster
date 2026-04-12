#!/usr/bin/env python3
"""Smoke test for the prd-taskmaster MCP server.

Imports server.py directly and calls tool functions in-process (no stdio
transport). This is a quick sanity check — the real integration test is
Claude Code itself connecting over MCP.

Run from the repo root:

    python3 mcp_server/test_server.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from mcp_server import server  # noqa: E402
except ImportError as e:
    print(f"SKIP: mcp package not available ({e})")
    sys.exit(0)


SAMPLE_PRD = """# PRD: User Authentication System

**Author:** Hayden
**Date:** 2026-04-10
**Status:** Draft
**Taskmaster Optimized:** Yes

---

## Executive Summary

This PRD defines the implementation of a two-factor authentication (2FA) system
to reduce security incidents from 150/month to fewer than 10/month. The system
will support both TOTP and SMS verification methods, with backup codes for recovery.
Target completion is Q2 2026 with a phased rollout to enterprise customers first.

---

## Problem Statement

### User Impact
Users are experiencing account compromises at a rate of 150 incidents per month,
leading to data loss and trust erosion. Affected users spend an average of 45 minutes
recovering their accounts.

### Business Impact
Each security incident costs approximately $500 in support time and revenue loss,
totaling $75,000/month. Strategic alignment with SOC2 compliance requirements
makes this a blocking requirement for enterprise sales.

---

## Goals & Success Metrics

| Metric | Baseline | Target | Timeframe | Measurement |
|--------|----------|--------|-----------|-------------|
| Security incidents | 150/month | <10/month | 90 days | Incident tracker |
| 2FA adoption rate | 0% | 60% | 180 days | Auth analytics |

---

## User Stories

### Story 1: Enable 2FA
As a user, I want to enable two-factor authentication so that my account is more secure.
- [ ] User can navigate to security settings
- [ ] User can scan QR code for TOTP setup

---

## Functional Requirements

- REQ-001: The system shall support TOTP-based 2FA using RFC 6238.
- REQ-002: The system shall support SMS-based 2FA with 6-digit codes.
- REQ-003: The system shall generate 10 backup codes per user at setup time.

---

## Non-Functional Requirements

- NFR-001: 2FA verification shall complete within 500ms at p99.
- NFR-002: Backup codes shall be hashed with bcrypt cost factor 12.

---

## Out of Scope

- Hardware security keys (FIDO2/WebAuthn) — deferred to phase 2.
- Biometric authentication — deferred to phase 2.

---

## Dependencies & Risks

- Twilio account required for SMS delivery (procurement blocker).
- Rate limiting infrastructure must exist before launch.
"""


def assert_ok(label: str, result: dict) -> None:
    if not isinstance(result, dict):
        print(f"FAIL {label}: expected dict, got {type(result).__name__}")
        sys.exit(1)
    if result.get("ok") is not True:
        print(f"FAIL {label}: ok != true")
        print(json.dumps(result, indent=2)[:800])
        sys.exit(1)
    print(f"PASS {label}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / ".taskmaster" / "docs").mkdir(parents=True)
        prd = tmp_path / ".taskmaster" / "docs" / "prd.md"
        prd.write_text(SAMPLE_PRD)

        # 1. preflight in the tmp project
        assert_ok("preflight", server.preflight(cwd=str(tmp_path)))

        # 2. detect_capabilities (no cwd required)
        assert_ok("detect_capabilities", server.detect_capabilities())

        # 3. validate_prd against the known-good sample
        result = server.validate_prd(input_path=str(prd), cwd=str(tmp_path))
        # validate-prd returns ok:true even when there are warnings; we just
        # want to confirm the structure round-trips cleanly.
        if not isinstance(result, dict) or "ok" not in result:
            print("FAIL validate_prd: missing 'ok' key")
            print(json.dumps(result, indent=2)[:800])
            sys.exit(1)
        print(f"PASS validate_prd (ok={result.get('ok')}, checks={len(result.get('checks', []))})")

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
