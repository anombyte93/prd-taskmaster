"""E2E: Full reachability loop — orphan blocks ship, wiring ships, scaffold honest.

This test drives the COMPLETE lifecycle end-to-end:

  1. A real git project is constructed with Gates 1-4 satisfied and the oracle
     stubbed PASS via ATLAS_ORACLE_CMD (Gate 5 always passes).
  2. A 'wired'-tier task exists.  Its module is committed but imported only by
     its own test — no production importer.

Scenario A — Orphan blocks ship (the headline acceptance criterion):
  * reachability-sweep → CDD card verdict == ORPHAN
  * ship-check.py subprocess → exits 1, no SHIP_CHECK_OK, failure names the
    ORPHAN and the task (non-vacuous: the task is wired-tier, so Gate 6 fires)

Scenario B — Oracle / test orthogonality:
  * The task's own test is GREEN (oracle stubbed PASS) — proving that a task
    can pass its unit test yet still be ORPHAN: the two axes are independent.
  * Gate 5 (oracle) passes; Gate 6 (reachability) is the sole blocker.

Scenario C — Wire it → ships:
  * A production importer is committed, sweep re-run → verdict WIRED
  * set-status done succeeds (auto-reads WIRED from card)
  * ship-check subprocess → SHIP_CHECK_OK, exit 0

Scenario D — Or scaffold → honest block:
  * Starting from the ORPHAN state (task still in-progress), set-status scaffold
  * ship-check subprocess → exits 1 (Gate 2: task not done), no SHIP_CHECK_OK
  * No Gate 6 involvement — honest "not done" message

ALL paths use real subprocess for ship-check.  The reachability-sweep is called
via its Python API (run_reachability_sweep) — no mock of sweep internals.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.lib import CommandError
from prd_taskmaster.reachability_cmd import run_reachability_sweep
from prd_taskmaster.task_state import run_set_status

# Path to the real ship-check script (stdlib-only, ships into user projects).
REPO_ROOT = Path(__file__).resolve().parents[2]
SHIP = REPO_ROOT / "skel" / "ship-check.py"


# ─── Git repo helpers ─────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


# ─── Project scaffolding ──────────────────────────────────────────────────────

TASK_ID = "42"
TASK_TITLE = "Implement widget module"


def _make_task(tier: str = "wired", status: str = "in-progress") -> dict:
    """Build a minimal task dict for tasks.json."""
    return {
        "id": int(TASK_ID),
        "title": TASK_TITLE,
        "description": "Implement the widget module",
        "details": "details here",
        "testStrategy": "unit test",
        "status": status,
        "priority": "medium",
        "dependencies": [],
        "subtasks": [],
        "phaseConfig": {"tier": tier},
    }


def _write_tasks(repo: Path, task: dict, tag: str = "master") -> Path:
    """Write .taskmaster/tasks/tasks.json and state.json."""
    payload = {
        tag: {
            "tasks": [task],
            "metadata": {"created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z"},
        }
    }
    tasks_dir = repo / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (repo / ".taskmaster" / "state.json").write_text(
        json.dumps({"currentTag": tag, "migrationNoticeShown": True})
    )
    path = tasks_dir / "tasks.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def _write_cdd_card(repo: Path, task_id: str = TASK_ID) -> Path:
    """Write the CDD card (with grading block so Gate 5 can run)."""
    cdd_dir = repo / ".atlas-ai" / "cdd"
    cdd_dir.mkdir(parents=True, exist_ok=True)
    card = {
        "task_id": task_id,
        "title": TASK_TITLE,
        "testing_plan": [{"check": "widget test passes", "evidence": "pytest"}],
        "grading": {"command": ["sh", "grade.sh"]},
    }
    path = cdd_dir / f"task-{task_id}.json"
    path.write_text(json.dumps(card, indent=2))
    return path


def _write_gates_1_4(repo: Path) -> None:
    """Write the Gates 1-4 supporting files."""
    # Gate 1: pipeline.json current_phase == EXECUTE
    state_dir = repo / ".atlas-ai" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "pipeline.json").write_text(
        json.dumps({"current_phase": "EXECUTE"})
    )
    # Gate 4: plan file
    docs = repo / ".taskmaster" / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "plan.md").write_text("# Plan\nImplement the widget module.\n")


def _fake_oracle_script(tmp_path: Path) -> str:
    """Return ATLAS_ORACLE_CMD string for a fake oracle that always emits PASS."""
    script = tmp_path / "fake_atlas.sh"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = "grade" ]; then\n'
        '    printf \'{"verdict":"PASS"}\'\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"sh {script}"


def _run_ship_check(repo: Path, oracle_cmd: str) -> subprocess.CompletedProcess:
    """Run ship-check.py as a subprocess against repo with a fake oracle."""
    env = dict(os.environ)
    env["ATLAS_ORACLE_CMD"] = oracle_cmd
    return subprocess.run(
        ["python3", str(SHIP)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# ─── Fixture: base orphan project ─────────────────────────────────────────────

@pytest.fixture()
def orphan_project(tmp_path):
    """Build a real git project where pkg/widget.py is an orphan.

    Layout:
      Commit 1 (start): pyproject.toml + pkg/__init__.py + pkg/app.py (production
                         entry point — empty placeholder, imports nothing yet)
      Commit 2 (head):  pkg/widget.py added (new module); only imported by its
                         own test, NOT by app.py → ORPHAN

    Key design rationale: app.py exists BEFORE start_sha so the sweep only
    counts widget.py as a new module (not app.py).  This means:
    - ORPHAN state: app.py does NOT import widget.py (widget is orphan)
    - WIRED state: editing app.py to import widget.py wires it (app.py is
      already counted as "existing production code", not a new module)

    The project has:
      - Gates 1-4 satisfied (pipeline.json, tasks.json, CDD card, plan.md)
      - Task 42, tier=wired, status=in-progress
      - Oracle stubbed PASS via ATLAS_ORACLE_CMD
    """
    repo = _init_repo(tmp_path)

    # Commit 1: base project with a production entrypoint (app.py) that does NOT
    # import widget yet.  This commit is start_sha.
    (repo / "pyproject.toml").write_text("[project]\nname = 'myapp'\n")
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    # app.py exists BEFORE start_sha so it is not counted as a new module.
    (pkg / "app.py").write_text("# Production entrypoint — widget import not wired yet\n")
    # Gate files
    _write_gates_1_4(repo)
    # tasks.json (task in-progress)
    task = _make_task(tier="wired", status="in-progress")
    tasks_file = _write_tasks(repo, task)
    # CDD card
    card_path = _write_cdd_card(repo)
    start_sha = _commit_all(repo, "initial: base project with app.py entrypoint")

    # Commit 2: widget.py added — only imported by its own test (orphan).
    # app.py is NOT modified, so widget.py has no production importer.
    (pkg / "widget.py").write_text(
        "class Widget:\n"
        "    def render(self):\n"
        "        return '<widget />'\n"
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_widget.py").write_text(
        "from pkg.widget import Widget\n\n"
        "def test_render():\n"
        "    assert Widget().render() == '<widget />'\n"
    )
    head_sha = _commit_all(repo, "feat: add widget module (test only, not wired to production)")

    oracle_cmd = _fake_oracle_script(tmp_path)

    return {
        "repo": repo,
        "start_sha": start_sha,
        "head_sha": head_sha,
        "tasks_file": tasks_file,
        "card_path": card_path,
        "oracle_cmd": oracle_cmd,
        "tmp_path": tmp_path,
    }


# ─── Scenario A: Orphan blocks ship ──────────────────────────────────────────

class TestOrphanBlocksShip:
    """Scenario A: orphan module → sweep writes ORPHAN → ship-check blocks."""

    def test_sweep_writes_orphan_verdict_to_cdd_card(self, orphan_project):
        """reachability-sweep on an orphan module writes ORPHAN to the CDD card."""
        p = orphan_project
        result = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(p["repo"]))

        assert result["verdict"] == "ORPHAN", (
            f"Expected ORPHAN but got {result['verdict']!r}. "
            f"Full result: {result}"
        )

        # Verify the card was updated.
        card = json.loads(p["card_path"].read_text())
        assert "reachability" in card
        assert card["reachability"]["verdict"] == "ORPHAN"
        # start_commit is recorded
        assert card["reachability"]["start_commit"] == p["start_sha"]

    def test_ship_check_exits_nonzero_for_orphan(self, orphan_project):
        """ship-check subprocess exits 1 when the wired task is ORPHAN."""
        p = orphan_project
        # First run sweep to write the ORPHAN verdict.
        run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(p["repo"]))

        # Mark task as done in tasks.json so Gate 2 passes and Gate 6 runs.
        # (We mark done without going through run_set_status — we want the card
        # to have ORPHAN so Gate 6 blocks, not set-status.)
        tasks = json.loads(p["tasks_file"].read_text())
        for t in tasks["master"]["tasks"]:
            if str(t["id"]) == TASK_ID:
                t["status"] = "done"
        p["tasks_file"].write_text(json.dumps(tasks, indent=2))

        r = _run_ship_check(p["repo"], p["oracle_cmd"])

        # Must NOT print SHIP_CHECK_OK.
        assert "SHIP_CHECK_OK" not in r.stdout, (
            f"Expected no SHIP_CHECK_OK but stdout was: {r.stdout!r}"
        )
        # Must exit non-zero.
        assert r.returncode != 0, (
            f"Expected non-zero exit but got {r.returncode}. stderr={r.stderr!r}"
        )

    def test_ship_check_stderr_names_orphan_and_task(self, orphan_project):
        """ship-check failure message names ORPHAN and the task id (non-vacuous)."""
        p = orphan_project
        run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(p["repo"]))
        # Mark done so Gate 6 fires.
        tasks = json.loads(p["tasks_file"].read_text())
        for t in tasks["master"]["tasks"]:
            if str(t["id"]) == TASK_ID:
                t["status"] = "done"
        p["tasks_file"].write_text(json.dumps(tasks, indent=2))

        r = _run_ship_check(p["repo"], p["oracle_cmd"])

        assert r.returncode == 1
        # Gate 6 failure message must mention ORPHAN.
        assert "ORPHAN" in r.stderr, f"Expected 'ORPHAN' in stderr, got: {r.stderr!r}"
        # Failure message must identify the task.
        assert TASK_ID in r.stderr, f"Expected task id {TASK_ID!r} in stderr, got: {r.stderr!r}"


# ─── Scenario B: Oracle / test orthogonality ──────────────────────────────────

class TestOracleOrthogonality:
    """Scenario B: the task's own test passes (oracle PASS) while reachability is ORPHAN.

    This is the user's exact bug: 'done' was optimised on 'tasks marked done',
    which broke when a task passed its unit test but the module was unreachable.

    Assertion: Gate 5 (oracle) == PASS AND Gate 6 (reachability) == ORPHAN → blocked.
    The two axes are independent.
    """

    def test_oracle_passes_while_reachability_is_orphan(self, orphan_project, tmp_path):
        """Gate 5 (oracle) passes; Gate 6 (reachability) blocks — two independent axes."""
        p = orphan_project
        # Write ORPHAN verdict into card.
        sweep_result = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(p["repo"]))
        assert sweep_result["verdict"] == "ORPHAN"

        # Confirm card has ORPHAN.
        card = json.loads(p["card_path"].read_text())
        assert card["reachability"]["verdict"] == "ORPHAN"

        # The oracle is stubbed PASS — Gate 5 would pass for this task.
        # Verify the fake oracle script emits PASS when called with 'grade'.
        oracle_result = subprocess.run(
            ["sh", str(p["tmp_path"] / "fake_atlas.sh"), "oracle", "grade"],
            capture_output=True,
            text=True,
        )
        oracle_out = json.loads(oracle_result.stdout)
        assert oracle_out["verdict"] == "PASS", (
            f"Oracle stub should emit PASS but got: {oracle_result.stdout!r}"
        )

        # Now run the full ship-check: Gate 5 passes, Gate 6 blocks.
        tasks = json.loads(p["tasks_file"].read_text())
        for t in tasks["master"]["tasks"]:
            if str(t["id"]) == TASK_ID:
                t["status"] = "done"
        p["tasks_file"].write_text(json.dumps(tasks, indent=2))

        r = _run_ship_check(p["repo"], p["oracle_cmd"])

        # Ship-check is blocked even though oracle says PASS.
        assert r.returncode == 1, (
            "Expected ship-check to block but it passed. "
            "Oracle says PASS, yet reachability is ORPHAN — Gate 6 should block."
        )
        assert "SHIP_CHECK_OK" not in r.stdout
        # Gate 6 is responsible — not Gate 5.
        assert "ORPHAN" in r.stderr, f"Expected Gate 6 to mention ORPHAN. stderr={r.stderr!r}"

    def test_set_status_done_raises_for_orphan(self, orphan_project):
        """set-status done raises for the orphan task; oracle has no bearing."""
        p = orphan_project
        run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(p["repo"]))

        old_cwd = os.getcwd()
        try:
            os.chdir(str(p["repo"]))
            with pytest.raises(CommandError) as exc_info:
                run_set_status(TASK_ID, "done")
        finally:
            os.chdir(old_cwd)

        msg = exc_info.value.message
        assert "ORPHAN" in msg or "reachability" in msg.lower(), (
            f"Expected ORPHAN or 'reachability' in error message, got: {msg!r}"
        )


# ─── Scenario C: Wire it → ships ──────────────────────────────────────────────

class TestWiredShips:
    """Scenario C: wire the module (edit existing app.py) → re-sweep → WIRED → ships.

    Design: app.py exists BEFORE start_sha (not counted as a new module).
    Wiring = modifying app.py to import Widget (an edit to an existing file, not
    a new module).  The sweep then finds only widget.py as a new module, and
    widget.py now has a production importer (app.py) → WIRED.
    """

    def test_wire_module_then_sweep_gives_wired(self, orphan_project):
        """After editing app.py to import Widget, sweep returns WIRED."""
        p = orphan_project
        repo = p["repo"]

        # Confirm we start with ORPHAN.
        result = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))
        assert result["verdict"] == "ORPHAN"

        # Wire: edit the existing production entrypoint to import Widget.
        # (app.py was committed before start_sha, so it's not a new module.)
        (repo / "pkg" / "app.py").write_text(
            "from pkg.widget import Widget\n\n"
            "def main():\n"
            "    w = Widget()\n"
            "    return w.render()\n"
        )
        _commit_all(repo, "wire: import Widget from pkg.widget in app.py")

        # Re-run sweep against the same start sha.
        result2 = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))
        assert result2["verdict"] == "WIRED", (
            f"Expected WIRED after wiring but got {result2['verdict']!r}. Full: {result2}"
        )

        # CDD card is updated.
        card = json.loads(p["card_path"].read_text())
        assert card["reachability"]["verdict"] == "WIRED"

    def test_wire_then_set_status_done_succeeds(self, orphan_project):
        """After wiring + sweep, set-status done auto-reads WIRED from card → ok."""
        p = orphan_project
        repo = p["repo"]

        # Wire: edit existing app.py to import Widget.
        (repo / "pkg" / "app.py").write_text(
            "from pkg.widget import Widget\n\n"
            "def main():\n"
            "    return Widget().render()\n"
        )
        _commit_all(repo, "wire: import Widget in app.py")

        # Sweep → WIRED (only widget.py is a new module; app.py existed before start_sha).
        sweep_result = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))
        assert sweep_result["verdict"] == "WIRED", f"Expected WIRED but got: {sweep_result}"

        # set-status done — auto-reads WIRED from card.
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            result = run_set_status(TASK_ID, "done")
        finally:
            os.chdir(old_cwd)

        assert result["ok"] is True
        assert result["status"] == "done"

        # tasks.json is updated.
        tasks = json.loads(p["tasks_file"].read_text())
        updated = {str(t["id"]): t for t in tasks["master"]["tasks"]}
        assert updated[TASK_ID]["status"] == "done"
        assert updated[TASK_ID]["reachability"]["verdict"] == "WIRED"

    def test_wire_then_ship_check_passes(self, orphan_project):
        """After wiring, set-status done, ship-check prints SHIP_CHECK_OK exit 0."""
        p = orphan_project
        repo = p["repo"]

        # Wire: edit existing app.py to import Widget.
        (repo / "pkg" / "app.py").write_text(
            "from pkg.widget import Widget\n\n"
            "def main():\n"
            "    return Widget().render()\n"
        )
        _commit_all(repo, "wire: import Widget in app.py")

        # Sweep → WIRED.
        sweep_result = run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))
        assert sweep_result["verdict"] == "WIRED", f"Expected WIRED but got: {sweep_result}"

        # set-status done (auto-reads WIRED from card).
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            run_set_status(TASK_ID, "done")
        finally:
            os.chdir(old_cwd)

        # ship-check subprocess should now pass.
        r = _run_ship_check(repo, p["oracle_cmd"])

        assert r.returncode == 0, (
            f"Expected ship-check to pass (exit 0) but got {r.returncode}. "
            f"stderr={r.stderr!r}"
        )
        assert "SHIP_CHECK_OK" in r.stdout, (
            f"Expected SHIP_CHECK_OK in stdout but got: {r.stdout!r}"
        )


# ─── Scenario D: Scaffold → honest block ─────────────────────────────────────

class TestScaffoldHonestBlock:
    """Scenario D: instead of wiring, re-status to scaffold → Gate 2 blocks honestly."""

    def test_scaffold_status_blocks_ship_gate2(self, orphan_project):
        """set-status scaffold → task not done → ship-check blocks at Gate 2."""
        p = orphan_project
        repo = p["repo"]

        # Run sweep (ORPHAN) first so reachability is recorded.
        run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))

        # Set status to scaffold (no reachability gate on non-done statuses).
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            result = run_set_status(TASK_ID, "scaffold")
        finally:
            os.chdir(old_cwd)

        assert result["ok"] is True
        assert result["status"] == "scaffold"

        # Verify tasks.json has the new status.
        tasks = json.loads(p["tasks_file"].read_text())
        updated = {str(t["id"]): t for t in tasks["master"]["tasks"]}
        assert updated[TASK_ID]["status"] == "scaffold"

        # ship-check: Gate 2 blocks (task is not done).
        r = _run_ship_check(repo, p["oracle_cmd"])

        assert r.returncode != 0, (
            f"Expected ship-check to block (scaffold is not done) but it passed. "
            f"stdout={r.stdout!r}"
        )
        assert "SHIP_CHECK_OK" not in r.stdout

    def test_scaffold_block_is_gate2_not_gate6(self, orphan_project):
        """Scaffold block comes from Gate 2 (not done), not Gate 6 (reachability)."""
        p = orphan_project
        repo = p["repo"]

        run_reachability_sweep(TASK_ID, p["start_sha"], cwd=str(repo))

        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            run_set_status(TASK_ID, "scaffold")
        finally:
            os.chdir(old_cwd)

        r = _run_ship_check(repo, p["oracle_cmd"])

        assert r.returncode == 1
        # Gate 2 message: task is "not done" / status check.
        stderr = r.stderr.lower()
        assert "not done" in stderr or "scaffold" in stderr or "status" in stderr, (
            f"Expected Gate 2 'not done' message in stderr, got: {r.stderr!r}"
        )
        # Gate 6 (ORPHAN) should NOT fire because the task is not 'done'.
        # The scaffold task is caught by Gate 2 first.
        # (Note: Gate 6 skips non-done tasks per the contract.)

    def test_scaffold_set_status_does_not_require_reachability(self, orphan_project):
        """set-status scaffold works without a reachability verdict (non-done bypass)."""
        p = orphan_project
        repo = p["repo"]

        # No sweep run — no reachability in card. Scaffold still works.
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            result = run_set_status(TASK_ID, "scaffold")
        finally:
            os.chdir(old_cwd)

        assert result["ok"] is True
        assert result["status"] == "scaffold"
