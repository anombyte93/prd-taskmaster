"""TDD: reachability-sweep CLI (Part A) + cmd_set_status auto-read (Part B).

All tests that exercise WIRED vs ORPHAN build real git repos so that the
grep / git logic runs against actual source content.  No mocking of the
load-bearing sweep calls.

Coverage:
  Part A — run_reachability_sweep
    A1. WIRED task → writes reachability.verdict==WIRED into CDD card, returns dict.
    A2. ORPHAN wired task → writes ORPHAN into card; caller should exit 1 (verdict check).
    A3. CDD card additive: other card keys preserved after sweep writes reachability.
    A4. No CDD card → CommandError (clear message).
    A5. No tasks.json → CommandError.
    A6. EXEMPT task (tier-exempt) → writes EXEMPT into card.

  Part B — cmd_set_status auto-read
    B1. wired task whose CDD card has verdict==WIRED → set-status done succeeds (no flag).
    B2. wired task whose CDD card has verdict==ORPHAN → raises CommandError.
    B3. --reachability WIRED explicit → passes.
    B4. --reachability JSON dict explicit → passes.
    B5. Backward-compat: untiered set-status done via CLI still works with no flags.
    B6. wired task, no CDD card, no --reachability → CommandError (RA5 gate, no card to auto-read).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.lib import CommandError
from prd_taskmaster.reachability_cmd import run_reachability_sweep
from prd_taskmaster.task_state import (
    _parse_reachability_arg,
    _read_cdd_reachability,
    run_set_status,
)


# ─── Git repo helpers (mirrors test_reachability.py) ─────────────────────────


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


def _make_wired_py_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Build a Python repo where pkg/foo.py is WIRED (imported by pkg/app.py).

    Commit 1 (start): pyproject.toml + pkg/__init__.py + pkg/app.py (importer)
    Commit 2 (head):  pkg/foo.py added (new module)

    Returns (repo, start_sha, head_sha, task_id).
    """
    repo = _init_repo(tmp_path)
    (repo / "pyproject.toml").write_text("[project]\nname = 'mypkg'\n")
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "app.py").write_text("from pkg import foo\n")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    start = _commit_all(repo, "initial")

    (pkg / "foo.py").write_text("def hello():\n    return 'hello'\n")
    (tests_dir / "test_foo.py").write_text(
        "from pkg.foo import hello\ndef test_hello():\n    assert hello() == 'hello'\n"
    )
    head = _commit_all(repo, "add foo")
    return repo, start, head, "1"


def _make_orphan_py_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Build a Python repo where pkg/foo.py is ORPHAN (imported by nothing non-test).

    Commit 1 (start): pyproject.toml + pkg/__init__.py
    Commit 2 (head):  pkg/foo.py added (new module, not imported by any non-test file)
    """
    repo = _init_repo(tmp_path)
    (repo / "pyproject.toml").write_text("[project]\nname = 'mypkg'\n")
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    start = _commit_all(repo, "initial")

    (pkg / "foo.py").write_text("def hello():\n    return 'hello'\n")
    (tests_dir / "test_foo.py").write_text(
        "from pkg.foo import hello\ndef test_hello():\n    assert hello() == 'hello'\n"
    )
    head = _commit_all(repo, "add orphan foo")
    return repo, start, head, "1"


def _write_tasks(repo: Path, tasks: list, *, tag: str = "master") -> Path:
    """Write a tagged tasks.json under .taskmaster/tasks/."""
    payload = {
        tag: {
            "tasks": tasks,
            "metadata": {"created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z"},
        }
    }
    tasks_dir = repo / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (repo / ".taskmaster" / "state.json").write_text(
        json.dumps({"currentTag": tag, "migrationNoticeShown": True})
    )
    f = tasks_dir / "tasks.json"
    f.write_text(json.dumps(payload, indent=2))
    return f


def _make_task(task_id: int | str, *, tier: str | None = None) -> dict:
    t: dict = {
        "id": task_id,
        "title": f"Task {task_id}",
        "description": "desc",
        "details": "details",
        "testStrategy": "test",
        "status": "in-progress",
        "priority": "medium",
        "dependencies": [],
        "subtasks": [],
    }
    if tier is not None:
        t["phaseConfig"] = {"tier": tier}
    return t


def _write_cdd_card(repo: Path, task_id: str, extra: dict | None = None) -> Path:
    """Write a minimal CDD card for *task_id*, optionally merging *extra* fields."""
    cdd_dir = repo / ".atlas-ai" / "cdd"
    cdd_dir.mkdir(parents=True, exist_ok=True)
    card: dict = {
        "task_id": task_id,
        "title": f"CDD card for task {task_id}",
        "testing_plan": [],
    }
    if extra:
        card.update(extra)
    path = cdd_dir / f"task-{task_id}.json"
    path.write_text(json.dumps(card, indent=2))
    return path


# ─── Part A: run_reachability_sweep ──────────────────────────────────────────


class TestRunReachabilitySweepWired:
    def test_wired_module_writes_wired_verdict_to_card(self, tmp_path):
        """WIRED task: sweep returns WIRED and writes it into the CDD card."""
        repo, start, head, tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        card_path = _write_cdd_card(repo, tid)

        result = run_reachability_sweep(tid, start, cwd=str(repo))

        assert result["verdict"] == "WIRED", f"expected WIRED, got: {result}"

        # Card must have the reachability block.
        card = json.loads(card_path.read_text())
        assert "reachability" in card
        assert card["reachability"]["verdict"] == "WIRED"
        assert card["reachability"]["start_commit"] == start
        # Original card keys preserved.
        assert card["task_id"] == tid
        assert card["title"] == f"CDD card for task {tid}"

    def test_wired_sweep_returns_full_dict(self, tmp_path):
        """run_reachability_sweep return value has all expected keys."""
        repo, start, _head, tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        _write_cdd_card(repo, tid)

        result = run_reachability_sweep(tid, start, cwd=str(repo))

        assert "verdict" in result
        assert "tier" in result
        assert "modules" in result
        assert "checked_at" in result
        assert "start_commit" in result


class TestRunReachabilitySweepOrphan:
    def test_orphan_module_writes_orphan_verdict_to_card(self, tmp_path):
        """ORPHAN task: sweep writes ORPHAN to CDD card."""
        repo, start, _head, tid = _make_orphan_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        card_path = _write_cdd_card(repo, tid)

        result = run_reachability_sweep(tid, start, cwd=str(repo))

        assert result["verdict"] == "ORPHAN", f"expected ORPHAN, got: {result}"

        card = json.loads(card_path.read_text())
        assert card["reachability"]["verdict"] == "ORPHAN"

    def test_orphan_verdict_is_not_pass(self, tmp_path):
        """Confirm ORPHAN is not in the passing set (exit-1 contract)."""
        from prd_taskmaster.reachability_cmd import _PASS_VERDICTS
        assert "ORPHAN" not in _PASS_VERDICTS
        assert "ERROR" not in _PASS_VERDICTS


class TestRunReachabilitySweepAdditiveCard:
    def test_existing_card_keys_preserved(self, tmp_path):
        """Sweep write is additive: other card keys survive."""
        repo, start, _head, tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        card_path = _write_cdd_card(repo, tid, extra={
            "testing_plan": [{"check": "unit tests pass", "evidence": "pytest"}],
            "grading": {"grade": "A", "score": 10},
            "custom_field": "preserve-me",
        })

        run_reachability_sweep(tid, start, cwd=str(repo))

        card = json.loads(card_path.read_text())
        # All pre-existing keys still present.
        assert card["task_id"] == tid
        assert card["custom_field"] == "preserve-me"
        assert card["grading"]["grade"] == "A"
        assert len(card["testing_plan"]) == 1
        # Reachability block written.
        assert "reachability" in card


class TestRunReachabilitySweepExempt:
    def test_tier_exempt_writes_exempt_verdict(self, tmp_path):
        """spike/domain-model tier → EXEMPT verdict written to CDD card."""
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\nname = 'mypkg'\n")
        _commit_all(repo, "initial")
        start = _git(repo, "rev-parse", "HEAD")

        _write_tasks(repo, [_make_task(1, tier="spike")])
        card_path = _write_cdd_card(repo, "1")

        result = run_reachability_sweep("1", start, cwd=str(repo))

        assert result["verdict"] == "EXEMPT"
        card = json.loads(card_path.read_text())
        assert card["reachability"]["verdict"] == "EXEMPT"


class TestRunReachabilitySweepErrors:
    def test_no_cdd_card_raises_command_error(self, tmp_path):
        """If no CDD card exists, raise CommandError with a clear message."""
        repo, start, _head, tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        # Create the cdd dir but not the card.
        (repo / ".atlas-ai" / "cdd").mkdir(parents=True)

        with pytest.raises(CommandError) as exc_info:
            run_reachability_sweep(tid, start, cwd=str(repo))

        assert "no CDD card" in exc_info.value.message or "CDD card" in exc_info.value.message

    def test_no_tasks_json_raises_command_error(self, tmp_path):
        """If tasks.json is missing, raise CommandError."""
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
        _commit_all(repo, "init")
        start = _git(repo, "rev-parse", "HEAD")
        _write_cdd_card(repo, "1")

        with pytest.raises(CommandError) as exc_info:
            run_reachability_sweep("1", start, cwd=str(repo))

        assert "tasks.json" in exc_info.value.message

    def test_task_not_found_raises_command_error(self, tmp_path):
        """If task id not in tasks.json, raise CommandError."""
        repo, start, _head, _tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(99, tier="wired")])
        _write_cdd_card(repo, "1")

        with pytest.raises(CommandError) as exc_info:
            run_reachability_sweep("1", start, cwd=str(repo))

        assert "not found" in exc_info.value.message


# ─── Part B: cmd_set_status auto-read ────────────────────────────────────────


def _write_project(tmp_path: Path, tasks: list, *, tag: str = "master") -> Path:
    """Write .taskmaster/tasks/tasks.json and state.json."""
    payload = {
        tag: {
            "tasks": tasks,
            "metadata": {"created": "2026-01-01T00:00:00Z"},
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


def _reload(tasks_file: Path, tag: str = "master") -> dict[str, dict]:
    raw = json.loads(tasks_file.read_text())
    return {str(t["id"]): t for t in raw[tag]["tasks"]}


class TestParseReachabilityArg:
    def test_none_returns_none(self):
        assert _parse_reachability_arg(None) is None

    def test_bare_wired_returns_dict(self):
        r = _parse_reachability_arg("WIRED")
        assert r == {"verdict": "WIRED"}

    def test_bare_exempt_returns_dict(self):
        r = _parse_reachability_arg("EXEMPT")
        assert r == {"verdict": "EXEMPT"}

    def test_bare_orphan_returns_dict(self):
        r = _parse_reachability_arg("ORPHAN")
        assert r == {"verdict": "ORPHAN"}

    def test_json_dict_parsed(self):
        r = _parse_reachability_arg('{"verdict": "WIRED", "tier": "wired"}')
        assert r == {"verdict": "WIRED", "tier": "wired"}

    def test_invalid_bare_raises(self):
        with pytest.raises(CommandError):
            _parse_reachability_arg("UNKNOWN_VERDICT")

    def test_invalid_json_raises(self):
        with pytest.raises(CommandError):
            _parse_reachability_arg("{bad json}")


class TestReadCddReachability:
    def test_reads_reachability_from_card(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cdd_dir = tmp_path / ".atlas-ai" / "cdd"
        cdd_dir.mkdir(parents=True)
        card = {"task_id": "1", "reachability": {"verdict": "WIRED", "tier": "wired"}}
        (cdd_dir / "task-1.json").write_text(json.dumps(card))

        result = _read_cdd_reachability("1")
        assert result == {"verdict": "WIRED", "tier": "wired"}

    def test_returns_none_when_no_card(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".atlas-ai" / "cdd").mkdir(parents=True)
        result = _read_cdd_reachability("42")
        assert result is None

    def test_returns_none_when_no_reachability_block(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cdd_dir = tmp_path / ".atlas-ai" / "cdd"
        cdd_dir.mkdir(parents=True)
        (cdd_dir / "task-1.json").write_text(json.dumps({"task_id": "1"}))
        result = _read_cdd_reachability("1")
        assert result is None


class TestSetStatusAutoRead:
    def test_wired_task_auto_reads_wired_from_card(self, tmp_path, monkeypatch):
        """wired task, CDD card has WIRED verdict → set-status done succeeds with no --reachability."""
        tasks_file = _write_project(tmp_path, [_make_task(1, tier="wired")])
        # Write CDD card with WIRED reachability already in place (as if sweep ran).
        cdd_dir = tmp_path / ".atlas-ai" / "cdd"
        cdd_dir.mkdir(parents=True)
        card = {
            "task_id": "1",
            "reachability": {"verdict": "WIRED", "tier": "wired", "start_commit": "abc123"},
        }
        (cdd_dir / "task-1.json").write_text(json.dumps(card))
        monkeypatch.chdir(tmp_path)

        # No --reachability flag → auto-reads WIRED from card.
        result = run_set_status("1", "done")

        assert result["ok"] is True
        assert result["status"] == "done"
        tasks = _reload(tasks_file)
        assert tasks["1"]["status"] == "done"
        # run_set_status persists the auto-read reachability dict.
        assert tasks["1"]["reachability"]["verdict"] == "WIRED"

    def test_wired_task_auto_reads_orphan_raises(self, tmp_path, monkeypatch):
        """wired task, CDD card has ORPHAN verdict → set-status done raises.

        When the CDD card has ORPHAN, auto-read provides the ORPHAN dict to
        run_set_status, which then fires the blocking-verdict gate.  The error
        message includes 'ORPHAN'.
        """
        _write_project(tmp_path, [_make_task(1, tier="wired")])
        cdd_dir = tmp_path / ".atlas-ai" / "cdd"
        cdd_dir.mkdir(parents=True)
        card = {
            "task_id": "1",
            "reachability": {"verdict": "ORPHAN", "tier": "wired"},
        }
        (cdd_dir / "task-1.json").write_text(json.dumps(card))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(CommandError) as exc_info:
            run_set_status("1", "done")

        # The gate reads the ORPHAN from the card and blocks with a message
        # that references the blocking verdict.
        msg = exc_info.value.message
        assert "ORPHAN" in msg or "reachability" in msg.lower()

    def test_explicit_reachability_wired_passes(self, tmp_path, monkeypatch):
        """--reachability WIRED explicit → passes (no card required)."""
        tasks_file = _write_project(tmp_path, [_make_task(1, tier="wired")])
        monkeypatch.chdir(tmp_path)

        result = run_set_status("1", "done", reachability={"verdict": "WIRED"})

        assert result["ok"] is True
        tasks = _reload(tasks_file)
        assert tasks["1"]["status"] == "done"

    def test_explicit_reachability_json_dict_passes(self, tmp_path, monkeypatch):
        """Explicit reachability as a full dict → ok."""
        tasks_file = _write_project(tmp_path, [_make_task(1, tier="wired")])
        monkeypatch.chdir(tmp_path)

        sweep = {"verdict": "EXEMPT", "reason": "entrypoint", "tier": "wired"}
        result = run_set_status("1", "done", reachability=sweep)

        assert result["ok"] is True
        tasks = _reload(tasks_file)
        assert tasks["1"]["reachability"]["verdict"] == "EXEMPT"

    def test_untiered_done_no_flags_still_works(self, tmp_path, monkeypatch):
        """Backward-compat: untiered task done with no --reachability → ok."""
        tasks_file = _write_project(tmp_path, [_make_task(1)])  # no tier
        monkeypatch.chdir(tmp_path)

        result = run_set_status("1", "done")

        assert result["ok"] is True
        tasks = _reload(tasks_file)
        assert tasks["1"]["status"] == "done"

    def test_wired_task_no_card_no_reachability_raises(self, tmp_path, monkeypatch):
        """wired task, no CDD card, no --reachability → CommandError (RA5 gate)."""
        _write_project(tmp_path, [_make_task(1, tier="wired")])
        monkeypatch.chdir(tmp_path)
        # No CDD card written — auto-read returns None → gate fires.

        with pytest.raises(CommandError) as exc_info:
            run_set_status("1", "done")

        assert "reachability" in exc_info.value.message.lower()

    def test_wired_task_card_missing_reachability_block_raises(self, tmp_path, monkeypatch):
        """wired task, CDD card exists but has no reachability key → CommandError."""
        _write_project(tmp_path, [_make_task(1, tier="wired")])
        cdd_dir = tmp_path / ".atlas-ai" / "cdd"
        cdd_dir.mkdir(parents=True)
        # Card without reachability block.
        (cdd_dir / "task-1.json").write_text(json.dumps({"task_id": "1"}))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(CommandError) as exc_info:
            run_set_status("1", "done")

        assert "reachability" in exc_info.value.message.lower()


class TestEndToEnd:
    """Integration: sweep writes WIRED → set-status auto-reads → done."""

    def test_sweep_then_set_status_done_e2e(self, tmp_path):
        """Full end-to-end: sweep writes WIRED into card, then set-status reads it."""
        repo, start, _head, tid = _make_wired_py_repo(tmp_path)
        _write_tasks(repo, [_make_task(1, tier="wired")])
        _write_cdd_card(repo, tid)

        # Step 1: sweep writes verdict.
        sweep_result = run_reachability_sweep(tid, start, cwd=str(repo))
        assert sweep_result["verdict"] == "WIRED"

        # Step 2: set-status done (no explicit reachability) → auto-reads from card.
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(str(repo))
            result = run_set_status(tid, "done")
        finally:
            os.chdir(old_cwd)

        assert result["ok"] is True
        assert result["status"] == "done"
