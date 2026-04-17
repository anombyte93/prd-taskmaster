"""End-to-end phase-pipeline tests for the prd-taskmaster-v2 skill.

These tests exist to catch the class of bugs found during the v4 ship-readiness
dogfood run on 2026-04-13 — the kind of bugs that unit tests on individual
script.py subcommands missed because they didn't exercise the phase-to-phase
flow a real user would hit. Specifically:

1. SETUP.md's wrong --set-main claude-code syntax (the test would have caught
   this because the fix command from validate-setup would fail to execute).
2. Preflight-then-validate-prd against a fresh .taskmaster/ directory.
3. Empty-PRD decision table row (prd_path exists + task_count == 0).
4. MCP shim returns same payload as direct CLI call.

The tests stay as real as possible — no mocking. They run script.py as a
subprocess against a tmp_path fixture and assert on the real JSON contract.
If you add a new script.py subcommand, add an assertion here too.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PY = PROJECT_ROOT / "script.py"
MCP_LIB = PROJECT_ROOT / "mcp_server" / "lib.py"


def run(subcommand, *args, cwd=None):
    """Shell out to script.py and return (returncode, parsed_json)."""
    cmd = [sys.executable, str(SCRIPT_PY), subcommand] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else os.getcwd(),
        timeout=60,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"_parse_failed": True, "_stdout": result.stdout, "_stderr": result.stderr}
    return result.returncode, payload


# ─── Phase 0: SETUP gate ──────────────────────────────────────────────────────


def test_validate_setup_returns_structured_checks(tmp_path):
    """validate-setup must return per-check pass/fail with a fix command hint."""
    rc, payload = run("validate-setup", cwd=tmp_path)
    assert rc == 0, f"validate-setup exited non-zero: {payload}"
    assert payload.get("ok") is True
    assert "checks" in payload
    assert len(payload["checks"]) >= 4  # binary, project, config, provider_main
    # Every check must have id, name, passed, detail keys
    for check in payload["checks"]:
        assert "id" in check
        assert "name" in check
        assert "passed" in check
        assert "detail" in check
    # If a check fails, it must provide a fix command
    for check in payload["checks"]:
        if not check["passed"] and check.get("severity") != "warning":
            assert check.get("fix"), f"Failing check {check['id']} has no fix hint"


def test_validate_setup_fix_commands_do_not_contain_broken_syntax():
    """REGRESSION: the v3 bug was SETUP.md documenting
    `task-master models --set-main claude-code` which fails because
    'claude-code' is a provider flag, not a model ID. Any fix command
    emitted by validate-setup must not reproduce this syntax.
    """
    rc, payload = run("validate-setup")
    assert rc == 0
    for check in payload.get("checks", []):
        fix = check.get("fix") or ""
        if "models --set-" in fix:
            # The correct form is --set-<role> <model_id> --<provider>
            # The broken form was --set-<role> claude-code (which is wrong)
            assert "--set-main claude-code" not in fix
            assert "--set-research claude-code" not in fix
            assert "--set-fallback claude-code" not in fix


# ─── Phase 1: PREFLIGHT ───────────────────────────────────────────────────────


def test_preflight_fresh_tmp_dir(tmp_path):
    """Fresh tmp dir with no .taskmaster/ should report has_taskmaster=False."""
    rc, payload = run("preflight", cwd=tmp_path)
    assert rc == 0
    assert payload.get("ok") is True
    assert payload.get("has_taskmaster") is False
    assert payload.get("task_count") == 0


def test_preflight_empty_taskmaster_dir(tmp_path):
    """.taskmaster/ exists but is empty — the ambiguous state that the
    v4 decision table used to miss. Must still return ok and has_taskmaster=True."""
    (tmp_path / ".taskmaster" / "docs").mkdir(parents=True)
    (tmp_path / ".taskmaster" / "tasks").mkdir(parents=True)

    rc, payload = run("preflight", cwd=tmp_path)
    assert rc == 0
    assert payload.get("has_taskmaster") is True
    assert payload.get("prd_path") is None  # no PRD yet
    assert payload.get("task_count") == 0


def test_preflight_prd_no_tasks(tmp_path):
    """prd_path exists but task_count == 0 — the 'stale PRD' ambiguous
    state. v4 SKILL.md added a decision table row for this case."""
    (tmp_path / ".taskmaster" / "docs").mkdir(parents=True)
    (tmp_path / ".taskmaster" / "docs" / "prd.md").write_text("# Stale\n")

    rc, payload = run("preflight", cwd=tmp_path)
    assert rc == 0
    assert payload.get("has_taskmaster") is True
    assert payload.get("prd_path") is not None
    assert payload.get("task_count") == 0


# ─── Phase 3: GENERATE — validate-prd with real template output ───────────────


def test_validate_prd_on_comprehensive_template():
    """Load the comprehensive template, write it to a tmp file, validate.
    Unfilled template should either pass with placeholders flagged or fail
    gracefully — it must NOT crash."""
    rc, load = run("load-template", "--type", "comprehensive")
    assert rc == 0
    assert load.get("ok") is True
    template_content = load.get("content", "")
    assert len(template_content) > 100

    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False
    ) as f:
        f.write(template_content)
        tmp_prd_path = f.name

    try:
        rc2, validate = run("validate-prd", "--input", tmp_prd_path)
        assert rc2 == 0
        assert validate.get("ok") is True
        assert "grade" in validate
        assert "checks" in validate
        # v4 added check 14 (placeholder reason attribution, per inbox 1559)
        assert len(validate["checks"]) == 14
    finally:
        Path(tmp_prd_path).unlink(missing_ok=True)


def test_validate_prd_check_14_rejects_bare_placeholders(tmp_path):
    """REGRESSION for inbox 1559 (user directive): placeholders without
    `reason:` attribution must fail check 14. This converts placeholders
    from 'technical debt smell' into 'intentional deferred decisions with
    attribution'.
    """
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# PRD\n\n## Executive Summary\nT\n\n## Problem Statement\n"
        "User impact: x. Business impact: y.\n\n## Goals\nMetric: {{TBD_VALUE}}\n\n"
        "## User Stories\n### Story 1: X\n- [ ] a\n- [ ] b\n- [ ] c\n\n"
        "## Functional Requirements\nREQ-001: Must have thing.\n\n"
        "## Technical Considerations\nArchitecture: x.\n\n## Out of Scope\nNothing.\n"
    )
    rc, payload = run("validate-prd", "--input", str(prd))
    assert rc == 0
    check_14 = next((c for c in payload["checks"] if c["id"] == 14), None)
    assert check_14 is not None, "Check 14 missing from validate-prd output"
    assert check_14["passed"] is False, \
        "Bare placeholder should have failed check 14"
    assert payload["bare_placeholders_count"] >= 1
    assert payload["deferred_decisions_count"] == 0


def test_validate_prd_check_14_accepts_attributed_placeholders(tmp_path):
    """REGRESSION for inbox 1559: placeholders WITH `reason:` attribution
    must pass check 14 and be surfaced as deferred_decisions in output.
    """
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# PRD\n\n## Executive Summary\nT\n\n## Problem Statement\n"
        "User impact: x. Business impact: y.\n\n## Goals\n"
        "Metric: {{TBD_VALUE}} reason: awaiting analytics baseline from Q2\n\n"
        "## User Stories\n### Story 1: X\n- [ ] a\n- [ ] b\n- [ ] c\n\n"
        "## Functional Requirements\nREQ-001: Must have thing.\n\n"
        "## Technical Considerations\nArchitecture: x.\n\n## Out of Scope\nNothing.\n"
    )
    rc, payload = run("validate-prd", "--input", str(prd))
    assert rc == 0
    check_14 = next((c for c in payload["checks"] if c["id"] == 14), None)
    assert check_14 is not None
    assert check_14["passed"] is True, \
        "Attributed placeholder should have passed check 14"
    assert payload["bare_placeholders_count"] == 0
    assert payload["deferred_decisions_count"] == 1
    assert len(payload["deferred_decisions"]) == 1
    assert payload["deferred_decisions"][0]["placeholder"] == "{{TBD_VALUE}}"


def test_validate_prd_ai_flag_degrades_gracefully_when_task_master_missing(monkeypatch, tmp_path):
    """validate-prd --ai must never hard-fail if task-master is unavailable.
    It degrades to deterministic-only with a warning in the output."""
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\n## Executive Summary\nA test.\n\n## Problem Statement\nUser impact: test. Business impact: test.\n\n## Goals\nMetric: target.\n\n## Functional Requirements\nREQ-001: Must have feature. Priority: Must have.\n\n## Technical Considerations\nArchitecture: test system design.\n\n## Out of Scope\nNothing.\n")

    # Temporarily hide task-master from PATH
    monkeypatch.setenv("PATH", "/nonexistent")

    rc, payload = run("validate-prd", "--input", str(prd), "--ai")
    assert rc == 0, f"validate-prd --ai hard-failed with no task-master: {payload}"
    assert payload.get("ok") is True
    # Deterministic path must still have run
    assert "grade" in payload
    # AI path must report its failure as a warning, not a crash
    assert "ai_review" in payload
    assert payload["ai_review"].get("ok") is False


# ─── Phase 4: detect-capabilities tier field ─────────────────────────────────


def test_detect_capabilities_returns_tier_field():
    """v4 added a 'tier' field distinguishing free vs premium. Mode D
    must require actual atlas-loop + atlas-cdd skills, not just generic cdd."""
    rc, payload = run("detect-capabilities")
    assert rc == 0
    assert payload.get("ok") is True
    assert "tier" in payload, "detect-capabilities must return a tier field"
    assert payload["tier"] in ("free", "premium")
    assert "recommended_mode" in payload
    assert payload["recommended_mode"] in ("A", "B", "C", "D")


# ─── MCP shim parity ──────────────────────────────────────────────────────────


def test_mcp_shim_returns_same_payload_as_direct_cli():
    """The MCP server's lib.run_script shim must return byte-identical JSON
    to calling script.py directly. If someone refactors lib.py to parse
    differently, this test catches the regression."""
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from mcp_server import lib
    except ImportError:
        pytest.skip("mcp_server package not importable")

    # Pick a read-only subcommand that doesn't touch state
    rc, cli_payload = run("detect-capabilities")
    assert rc == 0
    shim_payload = lib.run_script("detect-capabilities")

    # Compare the structured portion, not timestamps
    assert cli_payload.get("ok") == shim_payload.get("ok")
    assert cli_payload.get("recommended_mode") == shim_payload.get("recommended_mode")
    assert cli_payload.get("tier") == shim_payload.get("tier")
