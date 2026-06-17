"""TDD: set-status done — tier-gated reachability + evidence persistence.

Design:
- status != "done": evidence_ref / reachability ignored → unchanged behavior.
- status == "done" on wired/live task: requires reachability dict w/ WIRED or EXEMPT verdict.
  - absent reachability → CommandError
  - ORPHAN / ERROR verdict → CommandError
  - WIRED / EXEMPT verdict → ok, evidence persisted
- status == "done" on domain-model / untiered task: bare flip (backward-compat).
- evidence_ref / reachability persisted on the task object when provided (any tier).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prd_taskmaster.lib import CommandError
from prd_taskmaster.task_state import run_set_status

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(task_id, *, tier=None, status="pending"):
    t = {
        "id": task_id,
        "title": f"Task {task_id}",
        "description": f"Description {task_id}",
        "details": f"Details {task_id}",
        "testStrategy": f"Test {task_id}",
        "status": status,
        "priority": "medium",
        "dependencies": [],
        "subtasks": [],
    }
    if tier is not None:
        t["phaseConfig"] = {"tier": tier}
    return t


def _write_project(tmp_path, tasks, *, tag="master"):
    payload = {
        tag: {
            "tasks": tasks,
            "metadata": {
                "created": "2026-01-01T00:00:00.000Z",
                "updated": "2026-01-01T00:00:00.000Z",
                "description": f"Tasks for {tag}",
            },
        }
    }
    tasks_dir = tmp_path / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True)
    f = tasks_dir / "tasks.json"
    f.write_text(json.dumps(payload, indent=2))
    (tmp_path / ".taskmaster" / "state.json").write_text(
        json.dumps({"currentTag": tag, "migrationNoticeShown": True})
    )
    return f


def _reload(tasks_file, tag="master"):
    raw = json.loads(tasks_file.read_text())
    return {str(t["id"]): t for t in raw[tag]["tasks"]}


# ---------------------------------------------------------------------------
# 1. Backward-compat: untiered / domain-model task done without evidence → ok
# ---------------------------------------------------------------------------


def test_untiered_done_no_evidence_ok(tmp_path, monkeypatch):
    """Untiered task (falls back to domain-model) → bare flip, no raise."""
    tasks_file = _write_project(tmp_path, [_task(1)])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "done")

    assert result["ok"] is True
    assert result["status"] == "done"
    assert result["kind"] == "task"
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "done"
    # No doneEvidence persisted when none provided
    assert "doneEvidence" not in tasks["1"]


def test_domain_model_done_no_evidence_ok(tmp_path, monkeypatch):
    """Explicit domain-model tier → bare flip, no raise."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="domain-model")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "done")

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "done"


def test_spike_done_no_evidence_ok(tmp_path, monkeypatch):
    """spike tier → bare flip (same as domain-model), no raise."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="spike")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "done")

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "done"


# ---------------------------------------------------------------------------
# 2. wired requires reachability
# ---------------------------------------------------------------------------


def test_wired_done_without_reachability_raises(tmp_path, monkeypatch):
    """wired task + done + reachability=None → CommandError."""
    _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError) as exc_info:
        run_set_status("1", "done", reachability=None)

    msg = exc_info.value.message
    assert "reachability verdict" in msg
    assert "1" in msg


def test_live_done_without_reachability_raises(tmp_path, monkeypatch):
    """live tier + done + reachability=None → CommandError."""
    _write_project(tmp_path, [_task(1, tier="live")])
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError):
        run_set_status("1", "done")


# ---------------------------------------------------------------------------
# 3. wired ORPHAN verdict blocks
# ---------------------------------------------------------------------------


def test_wired_orphan_verdict_raises(tmp_path, monkeypatch):
    """wired task + ORPHAN verdict → CommandError."""
    _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError) as exc_info:
        run_set_status("1", "done", reachability={"verdict": "ORPHAN"})

    msg = exc_info.value.message
    assert "ORPHAN" in msg


def test_wired_error_verdict_raises(tmp_path, monkeypatch):
    """wired task + ERROR verdict → CommandError."""
    _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError) as exc_info:
        run_set_status("1", "done", reachability={"verdict": "ERROR"})

    msg = exc_info.value.message
    assert "ERROR" in msg


def test_wired_unknown_verdict_raises(tmp_path, monkeypatch):
    """wired task + unrecognized verdict → CommandError (fail closed)."""
    _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError):
        run_set_status("1", "done", reachability={"verdict": "UNKNOWN_FUTURE_VERDICT"})


# ---------------------------------------------------------------------------
# 4. wired WIRED verdict passes + evidence persisted
# ---------------------------------------------------------------------------


def test_wired_wired_verdict_passes_and_persists(tmp_path, monkeypatch):
    """wired task + WIRED verdict + evidence_ref → ok, both persisted."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    sweep = {"verdict": "WIRED", "tier": "wired", "modules": [], "start_commit": "abc123"}
    result = run_set_status("1", "done", evidence_ref="card.json", reachability=sweep)

    assert result["ok"] is True
    assert result["status"] == "done"

    tasks = _reload(tasks_file)
    task = tasks["1"]
    assert task["status"] == "done"
    assert task["doneEvidence"]["evidence_ref"] == "card.json"
    assert "at" in task["doneEvidence"]
    assert task["reachability"]["verdict"] == "WIRED"
    assert task["reachability"]["start_commit"] == "abc123"


# ---------------------------------------------------------------------------
# 5. EXEMPT verdict passes
# ---------------------------------------------------------------------------


def test_wired_exempt_verdict_passes(tmp_path, monkeypatch):
    """wired task + EXEMPT verdict → ok."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status(
        "1", "done", reachability={"verdict": "EXEMPT", "reason": "entrypoint"}
    )

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "done"
    assert tasks["1"]["reachability"]["verdict"] == "EXEMPT"


def test_live_exempt_verdict_passes(tmp_path, monkeypatch):
    """live tier + EXEMPT verdict → ok."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="live")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "done", reachability={"verdict": "EXEMPT"})

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "done"


# ---------------------------------------------------------------------------
# 6. Non-done transitions on wired task → no gate, no raise
# ---------------------------------------------------------------------------


def test_wired_in_progress_no_gate(tmp_path, monkeypatch):
    """set-status in-progress on wired task → ok without reachability."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "in-progress")

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "in-progress"
    # No reachability persisted
    assert "reachability" not in tasks["1"]


def test_wired_blocked_no_gate(tmp_path, monkeypatch):
    """set-status blocked on wired task → ok without reachability."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "blocked")

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["status"] == "blocked"


def test_wired_review_no_gate(tmp_path, monkeypatch):
    """set-status review on wired task → ok without reachability."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="wired")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "review")

    assert result["ok"] is True


# ---------------------------------------------------------------------------
# 7. Subtask path unbroken (subtask done never goes through tier gate)
# ---------------------------------------------------------------------------


def test_subtask_done_unaffected(tmp_path, monkeypatch):
    """Subtask done flip is not tier-gated (subtasks have no tier field)."""
    tasks_file = _write_project(
        tmp_path,
        [
            {
                "id": 1,
                "title": "Wired parent",
                "description": "",
                "details": "",
                "testStrategy": "",
                "status": "in-progress",
                "priority": "medium",
                "dependencies": [],
                "phaseConfig": {"tier": "wired"},
                "subtasks": [
                    {
                        "id": 1,
                        "title": "Subtask 1",
                        "description": "",
                        "details": "",
                        "status": "pending",
                        "dependencies": [],
                    }
                ],
            }
        ],
    )
    monkeypatch.chdir(tmp_path)

    # Subtask done should NOT raise even though parent is wired
    result = run_set_status("1.1", "done")

    assert result["ok"] is True
    assert result["kind"] == "subtask"
    raw = json.loads(tasks_file.read_text())
    subtask = raw["master"]["tasks"][0]["subtasks"][0]
    assert subtask["status"] == "done"


# ---------------------------------------------------------------------------
# 8. evidence_ref persisted on domain-model task (non-gated but evidence stored)
# ---------------------------------------------------------------------------


def test_domain_model_evidence_persisted(tmp_path, monkeypatch):
    """evidence_ref is stored even for non-gated tiers when provided."""
    tasks_file = _write_project(tmp_path, [_task(1, tier="domain-model")])
    monkeypatch.chdir(tmp_path)

    result = run_set_status("1", "done", evidence_ref="proof.json")

    assert result["ok"] is True
    tasks = _reload(tasks_file)
    assert tasks["1"]["doneEvidence"]["evidence_ref"] == "proof.json"
    assert "at" in tasks["1"]["doneEvidence"]
