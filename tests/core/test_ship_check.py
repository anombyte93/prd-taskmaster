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
  Gate 5 (HARD, ORACLE) — every DONE task is RE-GRADED by the atlas oracle CLI
           (shelled out; configurable via ATLAS_ORACLE_CMD). FAIL-CLOSED: a
           missing card, a card with no grading block, a CLI crash, unparseable
           output, or any non-PASS verdict BLOCKS the ship. The old fakable
           "no non-zero Exit status N in evidence" grep and the self-grantable
           --override SHIP_CHECK_OVERRIDE_ADMIN token are BOTH GONE (see the
           dedicated coverage in test_ship_check_oracle.py).
  Success → stdout exactly "SHIP_CHECK_OK\n", exit 0.
  Failure → nothing on stdout, FAIL detail on stderr, exit 1.

NOTE: these tests drive the script as a real subprocess, so the oracle gate is
satisfied by a real fake-oracle command (a tiny executable shell script) wired
through ATLAS_ORACLE_CMD. Pure-monkeypatch oracle coverage lives in
test_ship_check_oracle.py.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.shipcheck import run_ship_check

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIP_CHECK = REPO_ROOT / "skel" / "ship-check.py"


def _fake_oracle(tmp_path: Path, verdict: str = "PASS") -> str:
    """Write an executable fake `atlas` that emits {"verdict": <verdict>} for an
    `oracle grade` invocation. Return an ATLAS_ORACLE_CMD value pointing at it."""
    script = tmp_path / "fake_atlas.sh"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = "grade" ]; then\n'
        f'    printf \'{{"verdict":"{verdict}"}}\'\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"sh {script}"


def _run(cwd: Path, *extra: str, oracle_cmd: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if oracle_cmd is not None:
        env["ATLAS_ORACLE_CMD"] = oracle_cmd
    return subprocess.run(
        ["python3", str(SHIP_CHECK), *extra],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _green(tmp_path: Path) -> None:
    """Build an all-gates-green project tree under tmp_path. CDD cards carry a
    `grading` block so the oracle gate can re-grade them."""
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
    grading = {"grading": {"command": ["sh", "grade.sh"]}}
    (cdd / "task-1.json").write_text(json.dumps({"id": 1, **grading}))
    (cdd / "task-2.json").write_text(json.dumps({"id": 2, **grading}))
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
    r = _run(tmp_path, oracle_cmd=_fake_oracle(tmp_path, "PASS"))
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


def test_ship_check_gate5_oracle_fail_blocks_and_override_is_gone(tmp_path: Path) -> None:
    """Gate 5 (HARD, ORACLE): an oracle FAIL verdict blocks the ship, and the
    old self-grantable --override token no longer exists (argparse rejects it)."""
    _green(tmp_path)

    # An oracle FAIL verdict → blocked, nothing on stdout.
    r = _run(tmp_path, oracle_cmd=_fake_oracle(tmp_path, "FAIL"))
    assert r.returncode != 0
    assert "SHIP_CHECK_OK" not in r.stdout
    assert "oracle verdict FAIL" in r.stderr

    # The override token is GONE: argparse rejects the unknown flag (exit 2)
    # and never emits SHIP_CHECK_OK — there is no bypass path.
    r2 = _run(
        tmp_path,
        "--override",
        "SHIP_CHECK_OVERRIDE_ADMIN",
        oracle_cmd=_fake_oracle(tmp_path, "PASS"),
    )
    assert r2.returncode == 2
    assert "SHIP_CHECK_OK" not in r2.stdout


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
    r = _run(tmp_path, oracle_cmd=_fake_oracle(tmp_path, "PASS"))
    assert r.returncode == 0, f"stderr={r.stderr!r}"
    assert "SHIP_CHECK_OK" in r.stdout
