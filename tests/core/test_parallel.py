"""Roundtrip tests for the parallel research bridge via the unified CLI."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script.py"


def _run(cwd, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _seed_tasks(tmp_path):
    tasks_dir = tmp_path / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True)
    payload = {
        "master": {
            "tasks": [
                {"id": 1, "title": "Build auth", "description": "API key",
                 "details": "key check", "testStrategy": "unit",
                 "status": "pending", "subtasks": []},
                {"id": 2, "title": "List endpoint", "description": "GET /widgets",
                 "details": "paginated", "testStrategy": "integration",
                 "status": "pending", "dependencies": [1],
                 "subtasks": [{"id": 1, "title": "a", "description": "", "details": ""},
                              {"id": 2, "title": "b", "description": "", "details": ""}]},
            ]
        }
    }
    (tasks_dir / "tasks.json").write_text(json.dumps(payload))
    return tasks_dir / "tasks.json"


def test_parallel_plan_emits_packets(tmp_path):
    _seed_tasks(tmp_path)
    code, out, err = _run(tmp_path, "parallel-plan")
    assert code == 0, err
    data = json.loads(out)
    assert data["ok"] is True
    assert data["count"] == 2
    assert {p["id"] for p in data["packets"]} == {1, 2}
    assert "RESEARCH" in data["packets"][0]["prompt"]


def test_parallel_plan_missing_only_skips_expanded(tmp_path):
    _seed_tasks(tmp_path)
    code, out, _ = _run(tmp_path, "parallel-plan", "--missing-only")
    data = json.loads(out)
    # task 2 already has >=2 subtasks, so only task 1 needs research
    assert data["count"] == 1
    assert data["packets"][0]["id"] == 1


def test_parallel_apply_roundtrip(tmp_path):
    tasks_file = _seed_tasks(tmp_path)
    results = [
        {"id": 1, "complexityScore": 6, "recommendedSubtasks": 3,
         "reasoning": "moderate", "researchNotes": "use hmac",
         "subtasks": [
             {"title": "Parse header", "description": "x", "details": "y", "dependencies": []},
             {"title": "Validate key", "description": "x", "details": "y", "dependencies": [1]},
         ]},
    ]
    res_file = tmp_path / "results.json"
    res_file.write_text(json.dumps(results))

    code, out, err = _run(tmp_path, "parallel-apply", "--input", str(res_file))
    assert code == 0, err
    data = json.loads(out)
    assert data["ok"] is True
    assert data["applied"] == [1]

    # tasks.json now has the new subtasks merged for task 1
    merged = json.loads(tasks_file.read_text())
    task1 = merged["master"]["tasks"][0]
    assert len(task1["subtasks"]) == 2
    assert task1["subtasks"][0]["title"] == "Parse header"
    assert "use hmac" in task1["details"]

    # a complexity report was written
    report = tmp_path / ".taskmaster" / "reports" / "task-complexity-report.json"
    assert report.is_file()
    rep = json.loads(report.read_text())
    assert rep["complexityAnalysis"][0]["taskId"] == 1


def test_parallel_extract_inject_roundtrip(tmp_path):
    tasks_file = _seed_tasks(tmp_path)
    flat = tmp_path / "flat.json"
    code, out, err = _run(tmp_path, "parallel-extract", "--output", str(flat))
    assert code == 0, err
    assert json.loads(out)["count"] == 2

    # mutate the flat file then inject back
    data = json.loads(flat.read_text())
    data["tasks"][0]["title"] = "Build auth (edited)"
    flat.write_text(json.dumps(data))

    code, out, err = _run(tmp_path, "parallel-inject", "--input", str(flat))
    assert code == 0, err
    assert json.loads(out)["injected"] == 2

    merged = json.loads(tasks_file.read_text())
    assert merged["master"]["tasks"][0]["title"] == "Build auth (edited)"
