from prd_taskmaster.taskmaster import init_taskmaster, _build_env


def test_build_env_sets_project_root():
    env = _build_env()
    assert "TASK_MASTER_PROJECT_ROOT" not in env


def test_init_taskmaster_graceful_on_missing_binary(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    result = init_taskmaster()
    assert result["ok"] is False
    assert "not found" in result["error"].lower() or "task-master" in result["error"].lower()
