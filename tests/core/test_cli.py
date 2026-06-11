"""Representative end-to-end CLI tests for the prd_taskmaster package.

Each test invokes the root script.py shim via subprocess and asserts on key
fields of the emitted JSON, proving the CLI wiring and pure cores behave.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "script.py"
TEMPLATES = REPO_ROOT / "templates"


def run_cli(*args, expect_exit=0):
    """Run the CLI shim and return parsed JSON stdout."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == expect_exit, (
        f"exit={proc.returncode} expected={expect_exit}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    return json.loads(proc.stdout)


def test_calc_tasks_small_clamps_to_10():
    data = run_cli("calc-tasks", "--requirements", "3")
    assert data["ok"] is True
    assert data["recommended"] == 10
    assert data["raw_calculation"] == 5


def test_calc_tasks_mid_range():
    data = run_cli("calc-tasks", "--requirements", "12")
    assert data["recommended"] == 18
    assert data["requirements_count"] == 12


def test_calc_tasks_large_clamps_to_40():
    data = run_cli("calc-tasks", "--requirements", "40")
    assert data["recommended"] == 40


def test_load_template_minimal():
    data = run_cli("load-template", "--type", "minimal")
    assert data["ok"] is True
    assert data["type"] == "minimal"
    assert data["line_count"] > 0
    assert data["path"].endswith("taskmaster-prd-minimal.md")
    assert str(TEMPLATES) in data["path"]


def test_load_template_comprehensive():
    data = run_cli("load-template", "--type", "comprehensive")
    assert data["ok"] is True
    assert data["type"] == "comprehensive"
    assert "Executive Summary" in data["content"]


def test_validate_prd_returns_grade(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# Product Requirements: Widget API\n\n"
        "## Problem\nTeams lack a way to sync widgets.\n\n"
        "## Goals\n- REQ-001: The API must return widget lists in under 200ms p95.\n\n"
        "## Out of Scope\n- Billing.\n"
    )
    data = run_cli("validate-prd", "--input", str(prd))
    assert data["ok"] is True
    assert data["grade"] in {"EXCELLENT", "GOOD", "ACCEPTABLE", "NEEDS_WORK"}
    assert data["checks_total"] == 13
    assert 0 <= data["percentage"] <= 100


def test_validate_prd_missing_file_fails():
    data = run_cli("validate-prd", "--input", "does-not-exist.md", expect_exit=1)
    assert data["ok"] is False
    assert "not found" in data["error"]


def test_validate_tasks_valid_file(tmp_path):
    tasks = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Build the widget sync endpoint",
                    "description": "Implement the REST endpoint for syncing widgets",
                    "details": "Wire the route, handler, and serializer",
                    "testStrategy": "Unit and integration tests for the endpoint",
                    "priority": "high",
                    "status": "pending",
                    "dependencies": [],
                    "subtasks": [
                        {"id": 1, "title": "Define route", "description": "Add the URL route", "status": "pending", "dependencies": []},
                        {"id": 2, "title": "Write handler", "description": "Implement handler logic", "status": "pending", "dependencies": [1]},
                    ],
                }
            ]
        }
    }
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))
    data = run_cli("validate-tasks", "--input", str(tasks_file))
    assert data["ok"] is True
    assert data["task_count"] == 1
    assert data["subtask_count"] == 2


def test_enrich_tasks_adds_phase_config(tmp_path):
    tasks = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Research auth frameworks",
                    "description": "Evaluate options",
                    "priority": "high",
                    "status": "pending",
                    "subtasks": [],
                }
            ]
        }
    }
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))
    data = run_cli("enrich-tasks", "--input", str(tasks_file))
    assert data["ok"] is True
    assert data["enriched"] == 1
    written = json.loads(tasks_file.read_text())
    task = written["master"]["tasks"][0]
    assert task["phaseConfig"]["complexity"] == "RESEARCH"
    assert "acceptanceCriteria" in task["phaseConfig"]
