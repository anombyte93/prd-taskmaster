"""Oracle bridge tests — all subprocess calls are mocked; no real CLI/podman invoked."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from prd_taskmaster.oracle_bridge import grade_card, grade_task, OracleCardError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_graded_card(path: Path, extra: dict | None = None) -> Path:
    """Write a minimal valid Graded Card (has the required 'grading' key)."""
    card = {"id": "C-001", "grading": {"criteria": "all tests pass"}}
    if extra:
        card.update(extra)
    path.write_text(json.dumps(card))
    return path


def _fake_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Return a fake subprocess.CompletedProcess-like object."""
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _common_args(tmp_path: Path):
    """Return common keyword args for grade_card, pointing at tmp_path sub-dirs."""
    return dict(
        repo_path=tmp_path / "repo",
        commit_sha="abc123",
        held_root=tmp_path / "held",
        evidence_dir=tmp_path / "evidence",
        ledger_dir=tmp_path / "ledger",
    )


# ---------------------------------------------------------------------------
# Test 1: PASS round-trip + argv mapping
# ---------------------------------------------------------------------------

def test_pass_roundtrip_and_argv_mapping(tmp_path, monkeypatch):
    """grade_card returns ("PASS", full_dict) and passes correct CLI args."""
    card_path = _write_graded_card(tmp_path / "card.json")
    args = _common_args(tmp_path)

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _fake_proc(stdout='{"verdict":"PASS","exitCode":0,"ledgerEventId":"x"}')

    monkeypatch.setattr("prd_taskmaster.oracle_bridge.subprocess.run", fake_run)

    oracle_cmd = ["atlas"]
    verdict, detail = grade_card(card_path=card_path, oracle_cmd=oracle_cmd, **args)

    assert verdict == "PASS"
    assert detail == {"verdict": "PASS", "exitCode": 0, "ledgerEventId": "x"}

    # argv mapping checks
    assert "oracle" in captured_cmd
    assert "grade" in captured_cmd
    assert "--repo" in captured_cmd
    assert str(args["repo_path"]) in captured_cmd
    assert "--commit" in captured_cmd
    assert "abc123" in captured_cmd
    assert "--card" in captured_cmd
    assert str(card_path) in captured_cmd
    assert "--held" in captured_cmd
    assert str(args["held_root"]) in captured_cmd
    assert "--evidence" in captured_cmd
    assert str(args["evidence_dir"]) in captured_cmd
    assert "--ledger" in captured_cmd
    assert str(args["ledger_dir"]) in captured_cmd


# ---------------------------------------------------------------------------
# Test 2: Missing 'grading' block → OracleCardError
# ---------------------------------------------------------------------------

def test_missing_grading_block_raises(tmp_path, monkeypatch):
    """A card without a 'grading' key must raise OracleCardError (before shelling out)."""
    card_path = tmp_path / "card_no_grading.json"
    card_path.write_text(json.dumps({"id": "C-002", "title": "Some task"}))

    # subprocess.run should NOT be called — we assert by not patching it;
    # if the bridge reaches it the test will fail for a different reason.
    # But to be clean and not accidentally run a real 'atlas' binary, patch it too.
    def fake_run(cmd, **kwargs):
        raise AssertionError("subprocess.run should not be called when grading block absent")

    monkeypatch.setattr("prd_taskmaster.oracle_bridge.subprocess.run", fake_run)

    with pytest.raises(OracleCardError, match="no 'grading' block"):
        grade_card(card_path=card_path, **_common_args(tmp_path))


# ---------------------------------------------------------------------------
# Test 3: Fail-closed on unparseable output (non-JSON stdout)
# ---------------------------------------------------------------------------

def test_fail_closed_on_unparseable_output(tmp_path, monkeypatch):
    """Non-JSON stdout (e.g. 'podman: command not found') yields ("FAIL", {...}), never raises."""
    card_path = _write_graded_card(tmp_path / "card.json")

    def fake_run(cmd, **kwargs):
        return _fake_proc(stdout="podman: command not found", returncode=127)

    monkeypatch.setattr("prd_taskmaster.oracle_bridge.subprocess.run", fake_run)

    verdict, detail = grade_card(card_path=card_path, oracle_cmd=["atlas"], **_common_args(tmp_path))

    assert verdict == "FAIL"
    assert "error" in detail
    assert detail["returncode"] == 127


# ---------------------------------------------------------------------------
# Test 4: Fail-closed on CLI invocation error (FileNotFoundError)
# ---------------------------------------------------------------------------

def test_fail_closed_on_invocation_error(tmp_path, monkeypatch):
    """FileNotFoundError from subprocess.run yields ("FAIL", {...}), never raises."""
    card_path = _write_graded_card(tmp_path / "card.json")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("atlas: No such file or directory")

    monkeypatch.setattr("prd_taskmaster.oracle_bridge.subprocess.run", fake_run)

    verdict, detail = grade_card(card_path=card_path, oracle_cmd=["atlas"], **_common_args(tmp_path))

    assert verdict == "FAIL"
    assert "error" in detail
    assert "oracle CLI invocation failed" in detail["error"]


# ---------------------------------------------------------------------------
# Test 5: FAIL verdict passthrough
# ---------------------------------------------------------------------------

def test_fail_verdict_passthrough(tmp_path, monkeypatch):
    """A FAIL verdict from the oracle is passed through as ("FAIL", detail)."""
    card_path = _write_graded_card(tmp_path / "card.json")

    def fake_run(cmd, **kwargs):
        return _fake_proc(stdout='{"verdict":"FAIL"}', returncode=1)

    monkeypatch.setattr("prd_taskmaster.oracle_bridge.subprocess.run", fake_run)

    verdict, detail = grade_card(card_path=card_path, oracle_cmd=["atlas"], **_common_args(tmp_path))

    assert verdict == "FAIL"
    assert detail == {"verdict": "FAIL"}


# ---------------------------------------------------------------------------
# Test 6: grade_task missing card → OracleCardError
# ---------------------------------------------------------------------------

def test_grade_task_missing_card_raises(tmp_path):
    """grade_task raises OracleCardError when no CDD card exists for the given task."""
    # tmp_path has no .atlas-ai/cdd/task-1.json
    with pytest.raises(OracleCardError, match="no CDD card at"):
        grade_task(
            repo_root=tmp_path,
            task_id=1,
            commit_sha="deadbeef",
            held_root=tmp_path / "held",
            evidence_dir=tmp_path / "evidence",
            ledger_dir=tmp_path / "ledger",
        )
