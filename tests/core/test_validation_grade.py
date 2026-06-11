"""Minimal coverage for prd_taskmaster.validation.run_validate_prd.

The plugin's test_validation.py (14-check) was DROPPED — it asserted the
plugin's now-removed validation.py. The package's skill validation (13-check)
is canonical and is exercised by tests/core/test_cli.py. This adds one direct
assertion that run_validate_prd returns a graded dict.
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
