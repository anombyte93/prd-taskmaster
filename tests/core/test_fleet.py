"""Unit and CLI tests for the Atlas Fleet wave scheduler."""

import json
import subprocess
import sys
from pathlib import Path

from prd_taskmaster.fleet import compute_waves, ready_set

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script.py"


def _task(task_id, status="pending", dependencies=None):
    return {
        "id": task_id,
        "status": status,
        "dependencies": [] if dependencies is None else dependencies,
    }


def test_compute_waves_linear_chain():
    tasks = [
        _task(1),
        _task(2, dependencies=[1]),
        _task(3, dependencies=[2]),
    ]

    assert ready_set(tasks) == [1]
    assert compute_waves(tasks) == {
        "waves": [[1], [2], [3]],
        "blocked": [],
        "deadlocked": False,
    }


def _run_cli(cwd, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _write_tasks(tmp_path, payload, current_tag=None):
    tasks_dir = tmp_path / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "tasks.json").write_text(json.dumps(payload))
    if current_tag is not None:
        (tmp_path / ".taskmaster" / "state.json").write_text(
            json.dumps({"currentTag": current_tag})
        )


def test_fleet_waves_cli_uses_current_tag(tmp_path):
    _write_tasks(
        tmp_path,
        {
            "alpha": {
                "tasks": [
                    _task(1),
                    _task(2, dependencies=[1]),
                    _task(3, status="done"),
                ]
            }
        },
        current_tag="alpha",
    )

    code, out, err = _run_cli(tmp_path, "fleet-waves")

    assert code == 0, err
    data = json.loads(out)
    expected = {
        "ok": True,
        "tag": "alpha",
        "waves": [[1], [2]],
        "blocked": [],
        "deadlocked": False,
        "ready": [1],
        "concurrency": 3,
    }
    assert expected.items() <= data.items()
    assert set(data["routing"]) == {"1", "2"} and "backends" in data


def test_fleet_waves_cli_supports_flat_tasks_with_tag(tmp_path):
    _write_tasks(
        tmp_path,
        {
            "tasks": [
                _task(1),
                _task(2, dependencies=[1]),
            ]
        },
    )

    code, out, err = _run_cli(tmp_path, "fleet-waves", "--tag", "release")

    assert code == 0, err
    data = json.loads(out)
    assert data["ok"] is True
    assert data["tag"] == "release"
    assert data["waves"] == [[1], [2]]
    assert data["ready"] == [1]


def test_fleet_waves_cli_concurrency_override(tmp_path):
    _write_tasks(
        tmp_path,
        {
            "master": {
                "tasks": [
                    _task(1),
                    _task(2),
                    _task(3),
                ]
            }
        },
    )

    code, out, err = _run_cli(tmp_path, "fleet-waves", "--concurrency", "2")

    assert code == 0, err
    data = json.loads(out)
    assert data["concurrency"] == 2
    assert data["ready"] == [1, 2, 3]
    assert data["waves"] == [[1, 2], [3]]


def test_fleet_waves_cli_missing_tasks_json_fails(tmp_path):
    code, out, err = _run_cli(tmp_path, "fleet-waves")

    assert code == 1, err
    data = json.loads(out)
    assert data["ok"] is False
    assert ".taskmaster/tasks/tasks.json" in data["error"]
    assert "not found" in data["error"]


def test_compute_waves_diamond_dependency_preserves_input_order():
    tasks = [
        _task(1),
        _task(3, dependencies=[1]),
        _task(2, dependencies=[1]),
        _task(4, dependencies=[2, 3]),
    ]

    assert compute_waves(tasks) == {
        "waves": [[1], [3, 2], [4]],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_deadlock_cycle_lists_blocked_members():
    tasks = [
        _task(1, dependencies=[2]),
        _task(2, dependencies=[1]),
    ]

    assert compute_waves(tasks) == {
        "waves": [],
        "blocked": [1, 2],
        "deadlocked": True,
    }


def test_compute_waves_chunks_frontier_by_concurrency_in_input_order():
    tasks = [
        _task(5),
        _task(1),
        _task(4),
        _task(2),
        _task(3),
    ]

    assert compute_waves(tasks, max_concurrency=2) == {
        "waves": [[5, 1], [4, 2], [3]],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_empty_graph():
    assert compute_waves([]) == {
        "waves": [],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_all_done_graph():
    tasks = [
        _task(1, status="done"),
        _task(2, status="done", dependencies=[1]),
    ]

    assert ready_set(tasks) == []
    assert compute_waves(tasks) == {
        "waves": [],
        "blocked": [],
        "deadlocked": False,
    }
