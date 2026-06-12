"""Minimal coverage for prd_taskmaster.validation.run_validate_prd.

Smoke-level assertion that run_validate_prd returns a graded dict. The
granular 13-check coverage (per-check assertions, grade boundaries, vague
penalties) lives in tests/core/test_validation.py, ported from the plugin's
test suite and adapted to this package's contract.
"""
from prd_taskmaster.validation import run_validate_prd


def test_run_validate_prd_returns_graded_dict(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\n## Executive Summary\nA test PRD.\n")
    result = run_validate_prd(str(prd))
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert "grade" in result
    assert "checks" in result
    assert isinstance(result["checks"], list) and len(result["checks"]) > 0
    assert "score" in result and "percentage" in result
