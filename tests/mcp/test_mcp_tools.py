"""MCP tool contract tests — the merged server.py registers 18 tools.

Retargeted from the plugin: server.py now imports from prd_taskmaster.* and
lives at mcp-server/server.py. We add the repo root (so `prd_taskmaster` is
importable) and mcp-server/ (so `import server` works) to sys.path.
"""
import sys
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


def test_server_registers_18_tools():
    """Verify server.py declares all 18 expected tool functions at module scope."""
    import server as S
    expected = {
        "preflight", "current_phase", "advance_phase", "check_gate",
        "detect_taskmaster", "init_taskmaster", "validate_setup",
        "detect_capabilities", "load_template", "validate_prd",
        "calc_tasks", "gen_test_tasks", "backup_prd", "append_workflow",
        "debrief", "log_progress", "read_state", "gen_scripts",
    }
    assert len(expected) == 18
    public_attrs = {name for name in dir(S) if not name.startswith("_")}
    missing = expected - public_attrs
    assert not missing, f"missing tools: {sorted(missing)}"
