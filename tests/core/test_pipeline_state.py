import pytest
from pathlib import Path

from prd_taskmaster.pipeline import current_phase, advance_phase, check_gate, preflight, ATLAS_AI_DIR

PHASES = ["SETUP", "DISCOVER", "GENERATE", "HANDOFF", "EXECUTE"]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_current_phase_none_when_no_state_file(project):
    result = current_phase()
    assert result["current_phase"] is None
    assert result["phases_completed"] == []


def test_advance_phase_from_none_to_SETUP(project):
    result = advance_phase(expected_current=None, target="SETUP", evidence={"installed": True})
    assert result["ok"] is True
    assert result["new_phase"] == "SETUP"
    after = current_phase()
    assert after["current_phase"] == "SETUP"


def test_advance_phase_rejects_illegal_transition(project):
    advance_phase(expected_current=None, target="SETUP", evidence={})
    result = advance_phase(expected_current="SETUP", target="HANDOFF", evidence={})
    assert result["ok"] is False
    assert "illegal transition" in result["error"].lower()


def test_advance_phase_CAS_rejects_stale_expected_current(project):
    advance_phase(expected_current=None, target="SETUP", evidence={})
    # Concurrent session advances to DISCOVER
    advance_phase(expected_current="SETUP", target="DISCOVER", evidence={})
    # First session still thinks we're in SETUP — should fail
    result = advance_phase(expected_current="SETUP", target="DISCOVER", evidence={})
    assert result["ok"] is False
    assert "stale" in result["error"].lower() or "cas" in result["error"].lower()


def test_check_gate_SETUP_requires_validate_setup_ready(project):
    missing = check_gate(phase="SETUP", evidence={})
    assert missing["gate_passed"] is False
    assert "validate_setup" in missing["violations"][0].lower() or "ready" in missing["violations"][0].lower()

    ok = check_gate(phase="SETUP", evidence={"validate_setup": {"ready": True, "critical_failures": 0}})
    assert ok["gate_passed"] is True


def test_preflight_returns_recommended_action(project):
    result = preflight()
    assert "recommended_action" in result
    assert result["recommended_action"] in [
        "recover",
        "run_setup",
        "generate_prd",
        "parse_prd",
        "resume",
        "resume_existing_tasks",
        "select_taskmaster_tag",
        "complete",
    ]


def test_preflight_reads_standard_taskmaster_state_and_recommends_pending_tag(project):
    """Existing projects store TaskMaster state in .taskmaster, not .atlas-ai/taskmaster."""
    tm = project / ".taskmaster"
    (tm / "docs").mkdir(parents=True)
    (tm / "tasks").mkdir(parents=True)
    (tm / "docs" / "prd.md").write_text("# Existing PRD\n")
    (tm / "state.json").write_text(
        '{"currentTag":"production-agent","migrationNoticeShown":true}'
    )
    (tm / "tasks" / "tasks.json").write_text(
        """
        {
          "master": {
            "tasks": [
              {"id": 1, "title": "done", "status": "done"},
              {"id": 2, "title": "next", "status": "pending"}
            ]
          },
          "production-agent": {
            "tasks": [
              {"id": 1, "title": "done", "status": "done"}
            ]
          }
        }
        """
    )

    result = preflight()

    assert result["has_taskmaster"] is True
    assert result["taskmaster_root"] == ".taskmaster"
    assert result["tasks_path"] == ".taskmaster/tasks/tasks.json"
    assert result["prd_path"] == ".taskmaster/docs/prd.md"
    assert result["current_tag"] == "production-agent"
    assert result["task_count"] == 1
    assert result["pending_task_count"] == 0
    assert result["tag_counts"]["master"] == {"total": 2, "pending": 1, "done": 1}
    assert result["recommended_tag"] == "master"
    assert result["recommended_action"] == "select_taskmaster_tag"


def test_preflight_recommends_resume_when_current_tag_has_pending_tasks(project):
    tm = project / ".taskmaster"
    (tm / "docs").mkdir(parents=True)
    (tm / "tasks").mkdir(parents=True)
    (tm / "docs" / "prd.md").write_text("# Existing PRD\n")
    (tm / "state.json").write_text('{"currentTag":"master"}')
    (tm / "tasks" / "tasks.json").write_text(
        '{"master":{"tasks":[{"id":11,"title":"next","status":"pending"}]}}'
    )

    result = preflight()

    assert result["current_tag"] == "master"
    assert result["task_count"] == 1
    assert result["pending_task_count"] == 1
    assert result["recommended_tag"] == "master"
    assert result["recommended_action"] == "resume_existing_tasks"


def test_pipeline_json_written_atomically(project, monkeypatch):
    """Verify pipeline.json write goes through atomic_write."""
    advance_phase(expected_current=None, target="SETUP", evidence={"installed": True})
    pipeline_file = project / ".atlas-ai" / "state" / "pipeline.json"
    assert pipeline_file.exists()
    # no leftover .tmp files
    tmp_files = list(pipeline_file.parent.glob("*.tmp.*"))
    assert tmp_files == [], f"Leftover tmp files: {tmp_files}"
