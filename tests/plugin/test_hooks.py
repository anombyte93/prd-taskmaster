# tests/test_hooks.py
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_hook(hook_path, input_json):
    r = subprocess.run(
        ["python3", str(hook_path)],
        input=json.dumps(input_json),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return r.returncode, json.loads(r.stdout) if r.stdout.strip() else {}, r.stderr


def test_gate_enforcer_denies_advance_without_gate_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "gate_enforcer.py"
    input_json = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__plugin_prd_go__advance_phase",
        "tool_input": {"expected_current": None, "target": "SETUP", "evidence": {}},
        "session_id": "test-session",
    }
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    assert "evidence" in out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "").lower()


def test_gate_enforcer_allows_with_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "gate_enforcer.py"
    input_json = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__plugin_prd_go__advance_phase",
        "tool_input": {
            "expected_current": None,
            "target": "SETUP",
            "evidence": {"validate_setup": {"ready": True, "critical_failures": 0}},
        },
        "session_id": "test-session",
    }
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
    assert decision in (None, "allow")  # no denial


def test_mode_d_blocker_denies_atlas_cdd_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "mode_d_blocker.py"
    input_json = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__atlas-cdd__some_method",
        "tool_input": {},
        "session_id": "test-session",
    }
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    assert "waitlist" in out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "").lower()


def _write_pipeline(tmp_path, phase="EXECUTE"):
    p = tmp_path / ".atlas-ai" / "state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "pipeline.json").write_text(json.dumps({"current_phase": phase}))


def _write_tasks(tmp_path, tasks):
    p = tmp_path / ".atlas-ai" / "taskmaster" / "tasks"
    p.mkdir(parents=True, exist_ok=True)
    (p / "tasks.json").write_text(json.dumps({"master": {"tasks": tasks}}))


def test_evidence_gate_blocks_incomplete_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    _write_pipeline(tmp_path, phase="EXECUTE")
    _write_tasks(tmp_path, [
        {
            "id": "1",
            "status": "in-progress",
            "subtasks": [{"id": "1.1"}, {"id": "1.2"}],
            "evidence_files": [],
        }
    ])
    input_json = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    reason = out.get("reason", "")
    assert out.get("decision") == "block" or "incomplete" in reason.lower()


def test_evidence_gate_allows_complete_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    _write_pipeline(tmp_path, phase="EXECUTE")
    _write_tasks(tmp_path, [
        {
            "id": "1",
            "status": "in-progress",
            "subtasks": [{"id": "1.1"}, {"id": "1.2"}],
            "evidence_files": ["evidence/a.md", "evidence/b.md"],
        }
    ])
    input_json = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert "decision" not in out
    assert out == {}


def test_evidence_gate_noop_no_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    input_json = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out == {}


def test_evidence_gate_stop_hook_active_short_circuits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    _write_pipeline(tmp_path, phase="EXECUTE")
    _write_tasks(tmp_path, [
        {
            "id": "1",
            "status": "in-progress",
            "subtasks": [{"id": "1.1"}, {"id": "1.2"}],
            "evidence_files": [],
        }
    ])
    input_json = {"hook_event_name": "Stop", "stop_hook_active": True, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out == {}


def test_evidence_gate_done_task_not_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    _write_pipeline(tmp_path, phase="EXECUTE")
    _write_tasks(tmp_path, [
        {
            "id": "1",
            "status": "done",
            "subtasks": [{"id": "1.1"}, {"id": "1.2"}, {"id": "1.3"}],
            "evidence_files": [],
        }
    ])
    input_json = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out == {}


def test_evidence_gate_no_subtasks_key_no_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hook_path = REPO_ROOT / "hooks" / "evidence_gate.py"
    _write_pipeline(tmp_path, phase="EXECUTE")
    _write_tasks(tmp_path, [
        {
            "id": "1",
            "status": "in-progress",
            "evidence_files": [],
        }
    ])
    input_json = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "test-session"}
    rc, out, err = _run_hook(hook_path, input_json)
    assert rc == 0
    assert out == {}
