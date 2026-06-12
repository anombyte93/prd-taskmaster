"""Native backend tests for the v4.1 backend abstraction."""

import json
from pathlib import Path

import pytest

from prd_taskmaster import llm_client


def _valid_tasks(count: int = 1) -> dict:
    return {
        "tasks": [
            {
                "id": idx,
                "title": f"Task {idx}",
                "description": f"Deliver task {idx}",
                "details": "Implementation notes with concrete files and constraints.",
                "testStrategy": "python3 -m pytest tests/ -q",
                "status": "pending",
                "dependencies": [],
                "priority": "high" if idx == 1 else "medium",
                "subtasks": [
                    {
                        "id": 1,
                        "title": "Write failing test",
                        "description": "Add focused regression coverage.",
                        "status": "pending",
                        "dependencies": [],
                    },
                    {
                        "id": 2,
                        "title": "Implement behavior",
                        "description": "Make the failing test pass.",
                        "status": "pending",
                        "dependencies": [1],
                    },
                ],
            }
            for idx in range(1, count + 1)
        ]
    }


def _seed_project(tmp_path: Path, tasks: list[dict], tag: str = "master") -> Path:
    tm = tmp_path / ".taskmaster"
    (tm / "tasks").mkdir(parents=True, exist_ok=True)
    (tm / "docs").mkdir(parents=True, exist_ok=True)
    (tm / "reports").mkdir(parents=True, exist_ok=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": tag}))
    tasks_path = tm / "tasks" / "tasks.json"
    tasks_path.write_text(json.dumps({tag: {"tasks": tasks}}, indent=2))
    return tasks_path


def _pending_task(task_id: int = 1) -> dict:
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "description": "Needs expansion",
        "details": "Implement native backend expansion.",
        "testStrategy": "python3 -m pytest tests/core/test_native_backend.py -q",
        "status": "pending",
        "dependencies": [],
        "priority": "medium",
        "subtasks": [],
    }


def test_native_detect_reports_api_and_agent_modes(monkeypatch):
    from prd_taskmaster.backend import NativeBackend
    import prd_taskmaster

    monkeypatch.setattr(
        llm_client,
        "discover_key",
        lambda: {"provider": "anthropic", "key": "secret", "base_url": "https://example.test"},
    )
    api = NativeBackend().detect()
    assert api == {
        "name": "native",
        "available": True,
        "version": prd_taskmaster.__version__,
        "ai_ops": "api",
        "api_provider": "anthropic",
    }

    monkeypatch.setattr(llm_client, "discover_key", lambda: None)
    agent = NativeBackend().detect()
    assert agent["available"] is True
    assert agent["ai_ops"] == "agent"
    assert agent["api_provider"] is None


def test_init_project_idempotent_scaffold(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    result = NativeBackend().init_project()
    assert result["ok"] is True
    assert (tmp_path / ".taskmaster" / "docs").is_dir()
    assert (tmp_path / ".taskmaster" / "tasks").is_dir()
    assert (tmp_path / ".taskmaster" / "reports").is_dir()
    assert json.loads((tmp_path / ".taskmaster" / "state.json").read_text()) == {
        "currentTag": "master"
    }
    assert json.loads((tmp_path / ".taskmaster" / "tasks" / "tasks.json").read_text()) == {
        "master": {"tasks": []}
    }

    config = tmp_path / ".taskmaster" / "config.json"
    config.write_text(json.dumps({"custom": True}))
    second = NativeBackend().init_project()
    assert second["ok"] is True
    assert json.loads(config.read_text()) == {"custom": True}


def test_parse_prd_validates_and_writes_tagged_tasks(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nREQ-001: Build native backend.")
    calls = []
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "openai", "key": "k"})

    def fake_generate_json(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return _valid_tasks(2)

    monkeypatch.setattr(llm_client, "generate_json", fake_generate_json)

    result = NativeBackend().parse_prd(prd, 2, tag="native-tag")

    assert result["ok"] is True
    assert result["task_count"] == 2
    assert result["backend"] == "native"
    assert result["ai"] == "api"
    assert len(calls) == 1
    assert calls[0]["tier"] == "standard"
    assert calls[0]["schema_hint"] == TASKS_SCHEMA_HINT
    written = json.loads((tmp_path / ".taskmaster" / "tasks" / "tasks.json").read_text())
    assert list(written) == ["native-tag"]
    assert [task["id"] for task in written["native-tag"]["tasks"]] == [1, 2]


def test_parse_prd_success_echoes_telemetry_reference(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nREQ-001: Build native backend.")
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "anthropic", "key": "k"})
    telemetry_ref = {
        "path": str(tmp_path / ".atlas-ai" / "telemetry.jsonl"),
        "line": 1,
        "ts": "2026-06-12T00:00:00+00:00",
        "op_class": "structured_gen",
        "model": "claude-haiku-4-5-20251001",
        "backend": "native-api",
        "exit": 0,
    }
    calls = []

    def fake_generate_json(prompt, **kwargs):
        calls.append(kwargs)
        return _valid_tasks(2), telemetry_ref

    monkeypatch.setattr(llm_client, "generate_json", fake_generate_json)

    result = NativeBackend().parse_prd(prd, 2, tag="native-tag")

    assert result["ok"] is True
    assert result["task_count"] == 2
    assert result["tag"] == "native-tag"
    assert result["backend"] == "native"
    assert result["ai"] == "api"
    assert result["validation"]["task_count"] == 2
    assert result["telemetry_ref"] == telemetry_ref
    assert calls[0]["return_telemetry_ref"] is True


def test_parse_prd_invalid_candidate_returns_error_without_overwrite(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    tasks_path = _seed_project(tmp_path, [_pending_task()])
    before = tasks_path.read_text()
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "anthropic", "key": "k"})
    invalid = _valid_tasks(1)
    invalid["tasks"][0]["subtasks"] = invalid["tasks"][0]["subtasks"][:1]
    monkeypatch.setattr(llm_client, "generate_json", lambda *a, **k: invalid)

    result = NativeBackend().parse_prd(prd, 1)

    assert result["ok"] is False
    assert "Task validation failed" in result["error"]
    assert any("at least 2 subtasks" in problem for problem in result["problems"])
    assert tasks_path.read_text() == before


def test_expand_builds_packets_escalates_invalid_json_and_merges_once(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    tasks_path = _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "anthropic", "key": "k"})
    calls = []

    def fake_generate_json(prompt, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise llm_client.LLMError("invalid_json", "bad json")
        return {
            "id": 1,
            "complexityScore": 8,
            "recommendedSubtasks": 2,
            "reasoning": "Needs careful backend integration.",
            "researchNotes": "Reuse parallel.apply_results for the merge.",
            "subtasks": [
                {
                    "title": "Write expansion test",
                    "description": "Cover merge behavior.",
                    "details": "Assert subtasks are written once.",
                    "dependencies": [],
                },
                {
                    "title": "Implement expansion",
                    "description": "Generate and apply packet result.",
                    "details": "Use native backend API path.",
                    "dependencies": [1],
                },
            ],
        }

    monkeypatch.setattr(llm_client, "generate_json", fake_generate_json)

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is True
    assert result["applied"] == [1]
    assert result["failed"] == []
    assert [call["tier"] for call in calls] == ["standard", "capable"]
    merged = json.loads(tasks_path.read_text())
    task = merged["master"]["tasks"][0]
    assert [subtask["title"] for subtask in task["subtasks"]] == [
        "Write expansion test",
        "Implement expansion",
    ]
    rows = [
        json.loads(line)
        for line in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()
    ]
    assert rows[-1]["task_id"] == 1
    assert rows[-1]["escalated"] is True
    assert rows[-1]["backend"] == "native-api"


def test_rate_writes_taskmaster_report_from_batched_generation(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "openai", "key": "k"})
    calls = []

    def fake_generate_json(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {
            "complexityAnalysis": [
                {
                    "taskId": 1,
                    "taskTitle": "Task 1",
                    "complexityScore": 5,
                    "recommendedSubtasks": 3,
                    "expansionPrompt": "Expand Task 1",
                    "reasoning": "Moderate implementation work.",
                }
            ]
        }

    monkeypatch.setattr(llm_client, "generate_json", fake_generate_json)

    result = NativeBackend().rate(tag="master")

    assert result["ok"] is True
    assert len(calls) == 1
    assert result["complexityAnalysis"][0]["taskId"] == 1
    report = tmp_path / ".taskmaster" / "reports" / "task-complexity-report.json"
    assert report.is_file()
    written = json.loads(report.read_text())
    assert written["meta"]["generatedBy"] == "prd-taskmaster/native-backend"
    assert written["complexityAnalysis"][0]["complexityScore"] == 5


def test_no_key_operations_return_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(llm_client, "discover_key", lambda: None)

    parse = NativeBackend().parse_prd(prd, 1, tag="master")
    assert parse["ok"] is False
    assert parse["agent_action_required"]["op"] == "parse_prd"
    assert parse["agent_action_required"]["schema_hint"] == TASKS_SCHEMA_HINT

    expand = NativeBackend().expand(tag="master")
    assert expand["ok"] is False
    assert expand["agent_action_required"]["op"] == "expand"
    assert expand["agent_action_required"]["packets"]

    rate = NativeBackend().rate(tag="master")
    assert rate["ok"] is False
    assert rate["agent_action_required"]["op"] == "rate"
    assert "scoring_rubric" in rate["agent_action_required"]
