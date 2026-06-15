"""Tests for prd_taskmaster.validation — 13-check PRD quality validation.

Ported from prd-taskmaster-plugin tests/test_validation.py (itself ported
from prd-taskmaster-v4 tests/test_script.py::TestValidatePrd). Direct
function calls, real I/O, no mocking.

Contract differences from the plugin's 14-check validate_prd:
- entry point is run_validate_prd(path); no ai= param (the forward-compat
  ai arg lives in the MCP server wrapper — see tests/mcp/test_integration.py)
- 13 checks: the placeholder check became a warning + placeholder_penalty
- max score = 9*5 (required) + 4*3 (taskmaster) = 57
- missing file raises CommandError instead of returning {"ok": False}
"""

import json

import pytest

from prd_taskmaster.lib import CommandError
from prd_taskmaster.validation import run_validate_prd, run_validate_tasks


# ─── Fixtures ─────────────────────────────────────────────────────────────────


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


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestValidatePrd:
    """Test run_validate_prd — the 13-check quality validation.

    Max score = 9*5 (required) + 4*3 (taskmaster-specific) = 57.
    Placeholder attribution (the plugin's check 14) is a warning + penalty
    in this package, not a scored check.
    """

    def test_validate_comprehensive_prd(self, sample_prd):
        """Well-crafted PRD scores EXCELLENT."""
        out = run_validate_prd(str(sample_prd))
        assert out["ok"] is True
        assert out["checks_total"] == 13
        assert out["grade"] in ("EXCELLENT", "GOOD")
        assert out["score"] > 0
        assert out["max_score"] == 57  # 9*5 + 4*3

    def test_validate_checks_executive_summary(self, sample_prd):
        """Check 1: Executive summary exists and has appropriate length."""
        out = run_validate_prd(str(sample_prd))
        check1 = next(c for c in out["checks"] if c["id"] == 1)
        assert check1["passed"] is True
        assert check1["category"] == "required"
        assert "words" in check1["detail"].lower()

    def test_validate_checks_user_impact(self, sample_prd):
        """Check 2: Problem statement includes user impact."""
        out = run_validate_prd(str(sample_prd))
        check2 = next(c for c in out["checks"] if c["id"] == 2)
        assert check2["passed"] is True

    def test_validate_checks_business_impact(self, sample_prd):
        """Check 3: Problem statement includes business impact."""
        out = run_validate_prd(str(sample_prd))
        check3 = next(c for c in out["checks"] if c["id"] == 3)
        assert check3["passed"] is True

    def test_validate_checks_smart_goals(self, sample_prd):
        """Check 4: Goals have SMART metrics."""
        out = run_validate_prd(str(sample_prd))
        check4 = next(c for c in out["checks"] if c["id"] == 4)
        assert check4["passed"] is True

    def test_validate_checks_user_stories_ac(self, sample_prd):
        """Check 5: User stories have acceptance criteria (min 3)."""
        out = run_validate_prd(str(sample_prd))
        check5 = next(c for c in out["checks"] if c["id"] == 5)
        assert check5["passed"] is True

    def test_validate_checks_testable_requirements(self, sample_prd):
        """Check 6: Functional requirements are testable (no vague language)."""
        out = run_validate_prd(str(sample_prd))
        check6 = next(c for c in out["checks"] if c["id"] == 6)
        # Our sample PRD uses specific, measurable language — no vague terms
        assert check6["passed"] is True
        assert "specific" in check6["detail"].lower() or "vague" not in check6["detail"].lower()

    def test_validate_checks_priority_labels(self, sample_prd):
        """Check 7: Requirements have priority labels."""
        out = run_validate_prd(str(sample_prd))
        check7 = next(c for c in out["checks"] if c["id"] == 7)
        assert check7["passed"] is True

    def test_validate_checks_req_numbering(self, sample_prd):
        """Check 8: Requirements are numbered (REQ-NNN)."""
        out = run_validate_prd(str(sample_prd))
        check8 = next(c for c in out["checks"] if c["id"] == 8)
        assert check8["passed"] is True
        assert "6" in check8["detail"]  # we have REQ-001 through REQ-006

    def test_validate_checks_architecture(self, sample_prd):
        """Check 9: Technical considerations address architecture."""
        out = run_validate_prd(str(sample_prd))
        check9 = next(c for c in out["checks"] if c["id"] == 9)
        assert check9["passed"] is True

    def test_validate_checks_nfr_targets(self, sample_prd):
        """Check 10: Non-functional requirements have specific targets."""
        out = run_validate_prd(str(sample_prd))
        check10 = next(c for c in out["checks"] if c["id"] == 10)
        assert check10["passed"] is True
        assert check10["category"] == "taskmaster"

    def test_validate_checks_task_hints(self, sample_prd):
        """Check 11: Task breakdown hints exist."""
        out = run_validate_prd(str(sample_prd))
        check11 = next(c for c in out["checks"] if c["id"] == 11)
        assert check11["passed"] is True

    def test_validate_checks_dependencies(self, sample_prd):
        """Check 12: Dependencies identified."""
        out = run_validate_prd(str(sample_prd))
        check12 = next(c for c in out["checks"] if c["id"] == 12)
        assert check12["passed"] is True

    def test_validate_checks_out_of_scope(self, sample_prd):
        """Check 13: Out of scope section exists with content."""
        out = run_validate_prd(str(sample_prd))
        check13 = next(c for c in out["checks"] if c["id"] == 13)
        assert check13["passed"] is True

    def test_validate_minimal_prd_scores_lower(self, minimal_prd):
        """Minimal/vague PRD scores significantly lower than comprehensive."""
        out = run_validate_prd(str(minimal_prd))
        assert out["ok"] is True
        assert out["grade"] in ("NEEDS_WORK", "ACCEPTABLE")
        assert out["score"] < 40  # substantially lower

    def test_validate_vague_language_detected(self, minimal_prd):
        """Vague language warnings are generated."""
        out = run_validate_prd(str(minimal_prd))
        assert out["ok"] is True
        assert len(out["warnings"]) > 0
        vague_warnings = [w for w in out["warnings"] if w["type"] == "vague_language"]
        assert len(vague_warnings) > 0
        # Our minimal PRD has "user-friendly", "fast", "performant"
        vague_terms = {w["term"].lower() for w in vague_warnings}
        assert "user-friendly" in vague_terms or "fast" in vague_terms or "performant" in vague_terms

    def test_validate_vague_penalty_applied(self, minimal_prd):
        """Vague language penalty reduces score."""
        out = run_validate_prd(str(minimal_prd))
        assert out["ok"] is True
        assert out["vague_penalty"] > 0
        # Score should be less than sum of passed checks due to penalty
        passed_points = sum(c["points"] for c in out["checks"] if c["passed"])
        assert out["score"] <= passed_points

    def test_validate_missing_file_fails(self, tmp_path):
        """Non-existent file raises CommandError with a clear message."""
        with pytest.raises(CommandError, match="not found"):
            run_validate_prd(str(tmp_path / "nope.md"))

    def test_validate_empty_prd(self, tmp_project):
        """Empty PRD file gets lowest grade with most checks failing."""
        empty_prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        empty_prd.write_text("")
        out = run_validate_prd(str(empty_prd))
        assert out["grade"] == "NEEDS_WORK"
        # 3 checks pass vacuously on empty PRD:
        #   ch 5: no stories found → pass
        #   ch 6: no vague reqs → pass
        #   ch 10: no NFR section → pass
        assert out["checks_passed"] == 3
        assert out["score"] == 13  # 5 + 5 + 3

    def test_validate_grade_boundaries(self, tmp_project):
        """Verify grade boundary calculations match documented thresholds."""
        prd_path = tmp_project / ".taskmaster" / "docs" / "prd.md"

        # Empty PRD scores well below 75% -> NEEDS_WORK
        prd_path.write_text("")
        out = run_validate_prd(str(prd_path))
        assert out["grade"] == "NEEDS_WORK"
        assert out["percentage"] < 75

    def test_validate_grade_excellent_threshold(self, sample_prd):
        """Comprehensive PRD should achieve EXCELLENT (91%+) or GOOD (83%+)."""
        out = run_validate_prd(str(sample_prd))
        assert out["percentage"] >= 83  # At minimum GOOD
        assert out["grade"] in ("EXCELLENT", "GOOD")


class TestPlaceholderHardFail:
    """Placeholders are a hard fail (README contract): grade floored to
    NEEDS_WORK, result carries hard_fail, CLI exits non-zero."""

    @pytest.mark.parametrize(
        "token,ptype",
        [
            ("{{feature_name}}", "mustache"),
            ("[TBD]", "tbd"),
            ("TBD", "bare_tbd"),
            ("TODO", "bare_todo"),
        ],
    )
    def test_placeholder_floors_grade_and_sets_hard_fail(self, tmp_project, sample_prd, token, ptype):
        # seed an otherwise-EXCELLENT PRD with one placeholder token
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        prd.write_text(sample_prd.read_text() + f"\n\n## Rollout\n\nOwner: {token}\n")
        out = run_validate_prd(str(prd))
        assert out["hard_fail"] == {"reason": "placeholders", "count": out["placeholders_found"]}
        assert out["grade"] == "NEEDS_WORK"
        assert any(d["type"] == ptype for d in out["placeholder_details"])

    def test_clean_prd_has_no_hard_fail(self, sample_prd):
        out = run_validate_prd(str(sample_prd))
        assert out["hard_fail"] is None
        assert out["grade"] in ("EXCELLENT", "GOOD")

    def test_lowercase_todo_is_not_a_placeholder(self, tmp_project, sample_prd):
        # prose like "a todo app" must not trip the case-sensitive bare patterns
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        prd.write_text(sample_prd.read_text() + "\n\nThe team also maintains a todo app.\n")
        out = run_validate_prd(str(prd))
        assert out["hard_fail"] is None

    def test_cli_exits_nonzero_on_hard_fail(self, tmp_project, sample_prd):
        import subprocess, sys as _sys
        from pathlib import Path as _P
        repo = _P(__file__).resolve().parents[2]
        # sample_prd and prd share the same path — keep a clean copy aside first
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        clean = tmp_project / "clean-prd.md"
        clean.write_text(sample_prd.read_text())
        prd.write_text(clean.read_text() + "\n\nOwner: TBD\n")
        r = subprocess.run(
            [_sys.executable, str(repo / "script.py"), "validate-prd", "--input", str(prd)],
            capture_output=True, text=True, cwd=tmp_project,
        )
        assert r.returncode == 1, r.stdout + r.stderr
        # clean copy exits 0
        r2 = subprocess.run(
            [_sys.executable, str(repo / "script.py"), "validate-prd", "--input", str(clean)],
            capture_output=True, text=True, cwd=tmp_project,
        )
        assert r2.returncode == 0, r2.stdout + r2.stderr


class TestWarningsAreLocated:
    """README/UI claim: warnings are 'quoted + located, not just counted'.
    Each vague-language and placeholder finding must carry a line number."""

    def test_vague_warnings_carry_line_numbers(self, tmp_project):
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        prd.write_text("# PRD\n\n## Executive Summary\nA summary.\n\n## Requirements\n- it must be fast\n")
        out = run_validate_prd(str(prd))
        vague = [w for w in out["warnings"] if w["type"] == "vague_language"]
        assert vague, "expected a vague-language warning"
        for w in vague:
            assert "term" in w                      # quoted
            assert w.get("lines") and all(isinstance(n, int) for n in w["lines"])  # located
            assert str(w["lines"][0]) in w["suggestion"]

    def test_placeholder_findings_carry_line_numbers(self, tmp_project):
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        prd.write_text("# PRD\n\n## Executive Summary\nA summary.\n\n## Plan\nOwner: TODO\n")
        out = run_validate_prd(str(prd))
        assert out["placeholder_details"], "expected a placeholder finding"
        for pd in out["placeholder_details"]:
            assert "match" in pd and isinstance(pd.get("line"), int) and pd["line"] >= 1


# ─── Helpers for run_validate_tasks tests ─────────────────────────────────────

def _make_tasks_file(tmp_path, tasks: list) -> str:
    """Write a tasks.json and return the path string."""
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps({"tasks": tasks}))
    return str(p)


def _good_task(**overrides) -> dict:
    """Return a minimal valid task, optionally overriding fields."""
    base = {
        "id": 1,
        "title": "Implement user authentication flow",
        "description": "Add JWT-based authentication to the REST API endpoints.",
        "details": "Use PyJWT library, store tokens in Redis with 24h TTL.",
        "testStrategy": "Write unit tests for token creation and expiry.",
        "status": "pending",
        "priority": "high",
        "dependencies": [],
    }
    base.update(overrides)
    return base


# ─── Regression tests for angle-bracket false-positive (Bug: IGNORECASE) ─────

def _validate_tasks_problems(path: str) -> list[str]:
    """Run run_validate_tasks and return the list of problem strings.

    run_validate_tasks raises CommandError when problems are found; that error
    carries the list in e.extra["problems"].  When the file is valid it returns
    {"ok": True, ...} with no problems key.
    """
    from prd_taskmaster.lib import CommandError as _CE
    try:
        run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        return []
    except _CE as exc:
        return exc.extra.get("problems", [])


class TestAngleBracketPlaceholderRegex:
    """Regression suite for the IGNORECASE false-positive in the angle-bracket
    placeholder sub-pattern (<[A-Z][A-Z_ ]+> compiled with re.IGNORECASE).

    Technical tokens like <code>, <lines>, <bytes>, <filename> are LEGITIMATE
    in task titles / descriptions (URL path params, wc output format) and must
    NOT be treated as placeholders.

    True template placeholders like <PLACEHOLDER>, <API_KEY>, <YOUR_VALUE>
    MUST still be caught.
    """

    # ── MUST NOT flag (legitimate technical tokens) ────────────────────────

    def test_url_path_param_code_in_title_not_flagged(self, tmp_path):
        """GET /<code> in a task title must not trigger placeholder detection."""
        task = _good_task(title="Implement GET /<code> Redirect Endpoint")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs == [], (
            f"<code> in title was falsely flagged as placeholder: {placeholder_probs}"
        )

    def test_wc_format_tokens_in_details_not_flagged(self, tmp_path):
        """<lines> <words> <bytes> <filename> in details must not be flagged."""
        task = _good_task(
            details="The wc command output format is: <lines> <words> <bytes> <filename>"
        )
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs == [], (
            f"wc format tokens were falsely flagged: {placeholder_probs}"
        )

    def test_lowercase_angle_token_code_not_flagged(self, tmp_path):
        """Standalone <code> token must not be flagged."""
        task = _good_task(description="Returns HTTP <code> on success.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs == [], (
            f"<code> in description was falsely flagged: {placeholder_probs}"
        )

    def test_lowercase_angle_token_id_not_flagged(self, tmp_path):
        """<id> in a task field must not be flagged."""
        task = _good_task(description="Fetch resource by <id> from the store.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs == [], (
            f"<id> in description was falsely flagged: {placeholder_probs}"
        )

    def test_lowercase_angle_token_file_not_flagged(self, tmp_path):
        """<file> in a task field must not be flagged."""
        task = _good_task(testStrategy="Run: process <file> and assert exit code is 0.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs == [], (
            f"<file> in testStrategy was falsely flagged: {placeholder_probs}"
        )

    # ── MUST still flag (real template placeholders) ───────────────────────

    def test_uppercase_placeholder_flagged(self, tmp_path):
        """<PLACEHOLDER> must be caught as a placeholder."""
        task = _good_task(title="Set up <PLACEHOLDER> integration")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "<PLACEHOLDER> was not caught as a placeholder"

    def test_uppercase_api_key_flagged(self, tmp_path):
        """<API_KEY> must be caught as a placeholder."""
        task = _good_task(details="Set the env var to <API_KEY> before deploying.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "<API_KEY> was not caught as a placeholder"

    def test_uppercase_your_value_flagged(self, tmp_path):
        """<YOUR_VALUE> must be caught as a placeholder."""
        task = _good_task(testStrategy="Replace <YOUR_VALUE> with the real token.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "<YOUR_VALUE> was not caught as a placeholder"

    def test_mustache_placeholder_flagged(self, tmp_path):
        """{{variable}} mustache tokens must still be caught."""
        task = _good_task(description="Connect to {{database_url}} endpoint.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "{{variable}} was not caught as a placeholder"

    def test_bracketed_todo_placeholder_flagged(self, tmp_path):
        """[TODO] token in a task field must still be caught."""
        task = _good_task(description="[TODO] fill in the implementation details.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "[TODO] was not caught as a placeholder"

    def test_bracketed_tbd_placeholder_flagged(self, tmp_path):
        """[TBD] token in a task field must still be caught."""
        task = _good_task(title="Integrate auth [TBD]")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "[TBD] was not caught as a placeholder"

    def test_insert_placeholder_flagged(self, tmp_path):
        """[INSERT something] token in a task field must still be caught."""
        task = _good_task(details="Contact [INSERT team name] for review.")
        problems = _validate_tasks_problems(_make_tasks_file(tmp_path, [task]))
        placeholder_probs = [p for p in problems if "placeholder" in p.lower()]
        assert placeholder_probs, "[INSERT ...] was not caught as a placeholder"

    # ── PRD-level: validate_prd must also not false-flag lowercase tokens ──

    def test_prd_lowercase_angle_tokens_not_flagged(self, tmp_project):
        """run_validate_prd must not false-flag <code>, <lines> etc. in PRD text."""
        prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        prd.write_text(
            "# PRD\n\n## Executive Summary\nA summary.\n\n"
            "## Functional Requirements\n"
            "### API Endpoints\n"
            "- `GET /<code>` — redirect by short code\n"
            "- wc output: `<lines> <words> <bytes> <filename>`\n"
        )
        out = run_validate_prd(str(prd))
        angle_bracket_details = [d for d in out.get("placeholder_details", [])
                                  if d.get("type") == "angle_bracket"]
        assert angle_bracket_details == [], (
            f"PRD false-flagged angle-bracket tokens: {angle_bracket_details}"
        )


def _task(tid, *, subtasks=2):
    """Build a minimally-valid manual-mode task."""
    subs = [
        {"id": i, "title": f"sub {i}", "description": "d", "status": "pending",
         "dependencies": ([i - 1] if i > 1 else [])}
        for i in range(1, subtasks + 1)
    ]
    return {
        "id": tid, "title": f"task {tid}", "description": "d", "details": "dd",
        "testStrategy": "verify X", "status": "pending", "priority": "high",
        "dependencies": [], "subtasks": subs,
    }


class TestValidateTasksTagResolution:
    """BUG2: validate-tasks must honor the active tag (explicit --tag, else
    state.json currentTag) and NOT silently validate a coexisting stale flat
    'tasks' key."""

    def _project(self, tmp_path, current_tag, *, flat=None, tagged=None):
        tm = tmp_path / ".taskmaster"
        (tm / "tasks").mkdir(parents=True)
        if current_tag is not None:
            (tm / "state.json").write_text(json.dumps({"currentTag": current_tag}))
        data = {}
        if flat is not None:
            data["tasks"] = flat
        for tag, tasks in (tagged or {}).items():
            data[tag] = {"tasks": tasks}
        (tm / "tasks" / "tasks.json").write_text(json.dumps(data, indent=2))
        return tm / "tasks" / "tasks.json"

    def test_currenttag_wins_over_coexisting_flat_key(self, tmp_path, monkeypatch):
        # flat key has 1 INVALID task (no subtasks); productization has 3 valid.
        flat = [{"id": 9, "title": "legacy", "description": "d", "details": "dd",
                 "testStrategy": "t", "status": "pending", "priority": "high",
                 "dependencies": [], "subtasks": []}]
        tagged = {"productization": [_task(i) for i in range(1, 4)]}
        path = self._project(tmp_path, "productization", flat=flat, tagged=tagged)
        monkeypatch.chdir(tmp_path)

        out = run_validate_tasks(str(path), allow_empty_subtasks=False,
                                 require_phase_config=False)
        assert out["ok"] is True
        assert out["tag"] == "productization"
        assert out["task_count"] == 3  # the tagged block, NOT the 1 flat task

    def test_explicit_tag_overrides_currenttag(self, tmp_path, monkeypatch):
        tagged = {
            "master": [_task(i) for i in range(1, 3)],
            "productization": [_task(i) for i in range(1, 6)],
        }
        path = self._project(tmp_path, "master", tagged=tagged)
        monkeypatch.chdir(tmp_path)

        out = run_validate_tasks(str(path), allow_empty_subtasks=False,
                                 require_phase_config=False, tag="productization")
        assert out["ok"] is True
        assert out["tag"] == "productization"
        assert out["task_count"] == 5

    def test_explicit_missing_tag_errors_not_silent_flat_fallback(self, tmp_path, monkeypatch):
        flat = [_task(1)]
        tagged = {"productization": [_task(i) for i in range(1, 3)]}
        path = self._project(tmp_path, "productization", flat=flat, tagged=tagged)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(CommandError) as exc:
            run_validate_tasks(str(path), allow_empty_subtasks=False,
                               require_phase_config=False, tag="nope")
        assert "not found" in str(exc.value).lower()
        assert "productization" in exc.value.extra.get("available_tags", [])

    def test_flat_only_backward_compat(self, tmp_path, monkeypatch):
        flat = [_task(i) for i in range(1, 4)]
        path = self._project(tmp_path, None, flat=flat)
        monkeypatch.chdir(tmp_path)

        out = run_validate_tasks(str(path), allow_empty_subtasks=False,
                                 require_phase_config=False)
        assert out["ok"] is True
        assert out["task_count"] == 3
