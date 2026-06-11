"""Task state operation tests for native TaskMaster parity."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from prd_taskmaster.lib import CommandError

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script.py"


def _task(
    task_id,
    *,
    title=None,
    status="pending",
    priority="medium",
    dependencies=None,
    subtasks=None,
):
    return {
        "id": task_id,
        "title": title or f"Task {task_id}",
        "description": f"Description {task_id}",
        "details": f"Details {task_id}",
        "testStrategy": f"Test {task_id}",
        "status": status,
        "priority": priority,
        "dependencies": [] if dependencies is None else dependencies,
        "subtasks": [] if subtasks is None else subtasks,
    }


def _subtask(subtask_id, *, title=None, status="pending", dependencies=None):
    return {
        "id": subtask_id,
        "title": title or f"Subtask {subtask_id}",
        "description": f"Sub description {subtask_id}",
        "details": f"Sub details {subtask_id}",
        "status": status,
        "dependencies": [] if dependencies is None else dependencies,
    }


def _tagged_payload(tasks, tag="master"):
    return {
        tag: {
            "tasks": tasks,
            "metadata": {
                "created": "2026-01-01T00:00:00.000Z",
                "updated": "2026-01-01T00:00:00.000Z",
                "description": f"Tasks for {tag} context",
            },
        }
    }


def _write_project(tmp_path, payload, *, current_tag="master"):
    tasks_dir = tmp_path / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "tasks.json").write_text(json.dumps(payload, indent=2))
    (tmp_path / ".taskmaster" / "state.json").write_text(
        json.dumps({"currentTag": current_tag, "migrationNoticeShown": True})
    )
    return tasks_dir / "tasks.json"


def _write_taskmaster_config(tmp_path):
    (tmp_path / ".taskmaster").mkdir(exist_ok=True)
    (tmp_path / ".taskmaster" / "config.json").write_text(
        json.dumps(
            {
                "models": {
                    "main": {
                        "provider": "claude-code",
                        "modelId": "sonnet",
                        "maxTokens": 64000,
                        "temperature": 0.2,
                    },
                    "research": {
                        "provider": "openai-compatible",
                        "modelId": "sonar",
                        "maxTokens": 8700,
                        "temperature": 0.1,
                        "baseURL": "http://localhost:8765",
                    },
                    "fallback": {
                        "provider": "claude-code",
                        "modelId": "sonnet",
                        "maxTokens": 64000,
                        "temperature": 0.2,
                    },
                },
                "global": {
                    "logLevel": "error",
                    "debug": False,
                    "defaultNumTasks": 10,
                    "defaultSubtasks": 5,
                    "defaultPriority": "medium",
                    "projectName": "Task Master",
                    "responseLanguage": "English",
                    "defaultTag": "master",
                },
                "claudeCode": {},
                "codexCli": {},
                "grokCli": {
                    "timeout": 120000,
                    "workingDirectory": None,
                    "defaultModel": "grok-4-latest",
                },
            },
            indent=2,
        )
    )


def _run_cli(cwd, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_next_task_orders_ready_by_priority_before_id_and_dependency_count(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_next_task

    _write_project(
        tmp_path,
        _tagged_payload(
            [
                _task(1, title="Low id low priority", priority="low"),
                _task(2, status="done", priority="high"),
                _task(3, title="High id high priority", priority="high"),
                _task(4, title="Blocked", priority="high", dependencies=[99]),
                _task(5, title="Medium with dependency", dependencies=[2]),
                _task(6, title="Medium without dependency"),
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    result = run_next_task()

    assert result["ok"] is True
    assert result["tag"] == "master"
    assert result["ready_count"] == 4
    assert result["source"] == "ready"
    assert result["task"]["id"] == 3
    assert result["task"]["title"] == "High id high priority"


def test_next_task_resumes_in_progress_ready_subtask_before_ready_parent(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_next_task

    _write_project(
        tmp_path,
        _tagged_payload(
            [
                _task(
                    1,
                    title="Resume parent",
                    status="in-progress",
                    priority="low",
                    subtasks=[
                        _subtask(1, title="Blocked sibling", dependencies=[2]),
                        _subtask(2, title="Ready sibling"),
                    ],
                ),
                _task(2, title="Ready high parent", priority="high"),
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    result = run_next_task()

    assert result["ok"] is True
    assert result["source"] == "in-progress"
    assert result["ready_count"] == 1
    assert result["task"]["id"] == "1.2"
    assert result["task"]["title"] == "Ready sibling"
    assert result["task"]["status"] == "pending"
    assert result["task"]["priority"] == "low"
    assert result["task"]["parent_id"] == "1"
    assert result["task"]["parent_title"] == "Resume parent"


def test_next_task_all_done_returns_none_source_none(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_next_task

    _write_project(
        tmp_path,
        _tagged_payload([_task(1, status="done"), _task(2, status="done")]),
    )
    monkeypatch.chdir(tmp_path)

    result = run_next_task()

    assert result["ok"] is True
    assert result["task"] is None
    assert result["ready_count"] == 0
    assert result["source"] == "none"


def test_next_task_supports_flat_tasks_file_with_explicit_tag(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_next_task

    _write_project(tmp_path, {"tasks": [_task(7, priority="high")]}, current_tag="other")
    monkeypatch.chdir(tmp_path)

    result = run_next_task(tag="release")

    assert result["ok"] is True
    assert result["tag"] == "release"
    assert result["source"] == "ready"
    assert result["task"]["id"] == 7


def test_set_status_updates_subtask_without_auto_done_parent(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_set_status

    tasks_file = _write_project(
        tmp_path,
        _tagged_payload(
            [
                _task(
                    3,
                    status="in-progress",
                    subtasks=[_subtask(1), _subtask(2, status="done")],
                )
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    result = run_set_status("3.1", "done")

    assert result == {
        "ok": True,
        "tag": "master",
        "id": "3.1",
        "status": "done",
        "kind": "subtask",
    }
    written = json.loads(tasks_file.read_text())
    task = written["master"]["tasks"][0]
    assert task["status"] == "in-progress"
    assert [sub["status"] for sub in task["subtasks"]] == ["done", "done"]


def test_set_status_rejects_unknown_id_and_status(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_set_status

    _write_project(tmp_path, _tagged_payload([_task(1)]))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError) as id_exc:
        run_set_status("9.1", "done")
    assert "unknown id" in id_exc.value.message.lower()

    with pytest.raises(CommandError) as status_exc:
        run_set_status("1", "started")
    assert "unknown status" in status_exc.value.message.lower()


def test_set_status_two_sequential_locked_updates_both_land(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_set_status

    tasks_file = _write_project(tmp_path, _tagged_payload([_task(1), _task(2)]))
    monkeypatch.chdir(tmp_path)

    first = run_set_status("1", "in-progress")
    second = run_set_status("2", "blocked")

    assert first["kind"] == "task"
    assert second["kind"] == "task"
    written = json.loads(tasks_file.read_text())
    statuses = {task["id"]: task["status"] for task in written["master"]["tasks"]}
    assert statuses == {1: "in-progress", 2: "blocked"}


def test_task_state_cli_next_task_and_set_status(tmp_path):
    tasks_file = _write_project(tmp_path, _tagged_payload([_task(1)]))

    code, out, err = _run_cli(tmp_path, "next-task")
    assert code == 0, err
    data = json.loads(out)
    assert data["ok"] is True
    assert data["task"]["id"] == 1

    code, out, err = _run_cli(tmp_path, "set-status", "--id", "1", "--status", "review")
    assert code == 0, err
    assert json.loads(out)["kind"] == "task"
    written = json.loads(tasks_file.read_text())
    assert written["master"]["tasks"][0]["status"] == "review"


@pytest.mark.skipif(shutil.which("task-master") is None, reason="task-master not on PATH")
def test_run_next_task_matches_live_taskmaster_in_progress_subtask(tmp_path, monkeypatch):
    from prd_taskmaster.task_state import run_next_task

    _write_taskmaster_config(tmp_path)
    _write_project(
        tmp_path,
        _tagged_payload(
            [
                _task(
                    1,
                    title="Resume parent",
                    status="in-progress",
                    priority="high",
                    subtasks=[
                        _subtask(1, title="Blocked sibling", dependencies=[2]),
                        _subtask(2, title="Ready sibling"),
                    ],
                ),
                _task(2, title="Ready parent", priority="high"),
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    local = run_next_task(tag="master")
    proc = subprocess.run(
        ["task-master", "next", "--format", "json", "--project", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    live = json.loads(proc.stdout)
    assert local["source"] == "in-progress"
    assert local["task"]["id"] == live["task"]["id"] == "1.2"
    assert local["task"]["title"] == live["task"]["title"]
    assert local["task"]["status"] == live["task"]["status"]
    assert local["task"]["parent_id"] == live["task"]["parentId"]
    assert local["task"]["parent_title"] == "Resume parent"
