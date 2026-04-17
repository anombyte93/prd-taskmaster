"""Shared fixtures for prd-taskmaster test suite.

All fixtures create REAL files in temp directories — no mocking.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PY = PROJECT_ROOT / "script.py"
EXPAND_SCRIPT_PY = PROJECT_ROOT / "companion-skills" / "expand-tasks" / "script.py"
TEMPLATE_DIR = PROJECT_ROOT / "templates"


def run_script(script_path, args, cwd=None):
    """Run a script.py subcommand and return parsed JSON output."""
    cmd = [sys.executable, str(script_path)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
        timeout=30,
    )
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = {"_raw_stdout": result.stdout, "_raw_stderr": result.stderr}
    return result.returncode, output


@pytest.fixture
def tmp_project(tmp_path):
    """Create a realistic project directory with .taskmaster structure."""
    taskmaster = tmp_path / ".taskmaster"
    (taskmaster / "docs").mkdir(parents=True)
    (taskmaster / "tasks").mkdir(parents=True)
    (taskmaster / "scripts").mkdir(parents=True)
    (taskmaster / "state").mkdir(parents=True)
    (taskmaster / "notes").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_prd(tmp_project):
    """Create a realistic PRD file that should pass most validation checks."""
    prd_content = """# PRD: User Authentication System

**Author:** Author
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
| Account recovery time | 45 min | 5 min | 90 days | Support tickets |

---

## User Stories

### Story 1: Enable 2FA
As a user, I want to enable two-factor authentication so that my account is more secure.
- [ ] User can navigate to security settings
- [ ] User can choose TOTP or SMS method
- [ ] User can scan QR code for TOTP setup
- [ ] User receives confirmation of 2FA activation

### Story 2: Login with 2FA
As a user, I want to enter my 2FA code during login so that my identity is verified.
- [ ] User sees 2FA prompt after password entry
- [ ] User can enter 6-digit TOTP code
- [ ] User can request SMS code resend
- [ ] Invalid codes show clear error messages

### Story 3: Recovery
As a user, I want backup codes so that I can access my account if I lose my 2FA device.
- [ ] User receives 10 backup codes at 2FA setup
- [ ] Each backup code works exactly once
- [ ] User can regenerate backup codes

---

## Functional Requirements

### Must Have (P0)

**REQ-001**: The system must support TOTP-based authentication using RFC 6238.
Each TOTP token has a 30-second validity window with a 1-step tolerance.
- Task: Implement TOTP verification service (~4h)
- Acceptance: TOTP codes validate correctly within window

**REQ-002**: The system must support SMS-based verification via Twilio API.
SMS delivery must complete within 10 seconds for 99% of requests.
- Task: Integrate Twilio SMS gateway (~6h)
- Acceptance: SMS codes delivered and validated end-to-end

**REQ-003**: Users must have exactly 10 single-use backup codes generated at 2FA setup.
Codes must be cryptographically random, 8 characters alphanumeric.
- Task: Implement backup code generation and storage (~3h)
- Acceptance: Codes generate, store hashed, validate once only

### Should Have (P1)

**REQ-004**: The system should provide a 2FA management UI in user settings.
- Task: Build settings page component (~8h)

**REQ-005**: The system should log all 2FA events for audit purposes.
- Task: Implement audit logging (~4h)

### Could Have (P2)

**REQ-006**: The system could support WebAuthn/FIDO2 hardware keys.
- Task: Research and prototype WebAuthn integration (~12h)

---

## Non-Functional Requirements

- Authentication API response time must be under 200ms for 95th percentile
- System must handle 1000 concurrent authentication requests per second
- 2FA data must be encrypted at rest using AES-256
- Backup codes must be stored as bcrypt hashes (cost >= 10)
- SMS delivery success rate must exceed 99.5%

---

## Technical Considerations

### Architecture
The 2FA system follows a microservice architecture pattern with a dedicated Auth Service
communicating via REST API. The system design uses an event-driven component model for
audit logging, with integration points at the login flow and settings pages.

### Data Model
```sql
CREATE TABLE user_2fa (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    method VARCHAR(10) NOT NULL CHECK (method IN ('totp', 'sms')),
    secret_encrypted BYTEA NOT NULL,
    enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE backup_codes (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    code_hash VARCHAR(60) NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMPTZ
);
```

### API Endpoints
```
POST /api/v1/2fa/setup    - Initialize 2FA for user
POST /api/v1/2fa/verify   - Verify 2FA code during login
POST /api/v1/2fa/backup   - Generate/regenerate backup codes
DELETE /api/v1/2fa         - Disable 2FA
```

---

## Dependencies

- REQ-002 depends on REQ-001 (shared verification flow)
- REQ-004 depends on REQ-001, REQ-002, REQ-003 (all backend complete)
- REQ-005 depends on REQ-001 (needs auth events to log)
- External: Twilio API account and credentials
- Internal: User service API, Session management service

---

## Out of Scope

- Biometric authentication (fingerprint, face ID) — future consideration for v2
- SSO/SAML integration — separate project already in planning
- Password policy changes — handled by existing password service
- Rate limiting overhaul — addressed in separate security hardening sprint

---

## Validation Checkpoint

### Phase 1 Validation (Week 2)
- TOTP setup and verification working end-to-end
- Unit tests passing with >90% coverage

### Phase 2 Validation (Week 4)
- SMS integration complete with Twilio sandbox
- Backup codes functional
- Integration tests passing

---

## Task Breakdown for Taskmaster

1. Setup auth service scaffold - Small (2-4h) - Depends on: none
2. Implement TOTP verification - Medium (4-8h) - Depends on: Task 1
3. Integrate Twilio SMS - Medium (6-8h) - Depends on: Task 1
4. Build backup code system - Small (3-4h) - Depends on: Task 1
5. Create 2FA settings UI - Large (8-12h) - Depends on: Tasks 2,3,4
6. Implement audit logging - Small (4h) - Depends on: Task 2
7. Write integration tests - Medium (6-8h) - Depends on: Tasks 2,3,4
8. Security review and hardening - Small (4h) - Depends on: Task 7

**Critical Path:** Task 1 → Task 2 → Task 7 → Task 8
**Total:** ~45 hours across 8 tasks
"""
    prd_path = tmp_project / ".taskmaster" / "docs" / "prd.md"
    prd_path.write_text(prd_content)
    return prd_path


@pytest.fixture
def minimal_prd(tmp_project):
    """Create a minimal PRD that should trigger some validation warnings."""
    prd_content = """# PRD: Dark Mode

## Executive Summary
Add dark mode to the app. Users want it. We should build it quickly.

## Problem Statement
Users complain about eye strain.

## Goals
Make the app look good in dark mode.

## Requirements
- The app should be user-friendly in dark mode
- It needs to be fast and performant
- Colors should look good

## Technical
Use CSS variables for theming.
"""
    prd_path = tmp_project / ".taskmaster" / "docs" / "prd.md"
    prd_path.write_text(prd_content)
    return prd_path


@pytest.fixture
def sample_tasks_json(tmp_project):
    """Create a realistic tasks.json file."""
    tasks_data = {
        "tasks": [
            {
                "id": 1,
                "title": "Setup auth service scaffold",
                "description": "Create the base service structure for 2FA",
                "status": "pending",
                "dependencies": [],
                "subtasks": [
                    {"id": "1.1", "title": "Create service boilerplate"},
                    {"id": "1.2", "title": "Add database migrations"},
                ],
            },
            {
                "id": 2,
                "title": "Implement TOTP verification",
                "description": "Build TOTP verification using RFC 6238",
                "status": "pending",
                "dependencies": [1],
                "subtasks": [],
            },
            {
                "id": 3,
                "title": "Integrate Twilio SMS",
                "description": "SMS-based 2FA via Twilio API",
                "status": "done",
                "dependencies": [1],
                "details": "Using Twilio Verify API v2",
                "research_notes": "Previous research on Twilio integration",
                "subtasks": [],
            },
        ]
    }
    tasks_path = tmp_project / ".taskmaster" / "tasks" / "tasks.json"
    tasks_path.write_text(json.dumps(tasks_data, indent=2))
    return tasks_path


@pytest.fixture
def execution_state(tmp_project):
    """Create an in-progress execution state for crash recovery testing."""
    state = {
        "status": "in_progress",
        "current_task": "3",
        "current_subtask": "3.2",
        "mode": "sequential",
        "last_updated": "2026-04-10T08:00:00+00:00",
        "last_checkpoint": "2",
        "completed_tasks": ["1", "2"],
    }
    state_path = tmp_project / ".taskmaster" / "state" / "execution-state.json"
    state_path.write_text(json.dumps(state, indent=2))
    return state_path
