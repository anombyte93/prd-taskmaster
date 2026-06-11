"""Tests for skel/ship-check.py — the deterministic SHIP_CHECK_OK emitter.

Rewritten against the LIVE gate contract (the plugin's old test asserted a
phantom schema: state=="complete", evidence_files on tasks, tasks under
.atlas-ai/taskmaster/, plan at .atlas-ai/ralph-loop-prompt.md — none of which
the live skel/ship-check.py uses).

Live contract (see skel/ship-check.py docstring):
  Gate 1 — .atlas-ai/state/pipeline.json has current_phase == "EXECUTE"
           (no `state` field). Missing → stderr "pipeline.json missing", fail.
  Gate 2 — .taskmaster/tasks/tasks.json: every master.tasks[].status == "done".
  Gate 3 — for each task id, a CDD card at .atlas-ai/cdd/task-<id>.json (or a
           combined card whose filename contains the id).
  Gate 4 — plan at .taskmaster/docs/plan.md OR docs/superpowers/plans/*.md.
  Gate 5 (HARD) — no non-zero "Exit status N" in any .atlas-ai/evidence/ file.
           Bypass via --override SHIP_CHECK_OVERRIDE_ADMIN.
  Success → stdout exactly "SHIP_CHECK_OK\n" (+ " [OVERRIDE]"), exit 0.
  Failure → nothing on stdout, FAIL detail on stderr, exit 1.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.shipcheck import run_ship_check

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIP_CHECK = REPO_ROOT / "skel" / "ship-check.py"


def _run(cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SHIP_CHECK), *extra],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _green(tmp_path: Path) -> None:
    """Build an all-gates-green project tree under tmp_path."""
    atlas = tmp_path / ".atlas-ai"
    (atlas / "state").mkdir(parents=True)
    (atlas / "state" / "pipeline.json").write_text(
        json.dumps({"current_phase": "EXECUTE"})
    )
    tm = tmp_path / ".taskmaster" / "tasks"
    tm.mkdir(parents=True)
    (tm / "tasks.json").write_text(
        json.dumps(
            {
                "master": {
                    "tasks": [
                        {"id": 1, "status": "done"},
                        {"id": 2, "status": "done"},
                    ]
                }
            }
        )
    )
    cdd = atlas / "cdd"
    cdd.mkdir(parents=True)
    (cdd / "task-1.json").write_text(json.dumps({"id": 1}))
    (cdd / "task-2.json").write_text(json.dumps({"id": 2}))
    docs = tmp_path / ".taskmaster" / "docs"
    docs.mkdir(parents=True)
    (docs / "plan.md").write_text("# Plan\n")


def test_ship_check_fails_on_empty_state(tmp_path: Path) -> None:
    r = _run(tmp_path)
    assert r.returncode != 0
    assert "SHIP_CHECK_OK" not in r.stdout
    assert "pipeline.json missing" in r.stderr


def test_ship_check_passes_on_all_gates_green(tmp_path: Path) -> None:
    _green(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, f"stderr={r.stderr!r} stdout={r.stdout!r}"
    assert "SHIP_CHECK_OK" in r.stdout


def test_ship_check_fails_when_task_not_done(tmp_path: Path) -> None:
    """Gate 2: a task with status != done blocks the gate."""
    _green(tmp_path)
    tasks_path = tmp_path / ".taskmaster" / "tasks" / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            {
                "master": {
                    "tasks": [
                        {"id": 1, "status": "done"},
                        {"id": 2, "status": "in-progress"},
                    ]
                }
            }
        )
    )
    r = _run(tmp_path)
    assert r.returncode != 0
    assert "SHIP_CHECK_OK" not in r.stdout
    assert "task 2 not done" in r.stderr


def test_ship_check_fails_when_done_task_has_no_cdd_card(tmp_path: Path) -> None:
    """Gate 3: a done task without a CDD card blocks the gate."""
    _green(tmp_path)
    # Remove task-2's CDD card.
    (tmp_path / ".atlas-ai" / "cdd" / "task-2.json").unlink()
    r = _run(tmp_path)
    assert r.returncode != 0
    assert "SHIP_CHECK_OK" not in r.stdout
    assert "task 2: no CDD card" in r.stderr


def test_ship_check_gate5_blocks_on_nonzero_exit_and_override_passes(tmp_path: Path) -> None:
    """Gate 5 (HARD): a non-zero 'Exit status N' in evidence blocks; the
    override token bypasses it."""
    _green(tmp_path)
    evidence = tmp_path / ".atlas-ai" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "run.log").write_text("pnpm test\nExit status 1\n")

    # Without override → blocked.
    r = _run(tmp_path)
    assert r.returncode != 0
    assert "SHIP_CHECK_OK" not in r.stdout
    assert "Exit status 1" in r.stderr

    # With the override token → passes, OVERRIDE suffix on stdout.
    r2 = _run(tmp_path, "--override", "SHIP_CHECK_OVERRIDE_ADMIN")
    assert r2.returncode == 0, f"stderr={r2.stderr!r} stdout={r2.stdout!r}"
    assert "SHIP_CHECK_OK" in r2.stdout
    assert "[OVERRIDE]" in r2.stdout


# ─── Python API agreement (prd_taskmaster.shipcheck.run_ship_check) ──────────


def test_run_ship_check_api_agrees_on_green(tmp_path: Path, monkeypatch) -> None:
    """The importable run_ship_check() must agree with the standalone script
    on the all-green case."""
    _green(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = run_ship_check()
    assert result["passed"] is True, f"failures={result['failures']!r}"
    assert result["exit_code"] == 0
    assert result["stdout"] == "SHIP_CHECK_OK"
    assert result["failures"] == []


def test_run_ship_check_api_agrees_on_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_ship_check()
    assert result["passed"] is False
    assert result["exit_code"] == 1
    assert result["stdout"] is None
    assert any("pipeline.json missing" in f for f in result["failures"])


def test_ship_check_passes_with_flat_tasks_format(tmp_path):
    """Gate 2 must accept the flat {"tasks": [...]} format the engine itself
    produces in Native Mode (dogfood finding, 2026-06-11)."""
    _green(tmp_path)  # tagged all-green baseline...
    # ...then overwrite tasks.json with the FLAT format
    (tmp_path / ".taskmaster" / "tasks" / "tasks.json").write_text(json.dumps(
        {"tasks": [{"id": 1, "status": "done"}, {"id": 2, "status": "done"}]}
    ))
    r = _run(tmp_path)
    assert r.returncode == 0, f"stderr={r.stderr!r}"
    assert "SHIP_CHECK_OK" in r.stdout
