"""MCP tool contract tests — the merged server.py registers 21 tools.

Retargeted from the plugin: server.py now imports from prd_taskmaster.* and
lives at mcp-server/server.py. We add the repo root (so `prd_taskmaster` is
importable) and mcp-server/ (so `import server` works) to sys.path.
"""
import sys
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))


def test_load_template_comprehensive():
    import server as S
    r = S.load_template("comprehensive")
    assert r["ok"] is True
    assert len(r["content"]) > 100
    assert "{{" in r["content"] or "[" in r["content"]  # template has placeholders


def test_load_template_minimal():
    import server as S
    r = S.load_template("minimal")
    assert r["ok"] is True
    assert len(r["content"]) > 10


def test_load_template_unknown_type_raises():
    """LIVE contract: the package's run_load_template raises CommandError on an
    unknown type (the plugin returned an ok=False dict). The server wrapper
    does not catch it, so the call propagates the raise."""
    import server as S
    from prd_taskmaster.lib import CommandError
    with pytest.raises(CommandError) as exc:
        S.load_template("bogus")
    assert "not found" in str(exc.value).lower()


def test_compute_fleet_waves_tool(tmp_path, monkeypatch):
    import server as S
    tasks_dir = tmp_path / ".taskmaster" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "tasks.json").write_text(json.dumps({
        "alpha": {
            "tasks": [
                {"id": 1, "status": "pending", "dependencies": []},
                {"id": 2, "status": "pending", "dependencies": []},
                {"id": 3, "status": "pending", "dependencies": [1, 2]},
            ]
        }
    }))
    monkeypatch.chdir(tmp_path)

    r = S.compute_fleet_waves(concurrency=2, tag="alpha")

    expected = {
        "ok": True,
        "tag": "alpha",
        "waves": [[1, 2], [3]],
        "blocked": [],
        "deadlocked": False,
        "ready": [1, 2],
        "concurrency": 2,
    }
    assert expected.items() <= r.items()
    assert set(r["routing"]) == {"1", "2", "3"} and "backends" in r


def test_server_registers_21_tools():
    """Verify server.py declares all 21 expected tool functions at module scope."""
    import server as S
    expected = {
        "preflight", "current_phase", "advance_phase", "check_gate",
        "detect_taskmaster", "init_taskmaster", "validate_setup",
        "detect_capabilities", "load_template", "validate_prd",
        "calc_tasks", "gen_test_tasks", "backup_prd", "append_workflow",
        "debrief", "log_progress", "read_state", "gen_scripts",
        "compute_fleet_waves",
        "engine_preflight",
        "tm_parallel_expand",
    }
    assert len(expected) == 21
    public_attrs = {name for name in dir(S) if not name.startswith("_")}
    missing = expected - public_attrs
    assert not missing, f"missing tools: {sorted(missing)}"
