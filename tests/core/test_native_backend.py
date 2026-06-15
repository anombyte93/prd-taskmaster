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
    from prd_taskmaster import backend as backend_mod
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )

    parse = NativeBackend().parse_prd(prd, 1, tag="master")
    assert parse["ok"] is False
    assert parse["agent_action_required"]["op"] == "parse_prd"
    assert parse["agent_action_required"]["schema_hint"] == TASKS_SCHEMA_HINT

    expand = NativeBackend().expand(tag="master")
    assert expand["ok"] is False
    assert expand["agent_action_required"]["op"] == "expand"
    assert expand["agent_action_required"]["packets"]
    assert expand["agent_action_required"]["hint"] == (
        "run context-pack on the files a task touches before generating code"
    )

    rate = NativeBackend().rate(tag="master")
    assert rate["ok"] is False
    assert rate["agent_action_required"]["op"] == "rate"
    assert "scoring_rubric" in rate["agent_action_required"]


def _stub_handle(kind, provider="", role="main", model=None, reason="test"):
    from prd_taskmaster.provider_resolver import ProviderHandle
    return ProviderHandle(kind=kind, provider=provider, role=role, model=model, reason=reason)


def test_parse_prd_cli_kind_drives_cli_agent(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nREQ-001: Build native backend.")
    # Even if a key existed, cli kind must win — prove the resolver, not discover_key, decides.
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "anthropic", "key": "k"})
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, "prompt": prompt, **kwargs})
        return _valid_tasks(2)

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)
    # If the api path were taken this would blow up the test.
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    result = NativeBackend().parse_prd(prd, 2, tag="native-tag")

    assert result["ok"] is True
    assert result["task_count"] == 2
    assert result["backend"] == "native"
    assert result["ai"] == "cli"
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    assert cli_calls[0]["model"] is None  # plan-kind handle has model=None; contract must thread it through
    assert cli_calls[0]["schema_hint"] == TASKS_SCHEMA_HINT
    assert cli_calls[0]["op_class"] == "structured_gen"
    written = json.loads((tmp_path / ".taskmaster" / "tasks" / "tasks.json").read_text())
    assert [task["id"] for task in written["native-tag"]["tasks"]] == [1, 2]


def test_parse_prd_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().parse_prd(prd, 1, tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "parse_prd"
    assert result["agent_action_required"]["schema_hint"] == TASKS_SCHEMA_HINT


def test_parse_prd_cli_agent_error_falls_back_to_plan(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )

    def boom(provider, prompt, **kwargs):
        raise backend_mod.cli_agent.CliAgentError("spawn_refused", "nested claude refused")

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", boom)

    result = NativeBackend().parse_prd(prd, 1, tag="master")

    assert result["ok"] is False
    # CLI failure must demote to the plan floor, not hard-error.
    assert result["agent_action_required"]["op"] == "parse_prd"


def test_expand_cli_kind_drives_cli_agent_and_produces_graph(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    tasks_path = _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, **kwargs})
        return {
            "id": 1,
            "complexityScore": 8,
            "recommendedSubtasks": 2,
            "reasoning": "Needs careful backend integration.",
            "researchNotes": "Reuse parallel.apply_results for the merge.",
            "subtasks": [
                {"title": "Write expansion test", "description": "Cover merge.",
                 "details": "Assert once.", "dependencies": []},
                {"title": "Implement expansion", "description": "Apply packet.",
                 "details": "CLI path.", "dependencies": [1]},
            ],
        }

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is True
    assert result["applied"] == [1]
    assert result["failed"] == []
    assert result["ai"] == "cli"
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    merged = json.loads(tasks_path.read_text())
    titles = [s["title"] for s in merged["master"]["tasks"][0]["subtasks"]]
    assert titles == ["Write expansion test", "Implement expansion"]


def test_expand_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "expand"
    assert result["agent_action_required"]["packets"]


def test_expand_cli_kind_fans_out_in_parallel(tmp_path, monkeypatch):
    """Three packets must be in flight concurrently on the cli path."""
    import threading
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task(1), _pending_task(2), _pending_task(3)])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    # Force >=3 workers regardless of profile defaults.
    monkeypatch.setattr(backend_mod, "_native_concurrency", lambda n, c, p: max(n, 3))

    barrier = threading.Barrier(3, timeout=5)

    def fake_cli(provider, prompt, **kwargs):
        # If fan-out were serial, the 2nd/3rd never arrive and this times out.
        barrier.wait()
        tid = kwargs["task_id"]
        return {
            "id": tid,
            "complexityScore": 5,
            "recommendedSubtasks": 2,
            "reasoning": "parallel proof",
            "researchNotes": "n/a",
            "subtasks": [
                {"title": "a", "description": "x", "details": "y", "dependencies": []},
                {"title": "b", "description": "x", "details": "y", "dependencies": [1]},
            ],
        }

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is True
    assert sorted(result["applied"]) == [1, 2, 3]
    assert result["ai"] == "cli"


def _complexity_payload():
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


def test_rate_cli_kind_drives_cli_agent(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, **kwargs})
        return _complexity_payload()

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().rate(tag="master")

    assert result["ok"] is True
    assert result["ai"] == "cli"
    assert result["complexityAnalysis"][0]["taskId"] == 1
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    report = tmp_path / ".taskmaster" / "reports" / "task-complexity-report.json"
    assert report.is_file()


def test_rate_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().rate(tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "rate"
    assert "scoring_rubric" in result["agent_action_required"]
