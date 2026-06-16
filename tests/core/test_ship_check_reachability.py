"""Gate 6 — reachability contract for skel/ship-check.py.

Gate 6 reads the 'reachability' block recorded in each task's CDD card
(written by execute-task RA6).  It does NOT re-execute the sweep; the
standalone skel stays stdlib-only.

Contract:
  * done + tier in {wired, live} + no CDD card          → FAIL-CLOSED block
  * done + tier in {wired, live} + card has no reach key → FAIL-CLOSED block
  * done + tier in {wired, live} + verdict ORPHAN        → block
  * done + tier in {wired, live} + verdict ERROR         → block
  * done + tier in {wired, live} + verdict WIRED/EXEMPT  → pass
  * done + tier domain-model (any reachability or none)  → skipped (pass)
  * status != done (wired tier, no reachability)         → skipped (pass)

The oracle gate (Gate 5) must also be satisfied for run_all_gates to pass in
the subprocess tests; we wire ATLAS_ORACLE_CMD to a fake PASS oracle.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIP = REPO_ROOT / "skel" / "ship-check.py"


# ─── importlib loader (mirrors test_ship_check_oracle.py) ────────────────────


def _load():
    spec = importlib.util.spec_from_file_location("ship_check_mod", SHIP)
    mod = importlib.util.module_from_spec(spec)
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = prev
    return mod


# ─── fake subprocess.run factory (reuses oracle-test pattern) ────────────────


def _fake_run_oracle_pass(cmd, *args, **kwargs):
    """Stub subprocess.run: rev-parse → deadbeef; oracle grade → PASS."""
    joined = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
    if "rev-parse" in joined:
        return types.SimpleNamespace(stdout="deadbeef\n", stderr="", returncode=0)
    if "oracle" in joined and "grade" in joined:
        return types.SimpleNamespace(stdout='{"verdict":"PASS"}', stderr="", returncode=0)
    raise AssertionError(f"unexpected subprocess command: {joined}")


# ─── project scaffolding helpers ─────────────────────────────────────────────


def _setup_base(tmp_path: Path, tasks: list) -> Path:
    """Write Gates 1-4 green with the given task list.

    Each entry in ``tasks`` is a dict with at least 'id' and 'status'.
    CDD cards are created for every task whose status == 'done', with a
    grading block so Gate 5 (oracle) can run.  No reachability block is added
    by default — individual tests add it as needed.
    """
    atlas = tmp_path / ".atlas-ai"
    (atlas / "state").mkdir(parents=True)
    (atlas / "state" / "pipeline.json").write_text(
        json.dumps({"current_phase": "EXECUTE"})
    )
    tm = tmp_path / ".taskmaster" / "tasks"
    tm.mkdir(parents=True)
    (tm / "tasks.json").write_text(json.dumps({"master": {"tasks": tasks}}))
    docs = tmp_path / ".taskmaster" / "docs"
    docs.mkdir(parents=True)
    (docs / "plan.md").write_text("# Plan\n")
    cdd = atlas / "cdd"
    cdd.mkdir(parents=True)
    for t in tasks:
        if t.get("status") == "done":
            card: dict = {"id": t["id"], "grading": {"command": ["sh", "grade.sh"]}}
            (cdd / f"task-{t['id']}.json").write_text(json.dumps(card))
    return atlas


def _add_reachability(atlas: Path, tid, verdict: str, modules: list | None = None) -> None:
    """Patch an existing CDD card to include a reachability block."""
    card_path = atlas / "cdd" / f"task-{tid}.json"
    card = json.loads(card_path.read_text())
    reach: dict = {"verdict": verdict}
    if modules is not None:
        reach["modules"] = modules
    card["reachability"] = reach
    card_path.write_text(json.dumps(card))


# ─── fake oracle shell script for subprocess tests ───────────────────────────


def _fake_oracle_cmd(tmp_path: Path) -> str:
    """Return ATLAS_ORACLE_CMD pointing at a tiny shell script that emits PASS."""
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


def _run_subprocess(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ATLAS_ORACLE_CMD"] = _fake_oracle_cmd(tmp_path)
    return subprocess.run(
        ["python3", str(SHIP), *extra],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests for gate_reachability directly
# ═══════════════════════════════════════════════════════════════════════════════


class TestGateReachabilityUnit:
    """Direct unit tests — bypass run_all_gates to isolate Gate 6."""

    def test_wired_task_with_wired_verdict_passes(self, tmp_path):
        tasks = [{"id": 1, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 1, "WIRED")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures
        assert failures == []

    def test_wired_task_with_exempt_verdict_passes(self, tmp_path):
        tasks = [{"id": 2, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 2, "EXEMPT")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_wired_task_with_orphan_verdict_blocks(self, tmp_path):
        tasks = [{"id": 3, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 3, "ORPHAN", modules=["myapp.core"])
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("3" in f and "ORPHAN" in f for f in failures), failures

    def test_wired_task_with_error_verdict_blocks(self, tmp_path):
        tasks = [{"id": 4, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 4, "ERROR")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("4" in f and "ERROR" in f for f in failures), failures

    def test_wired_task_missing_reachability_key_blocks(self, tmp_path):
        """No 'reachability' key in the CDD card → fail-closed."""
        tasks = [{"id": 5, "status": "done", "tier": "wired"}]
        _setup_base(tmp_path, tasks)  # card has grading but no reachability
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("5" in f and "reachability" in f for f in failures), failures

    def test_wired_task_no_cdd_card_blocks(self, tmp_path):
        """No CDD card at all for a wired done task → fail-closed."""
        # Don't call _setup_base; build minimum structure manually.
        atlas = tmp_path / ".atlas-ai"
        (atlas / "cdd").mkdir(parents=True)
        tasks = [{"id": 6, "status": "done", "tier": "wired"}]
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("6" in f and "no CDD card" in f for f in failures), failures

    def test_live_task_with_wired_verdict_passes(self, tmp_path):
        tasks = [{"id": 7, "status": "done", "tier": "live"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 7, "WIRED")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_live_task_with_orphan_verdict_blocks(self, tmp_path):
        tasks = [{"id": 8, "status": "done", "tier": "live"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 8, "ORPHAN")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("8" in f and "ORPHAN" in f for f in failures), failures

    def test_domain_model_task_ignored_even_with_orphan(self, tmp_path):
        """domain-model tier: Gate 6 skips entirely — ORPHAN is not a blocker."""
        tasks = [{"id": 9, "status": "done", "tier": "domain-model"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 9, "ORPHAN")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures
        assert failures == []

    def test_domain_model_task_ignored_with_no_reachability(self, tmp_path):
        """domain-model tier + no reachability block: skipped, no failure."""
        tasks = [{"id": 10, "status": "done", "tier": "domain-model"}]
        _setup_base(tmp_path, tasks)
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_spike_task_ignored(self, tmp_path):
        tasks = [{"id": 11, "status": "done", "tier": "spike"}]
        _setup_base(tmp_path, tasks)
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_untiered_task_ignored(self, tmp_path):
        """A task with no tier field defaults to domain-model → skipped."""
        tasks = [{"id": 12, "status": "done"}]
        _setup_base(tmp_path, tasks)
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_non_done_wired_task_ignored(self, tmp_path):
        """pending wired task: Gate 6 skips non-done tasks."""
        tasks = [{"id": 13, "status": "pending", "tier": "wired"}]
        _setup_base(tmp_path, tasks)  # no card written for non-done
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_unknown_verdict_blocks_fail_closed(self, tmp_path):
        """A verdict string that is not WIRED/EXEMPT/ORPHAN/ERROR → fail-closed."""
        tasks = [{"id": 14, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 14, "UNKNOWN_GARBAGE")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("14" in f for f in failures), failures

    def test_phaseconfig_tier_respected(self, tmp_path):
        """tier nested in phaseConfig.tier is honoured."""
        tasks = [{"id": 15, "status": "done", "phaseConfig": {"tier": "wired"}}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 15, "WIRED")
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_combined_card_is_found(self, tmp_path):
        """A combined task-15-16-17.json card covers task 16."""
        atlas = tmp_path / ".atlas-ai"
        (atlas / "cdd").mkdir(parents=True)
        combined = atlas / "cdd" / "task-15-16-17.json"
        combined.write_text(json.dumps({
            "id": "15-16-17",
            "grading": {"command": ["sh", "grade.sh"]},
            "reachability": {"verdict": "WIRED"},
        }))
        tasks = [{"id": 16, "status": "done", "tier": "wired"}]
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is True, failures

    def test_modules_listed_in_orphan_failure_message(self, tmp_path):
        """ORPHAN failure message includes the module names from the card."""
        tasks = [{"id": 20, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability(atlas, 20, "ORPHAN", modules=["myapp.dead_code", "myapp.other"])
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        assert any("myapp.dead_code" in f for f in failures), failures


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests via run_all_gates (importlib, monkeypatched oracle)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGate6ViaRunAllGates:
    """run_all_gates integration: Gate 6 is wired after Gate 5."""

    def test_wired_ships_when_reachability_is_wired(self, tmp_path, monkeypatch, capsys):
        tasks_data = [{"id": 1, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 1, "WIRED")
        mod = _load()
        monkeypatch.setattr(mod.subprocess, "run", _fake_run_oracle_pass)
        ok, failures = mod.run_all_gates(tmp_path)
        assert ok is True, f"failures={failures!r}"

    def test_orphan_blocks_run_all_gates(self, tmp_path, monkeypatch):
        tasks_data = [{"id": 2, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 2, "ORPHAN", modules=["myapp.route"])
        mod = _load()
        monkeypatch.setattr(mod.subprocess, "run", _fake_run_oracle_pass)
        ok, failures = mod.run_all_gates(tmp_path)
        assert ok is False
        assert any("2" in f and "ORPHAN" in f for f in failures), failures

    def test_missing_reachability_blocks_run_all_gates(self, tmp_path, monkeypatch):
        tasks_data = [{"id": 3, "status": "done", "tier": "live"}]
        _setup_base(tmp_path, tasks_data)  # card has no reachability key
        mod = _load()
        monkeypatch.setattr(mod.subprocess, "run", _fake_run_oracle_pass)
        ok, failures = mod.run_all_gates(tmp_path)
        assert ok is False
        assert any("3" in f for f in failures), failures

    def test_domain_model_does_not_block_run_all_gates(self, tmp_path, monkeypatch):
        """domain-model done task with NO reachability block: whole suite passes."""
        tasks_data = [{"id": 4, "status": "done", "tier": "domain-model"}]
        _setup_base(tmp_path, tasks_data)
        mod = _load()
        monkeypatch.setattr(mod.subprocess, "run", _fake_run_oracle_pass)
        ok, failures = mod.run_all_gates(tmp_path)
        assert ok is True, f"failures={failures!r}"

    def test_untiered_done_task_does_not_block_run_all_gates(self, tmp_path, monkeypatch):
        tasks_data = [{"id": 5, "status": "done"}]
        _setup_base(tmp_path, tasks_data)
        mod = _load()
        monkeypatch.setattr(mod.subprocess, "run", _fake_run_oracle_pass)
        ok, failures = mod.run_all_gates(tmp_path)
        assert ok is True, f"failures={failures!r}"

    def test_non_done_wired_task_does_not_block_run_all_gates(self, tmp_path, monkeypatch):
        # All tasks must be done for Gate 2 to pass; use a done untiered task
        # plus a pending wired task and verify the pending one doesn't trigger Gate 6.
        # NOTE: Gate 2 requires ALL tasks done, so we can't mix done/pending here.
        # Test Gate 6 isolation: directly call gate_reachability with pending task.
        tasks_data = [{"id": 6, "status": "pending", "tier": "wired"}]
        _setup_base(tmp_path, [])  # cdd dir created, no cards needed
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks_data)
        assert ok is True, failures


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-end subprocess tests (main() → SHIP_CHECK_OK / exit 1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGate6Subprocess:
    """Drive the actual script as a subprocess; oracle stubbed via ATLAS_ORACLE_CMD."""

    def test_wired_wired_verdict_ships(self, tmp_path):
        """Scenario 1: done wired task with WIRED verdict → SHIP_CHECK_OK, exit 0."""
        tasks_data = [{"id": 1, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 1, "WIRED")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 0, f"stderr={r.stderr!r}"
        assert "SHIP_CHECK_OK" in r.stdout

    def test_orphan_blocks_main(self, tmp_path):
        """Scenario 2: done wired task ORPHAN → nothing on stdout, exit 1."""
        tasks_data = [{"id": 2, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 2, "ORPHAN")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 1
        assert "SHIP_CHECK_OK" not in r.stdout
        assert "ORPHAN" in r.stderr

    def test_missing_reachability_block_blocks_main(self, tmp_path):
        """Scenario 3: wired done task, card has no 'reachability' key → exit 1."""
        tasks_data = [{"id": 3, "status": "done", "tier": "wired"}]
        _setup_base(tmp_path, tasks_data)  # card has grading but no reachability
        r = _run_subprocess(tmp_path)
        assert r.returncode == 1
        assert "SHIP_CHECK_OK" not in r.stdout
        assert "reachability" in r.stderr.lower()

    def test_error_verdict_blocks_main(self, tmp_path):
        """Scenario 4: done wired task ERROR verdict → exit 1."""
        tasks_data = [{"id": 4, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 4, "ERROR")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 1
        assert "SHIP_CHECK_OK" not in r.stdout
        assert "ERROR" in r.stderr

    def test_domain_model_not_blocked_even_without_reachability(self, tmp_path):
        """Scenario 5: domain-model done task, no reachability → ships fine."""
        tasks_data = [{"id": 5, "status": "done", "tier": "domain-model"}]
        _setup_base(tmp_path, tasks_data)
        r = _run_subprocess(tmp_path)
        assert r.returncode == 0, f"stderr={r.stderr!r}"
        assert "SHIP_CHECK_OK" in r.stdout

    def test_live_tier_with_orphan_blocks(self, tmp_path):
        """live tier is also subject to Gate 6."""
        tasks_data = [{"id": 6, "status": "done", "tier": "live"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 6, "ORPHAN")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 1
        assert "SHIP_CHECK_OK" not in r.stdout

    def test_live_tier_with_exempt_ships(self, tmp_path):
        """live tier + EXEMPT verdict → ships."""
        tasks_data = [{"id": 7, "status": "done", "tier": "live"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 7, "EXEMPT")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 0, f"stderr={r.stderr!r}"
        assert "SHIP_CHECK_OK" in r.stdout

    def test_remediation_hint_in_orphan_failure(self, tmp_path):
        """ORPHAN failure message must mention remediation (wire or re-status)."""
        tasks_data = [{"id": 8, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks_data)
        _add_reachability(atlas, 8, "ORPHAN")
        r = _run_subprocess(tmp_path)
        assert r.returncode == 1
        assert "wire" in r.stderr.lower() or "re-status" in r.stderr.lower(), r.stderr


# ═══════════════════════════════════════════════════════════════════════════════
# Regression tests: dict-shaped modules (real sweep_task / reachability-sweep output)
# Both copies of gate_reachability must handle this without crashing.
# ═══════════════════════════════════════════════════════════════════════════════

_DICT_MODULES_REACHABILITY = {
    "verdict": "ORPHAN",
    "modules": [
        {"verdict": "ORPHAN", "module": "pkg/widget.py", "importers": []},
    ],
}


def _add_reachability_raw(atlas: Path, tid, reach: dict) -> None:
    """Patch a CDD card to set the reachability block to a raw dict."""
    card_path = atlas / "cdd" / f"task-{tid}.json"
    card = json.loads(card_path.read_text())
    card["reachability"] = reach
    card_path.write_text(json.dumps(card))


class TestGateReachabilityDictModules:
    """Regression: gate_reachability must NOT crash when modules are dicts.

    Both copies — skel/ship-check.py (loaded via importlib) and
    prd_taskmaster.shipcheck — are exercised with the exact shape that
    reachability.sweep_task / reachability-sweep writes:

        {"verdict": "ORPHAN", "module": "pkg/widget.py", "importers": []}
    """

    def test_skel_dict_modules_no_crash_and_module_name_in_failure(self, tmp_path):
        """skel copy: dict-shaped modules → no TypeError, module name appears in failure."""
        tasks = [{"id": 50, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability_raw(atlas, 50, _DICT_MODULES_REACHABILITY)
        mod = _load()
        # Must not raise TypeError
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False, "ORPHAN verdict should block ship"
        assert failures, "expected at least one failure message"
        assert any("pkg/widget.py" in f for f in failures), (
            f"module name missing from failure messages: {failures!r}"
        )

    def test_twin_dict_modules_no_crash_and_module_name_in_failure(self, tmp_path):
        """prd_taskmaster.shipcheck twin: dict-shaped modules → no TypeError, module name in failure."""
        from prd_taskmaster import shipcheck as twin

        tasks = [{"id": 51, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability_raw(atlas, 51, _DICT_MODULES_REACHABILITY)
        # Must not raise TypeError
        ok, failures = twin.gate_reachability(tmp_path, tasks)
        assert ok is False, "ORPHAN verdict should block ship"
        assert failures, "expected at least one failure message"
        assert any("pkg/widget.py" in f for f in failures), (
            f"module name missing from failure messages: {failures!r}"
        )

    def test_skel_dict_modules_multi_module(self, tmp_path):
        """skel copy: multiple dict-shaped modules all appear in the failure message."""
        reach = {
            "verdict": "ORPHAN",
            "modules": [
                {"verdict": "ORPHAN", "module": "pkg/alpha.py", "importers": []},
                {"verdict": "ORPHAN", "module": "pkg/beta.py", "importers": []},
            ],
        }
        tasks = [{"id": 52, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability_raw(atlas, 52, reach)
        mod = _load()
        ok, failures = mod.gate_reachability(tmp_path, tasks)
        assert ok is False
        combined = " ".join(failures)
        assert "pkg/alpha.py" in combined, failures
        assert "pkg/beta.py" in combined, failures

    def test_twin_dict_modules_multi_module(self, tmp_path):
        """twin: multiple dict-shaped modules all appear in the failure message."""
        from prd_taskmaster import shipcheck as twin

        reach = {
            "verdict": "ORPHAN",
            "modules": [
                {"verdict": "ORPHAN", "module": "pkg/alpha.py", "importers": []},
                {"verdict": "ORPHAN", "module": "pkg/beta.py", "importers": []},
            ],
        }
        tasks = [{"id": 53, "status": "done", "tier": "wired"}]
        atlas = _setup_base(tmp_path, tasks)
        _add_reachability_raw(atlas, 53, reach)
        ok, failures = twin.gate_reachability(tmp_path, tasks)
        assert ok is False
        combined = " ".join(failures)
        assert "pkg/alpha.py" in combined, failures
        assert "pkg/beta.py" in combined, failures
