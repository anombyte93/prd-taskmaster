"""Full MCP surface end-to-end integration (retargeted to the merged repo).

Originally the plugin's tests/test_integration.py. Retargeted:
  - imports now come from prd_taskmaster.* (pipeline, templates, mode_recommend)
    and the MCP server at mcp-server/server.py;
  - the plugin's stricter 14-check validate_prd is gone — the package's
    canonical 13-check skill validation is asserted instead;
  - validate_prd(ai=True) no longer produces an ai_review stub: the server
    wrapper accepts `ai` for forward-compat but the deterministic path is
    canonical. The test asserts graceful (non-crashing) completion.

Guarded with importorskip("mcp") because importing the server pulls in the
mcp package.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))

from prd_taskmaster import pipeline as P  # noqa: E402
from prd_taskmaster import templates as TPL  # noqa: E402
from prd_taskmaster.mode_recommend import (  # noqa: E402
    detect_capabilities,
    validate_setup,
)
import server as S  # noqa: E402


# ─── Phase 0: SETUP gate ──────────────────────────────────────────────────────


def test_validate_setup_returns_structured_checks(tmp_path, monkeypatch):
    """validate_setup must return per-check pass/fail with a fix hint on failures."""
    monkeypatch.chdir(tmp_path)
    payload = validate_setup()
    assert payload.get("ok") is True
    assert "checks" in payload
    assert len(payload["checks"]) >= 4
    for check in payload["checks"]:
        assert "id" in check
        assert "name" in check
        assert "passed" in check
        assert "detail" in check
    for check in payload["checks"]:
        if not check["passed"] and check.get("severity") not in ("warning", "advisory"):
            assert check.get("fix"), f"Failing check {check['id']} has no fix hint"


def test_validate_setup_fix_commands_do_not_contain_broken_syntax(tmp_path, monkeypatch):
    """REGRESSION: SETUP.md once documented `task-master models --set-main claude-code`
    which fails because 'claude-code' is a provider flag, not a model ID. Any fix
    command emitted must not reproduce this syntax.
    """
    monkeypatch.chdir(tmp_path)
    payload = validate_setup()
    for check in payload.get("checks", []):
        fix = check.get("fix") or ""
        if "models --set-" in fix:
            assert "--set-main claude-code" not in fix
            assert "--set-research claude-code" not in fix
            assert "--set-fallback claude-code" not in fix


# ─── Phase 1: PREFLIGHT ───────────────────────────────────────────────────────


def test_preflight_fresh_tmp_dir(tmp_path, monkeypatch):
    """Fresh dir with no .taskmaster/ reports has_taskmaster=False."""
    monkeypatch.chdir(tmp_path)
    payload = P.preflight()
    assert payload.get("ok") is True
    assert payload.get("has_taskmaster") is False
    assert payload.get("task_count", 0) == 0


def test_preflight_empty_taskmaster_dir(tmp_path, monkeypatch):
    """.taskmaster/ exists but empty — ambiguous state."""
    (tmp_path / ".taskmaster" / "docs").mkdir(parents=True)
    (tmp_path / ".taskmaster" / "tasks").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    payload = P.preflight()
    assert payload.get("has_taskmaster") is True
    assert payload.get("prd_path") is None
    assert payload.get("task_count", 0) == 0


def test_preflight_prd_no_tasks(tmp_path, monkeypatch):
    """Stale-PRD state: prd_path set but task_count == 0."""
    (tmp_path / ".taskmaster" / "docs").mkdir(parents=True)
    (tmp_path / ".taskmaster" / "docs" / "prd.md").write_text("# Stale\n")

    monkeypatch.chdir(tmp_path)
    payload = P.preflight()
    assert payload.get("has_taskmaster") is True
    assert payload.get("prd_path") is not None
    assert payload.get("task_count", 0) == 0


# ─── Phase 3: GENERATE — validate_prd integration ─────────────────────────────


def test_validate_prd_on_comprehensive_template(tmp_path):
    """Integration: load_template -> validate_prd. An unfilled template must
    not crash — it grades against the canonical 13-check skill validation."""
    load = TPL.run_load_template("comprehensive")
    assert load.get("ok") is True
    template_content = load.get("content", "")
    assert len(template_content) > 100

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, dir=tmp_path
    ) as f:
        f.write(template_content)
        tmp_prd_path = f.name

    try:
        payload = S.validate_prd(tmp_prd_path)
        assert payload.get("ok") is True
        assert "grade" in payload
        assert "checks" in payload
        # Canonical skill validation: 13 checks (the plugin's 14th
        # placeholder-attribution check was removed in the merge).
        assert len(payload["checks"]) == 13
    finally:
        Path(tmp_prd_path).unlink(missing_ok=True)


def test_validate_prd_grades_a_thin_prd(tmp_path):
    """A thin PRD still grades cleanly (graded dict, never a crash)."""
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# PRD\n\n## Executive Summary\nT\n\n## Problem Statement\n"
        "User impact: x. Business impact: y.\n\n## Goals\nMetric: target.\n\n"
        "## User Stories\n### Story 1: X\n- [ ] a\n- [ ] b\n- [ ] c\n\n"
        "## Functional Requirements\nREQ-001: Must have thing.\n\n"
        "## Technical Considerations\nArchitecture: x.\n\n## Out of Scope\nNothing.\n"
    )
    payload = S.validate_prd(str(prd))
    assert payload.get("ok") is True
    assert "grade" in payload
    assert "score" in payload and "percentage" in payload
    assert isinstance(payload.get("placeholders_found"), int)


def test_validate_prd_ai_flag_degrades_gracefully_when_task_master_missing(
    monkeypatch, tmp_path
):
    """validate_prd(ai=True) must never hard-fail when task-master is unavailable.
    LIVE behavior: the server wrapper accepts `ai` for forward-compat but runs
    only the deterministic 13-check path (no ai_review stub). The call must
    complete and return a graded dict."""
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# PRD\n\n## Executive Summary\nA test.\n\n"
        "## Problem Statement\nUser impact: test. Business impact: test.\n\n"
        "## Goals\nMetric: target.\n\n"
        "## Functional Requirements\nREQ-001: Must have feature. Priority: Must have.\n\n"
        "## Technical Considerations\nArchitecture: test system design.\n\n"
        "## Out of Scope\nNothing.\n"
    )
    monkeypatch.setenv("PATH", "/nonexistent")

    payload = S.validate_prd(str(prd), ai=True)
    assert payload.get("ok") is True, (
        f"validate_prd ai=True hard-failed with no task-master: {payload}"
    )
    assert "grade" in payload, "Deterministic path must still have run"


# ─── Phase 4: detect_capabilities tier field ─────────────────────────────────


def test_detect_capabilities_returns_tier_field(tmp_path, monkeypatch):
    """detect_capabilities returns a `tier` (free|premium) and recommended_mode."""
    monkeypatch.chdir(tmp_path)
    payload = detect_capabilities()
    assert payload.get("ok") is True
    assert "tier" in payload, "detect_capabilities must return a tier field"
    assert payload["tier"] in ("free", "premium")
    assert "recommended_mode" in payload
    assert payload["recommended_mode"] in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")


# ─── MCP surface parity ───────────────────────────────────────────────────────


def test_mcp_server_module_imports_cleanly():
    """The merged MCP server.py must be importable without side effects — the
    @mcp.tool() registrations should not raise."""
    assert hasattr(S, "mcp"), "FastMCP instance 'mcp' must be exported"
    assert hasattr(S, "preflight"), "preflight tool must be registered"
    assert hasattr(S, "validate_prd"), "validate_prd tool must be registered"
    assert hasattr(S, "detect_capabilities"), "detect_capabilities tool must be registered"


def test_mcp_direct_import_returns_dict(tmp_path, monkeypatch):
    """Every MCP tool returns a plain dict, not a sys.exit'd JSON blob. This is
    what makes direct-import tests possible. Verify across four tools."""
    monkeypatch.chdir(tmp_path)
    p1 = P.preflight()
    assert isinstance(p1, dict) and "ok" in p1

    p2 = TPL.run_load_template("minimal")
    assert isinstance(p2, dict) and "ok" in p2

    p3 = detect_capabilities()
    assert isinstance(p3, dict) and "ok" in p3

    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\n## Executive Summary\nT\n")
    p4 = S.validate_prd(str(prd))
    assert isinstance(p4, dict) and "ok" in p4
