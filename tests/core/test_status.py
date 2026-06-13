"""Status renderer integration: reads seeded state and renders panels;
validate-prd persists its result so the scorecard is a pure reader."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script.py"


def _seed(tmp_path, phase="EXECUTE"):
    state = tmp_path / ".atlas-ai" / "state"
    state.mkdir(parents=True)
    (state / "pipeline.json").write_text(json.dumps({
        "current_phase": phase,
        "phases_completed": ["SETUP", "DISCOVER", "GENERATE", "HANDOFF"],
    }))
    (state / "validation.json").write_text(json.dumps({
        "ok": True, "grade": "GOOD", "score": 49, "max_score": 57, "percentage": 86,
        "checks_passed": 11, "warnings": [{"term": "fast", "lines": [7]}],
        "placeholders_found": 0, "hard_fail": None,
    }))
    tasks = tmp_path / ".taskmaster" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "tasks.json").write_text(json.dumps({
        "master": {"tasks": [
            {"id": 1, "status": "done", "subtasks": [{"id": 1, "status": "done"}]},
            {"id": 2, "status": "done", "subtasks": []},
        ]}
    }))
    return tmp_path


def _run(tmp_path, *args, expect=0):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "status", *args],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == expect, proc.stdout + proc.stderr
    return proc.stdout


def test_status_boxed_prints_panels(tmp_path):
    _seed(tmp_path)
    out = _run(tmp_path)
    assert "┌" in out and "│" in out          # boxed
    assert "Grade: GOOD" in out
    assert "49/57 (86%)" in out


def test_status_ascii_has_no_box_unicode(tmp_path):
    _seed(tmp_path)
    out = _run(tmp_path, "--format", "ascii")
    assert "┌" not in out and "│" not in out
    assert "[ok]" in out or "#" in out


def test_status_json_returns_structured(tmp_path):
    _seed(tmp_path)
    out = _run(tmp_path, "--format", "json")
    data = json.loads(out)
    assert data["ok"] is True
    assert data["phase"] == "EXECUTE"
    assert "rendered" in data and "panels" in data


def test_status_degrades_without_validation(tmp_path):
    # pipeline at GENERATE but no validation.json yet → honest "not generated"
    state = tmp_path / ".atlas-ai" / "state"
    state.mkdir(parents=True)
    (state / "pipeline.json").write_text(json.dumps({"current_phase": "GENERATE", "phases_completed": []}))
    out = _run(tmp_path)
    assert "not generated" in out.lower() or "No PRD validated" in out


def test_validate_prd_persists_result(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\n## Executive Summary\nA test summary for persistence.\n")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "validate-prd", "--input", str(prd)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    persisted = tmp_path / ".atlas-ai" / "state" / "validation.json"
    assert persisted.exists()
    data = json.loads(persisted.read_text())
    assert data["ok"] is True and "grade" in data
