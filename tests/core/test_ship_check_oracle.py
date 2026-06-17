"""Oracle-gate contract for the standalone skel/ship-check.py (Gate 5 cutover).

Gate 5 was a FAKABLE deterministic grep over .atlas-ai/evidence/ that SILENTLY
PASSED when no evidence existed, and was bypassable with a self-grantable
--override SHIP_CHECK_OVERRIDE_ADMIN token. This suite proves the new contract:

  * For every DONE task, the gate RE-EXECUTES the CDD card's grading via the
    `atlas oracle grade` CLI (shelled out — the script stays stdlib-only).
  * FAIL-CLOSED: missing card, missing grading block, CLI crash, unparseable
    output, or a non-PASS verdict all BLOCK the ship. ONLY verdict=="PASS"
    ships a task.
  * The override token is GONE — there is no self-grantable bypass path.

The script is loaded by file path via importlib because it ships into user
projects as a standalone `.atlas-ai/ship-check.py` (no prd_taskmaster import).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SHIP = Path(__file__).resolve().parents[2] / "skel" / "ship-check.py"


def load():
    spec = importlib.util.spec_from_file_location("ship_check_mod", SHIP)
    mod = importlib.util.module_from_spec(spec)
    # Don't write skel/__pycache__/*.pyc — the packaging tarball must stay clean.
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = prev
    return mod


def setup_project(tmp_path: Path, task_ids, with_cdd: bool = True) -> None:
    """Write a tree where Gates 1-4 PASS so the ORACLE gate decides the verdict.

    pipeline.json current_phase=EXECUTE (Gate 1), every task done (Gate 2),
    a CDD card per task when with_cdd (Gate 3), and a plan.md (Gate 4).
    """
    atlas = tmp_path / ".atlas-ai"
    (atlas / "state").mkdir(parents=True)
    (atlas / "state" / "pipeline.json").write_text(
        json.dumps({"current_phase": "EXECUTE"})
    )
    tm = tmp_path / ".taskmaster" / "tasks"
    tm.mkdir(parents=True)
    (tm / "tasks.json").write_text(
        json.dumps({"master": {"tasks": [{"id": i, "status": "done"} for i in task_ids]}})
    )
    docs = tmp_path / ".taskmaster" / "docs"
    docs.mkdir(parents=True)
    (docs / "plan.md").write_text("# Plan\n")
    if with_cdd:
        cdd = atlas / "cdd"
        cdd.mkdir(parents=True)
        for i in task_ids:
            (cdd / f"task-{i}.json").write_text(
                json.dumps({"id": f"C-00{i}", "grading": {"command": ["sh", "grade.sh"]}})
            )


def _fake_run_factory(grade_stdout: str, grade_returncode: int = 0):
    """Build a fake subprocess.run dispatching on the command.

    rev-parse → a fixed HEAD sha; oracle grade → the canned (stdout, returncode).
    """

    def fake_run(cmd, *args, **kwargs):
        joined = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "rev-parse" in joined:
            return types.SimpleNamespace(stdout="deadbeef\n", stderr="", returncode=0)
        if "oracle" in joined and "grade" in joined:
            return types.SimpleNamespace(stdout=grade_stdout, stderr="", returncode=grade_returncode)
        raise AssertionError(f"unexpected subprocess command: {joined}")

    return fake_run


# ─── 1. Oracle PASS → ships ───────────────────────────────────────────────────


def test_oracle_pass_ships(tmp_path, monkeypatch, capsys):
    mod = load()
    setup_project(tmp_path, [1, 2], with_cdd=True)
    monkeypatch.setattr(mod.subprocess, "run", _fake_run_factory('{"verdict":"PASS"}'))

    ok, failures = mod.run_all_gates(tmp_path)
    assert ok is True, f"failures={failures!r}"
    assert failures == []

    # main() end-to-end prints exactly SHIP_CHECK_OK and exits 0.
    monkeypatch.setattr(mod.sys, "argv", ["ship-check.py", "--cwd", str(tmp_path)])
    rc = mod.main()
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.strip() == "SHIP_CHECK_OK"


# ─── 2. Oracle FAIL → blocks ──────────────────────────────────────────────────


def test_oracle_fail_blocks(tmp_path, monkeypatch, capsys):
    mod = load()
    setup_project(tmp_path, [1, 2], with_cdd=True)
    monkeypatch.setattr(mod.subprocess, "run", _fake_run_factory('{"verdict":"FAIL"}'))

    ok, failures = mod.run_all_gates(tmp_path)
    assert ok is False
    assert any("oracle" in f.lower() and ("1" in f or "2" in f) for f in failures), failures

    monkeypatch.setattr(mod.sys, "argv", ["ship-check.py", "--cwd", str(tmp_path)])
    rc = mod.main()
    out = capsys.readouterr()
    assert rc == 1
    assert "SHIP_CHECK_OK" not in out.out


# ─── 3. The silent-pass loophole is closed (fail-closed on ambiguity) ──────────


def test_silent_pass_is_gone(tmp_path, monkeypatch):
    """OLD Gate 5 silently PASSED when no evidence existed. The new gate must
    FAIL-CLOSED when the oracle output is not parseable JSON."""
    mod = load()
    setup_project(tmp_path, [1], with_cdd=True)
    monkeypatch.setattr(
        mod.subprocess, "run", _fake_run_factory("podman: not found", grade_returncode=127)
    )

    ok, failures = mod.run_all_gates(tmp_path)
    assert ok is False
    assert failures, "non-JSON oracle output must produce a failure"


# ─── 4. Missing CDD card fails closed ─────────────────────────────────────────


def test_missing_cdd_card_fails_closed(tmp_path, monkeypatch):
    mod = load()
    # Build Gates 1,2,4 green but NO cdd dir/card (with_cdd=False).
    setup_project(tmp_path, [1], with_cdd=False)
    # The oracle would pass IF it were called — it must never be reached.
    monkeypatch.setattr(mod.subprocess, "run", _fake_run_factory('{"verdict":"PASS"}'))

    ok, failures = mod.gate_oracle(tmp_path, [{"id": 1, "status": "done"}], "deadbeef")
    assert ok is False
    assert any("no CDD card" in f for f in failures), failures


# ─── 5. The override token is removed ─────────────────────────────────────────


def test_override_token_removed(tmp_path, monkeypatch, capsys):
    mod = load()
    assert not hasattr(mod, "OVERRIDE_TOKEN")

    setup_project(tmp_path, [1], with_cdd=True)
    # Even an attempt to pass the old token must NOT produce SHIP_CHECK_OK.
    monkeypatch.setattr(mod.subprocess, "run", _fake_run_factory('{"verdict":"FAIL"}'))
    monkeypatch.setattr(
        mod.sys,
        "argv",
        ["ship-check.py", "--override", "SHIP_CHECK_OVERRIDE_ADMIN", "--cwd", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    # argparse rejects the unknown --override argument with exit code 2.
    assert exc.value.code == 2
    out = capsys.readouterr()
    assert "SHIP_CHECK_OK" not in out.out

    # The token string no longer appears anywhere in the file.
    assert "OVERRIDE" not in SHIP.read_text()


# ─── 6. Gates 1-4 still enforced (regression) ─────────────────────────────────


def test_gates_1_to_4_still_enforced(tmp_path, monkeypatch):
    mod = load()
    setup_project(tmp_path, [1], with_cdd=True)
    # Break Gate 1: pipeline not in EXECUTE.
    (tmp_path / ".atlas-ai" / "state" / "pipeline.json").write_text(
        json.dumps({"current_phase": "GENERATE"})
    )
    # Oracle would pass — Gate 1 must still block.
    monkeypatch.setattr(mod.subprocess, "run", _fake_run_factory('{"verdict":"PASS"}'))

    ok, failures = mod.run_all_gates(tmp_path)
    assert ok is False
    assert any("current_phase" in f for f in failures), failures
