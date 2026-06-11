"""Smoke tests for the imported stateful core: pipeline state machine,
gate checks, and the ship-check gate logic.

Each test runs in an isolated tmp_path via monkeypatch.chdir so the relative
path constants in pipeline.py / shipcheck.py resolve under the temp dir.
"""

from prd_taskmaster import pipeline, shipcheck


def test_fresh_current_phase_is_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = pipeline.current_phase()
    assert state["ok"] is True
    assert state["current_phase"] is None
    assert state["phases_completed"] == []


def test_advance_phase_none_to_setup_succeeds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = pipeline.advance_phase(None, "SETUP", {"validate_setup": {"ready": True}})
    assert result["ok"] is True
    assert result["new_phase"] == "SETUP"
    # The state file now reflects SETUP.
    assert pipeline.current_phase()["current_phase"] == "SETUP"


def test_advance_phase_stale_expected_current_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Fresh state is None; claiming the current phase is DISCOVER is stale.
    result = pipeline.advance_phase("DISCOVER", "GENERATE", {})
    assert result["ok"] is False
    assert "stale" in result["error"]
    assert result["actual"] is None


def test_advance_phase_illegal_transition_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # From None only None->SETUP is legal; None->GENERATE is illegal.
    result = pipeline.advance_phase(None, "GENERATE", {})
    assert result["ok"] is False
    assert "illegal transition" in result["error"]
    assert result["legal"] == ["SETUP"]


def test_check_gate_generate_passes_when_evidence_good(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = pipeline.check_gate("GENERATE", {
        "validation_grade": "GOOD",
        "task_count": 5,
        "subtask_coverage": 1.0,
    })
    assert result["gate_passed"] is True
    assert result["violations"] == []


def test_check_gate_generate_fails_on_needs_work(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = pipeline.check_gate("GENERATE", {
        "validation_grade": "NEEDS_WORK",
        "task_count": 5,
        "subtask_coverage": 1.0,
    })
    assert result["gate_passed"] is False
    assert any("validation_grade" in v for v in result["violations"])


def test_run_ship_check_empty_dir_not_passed_no_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Must not raise / not sys.exit; gate 1 (pipeline.json) fails in an empty dir.
    result = shipcheck.run_ship_check(cwd=str(tmp_path))
    assert result["passed"] is False
    assert result["exit_code"] == 1
    assert any("pipeline.json" in f for f in result["failures"])
    assert result["stdout"] is None
