"""TaskMaster CLI wrapper for standard .taskmaster projects."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from prd_taskmaster.lib import emit_json_error


def _build_env() -> dict:
    """Return the subprocess environment without overriding TaskMaster's project detection."""
    env = os.environ.copy()
    env.pop("TASK_MASTER_PROJECT_ROOT", None)
    return env


def _find_binary() -> str | None:
    return shutil.which("task-master") or shutil.which("task-master-ai") or shutil.which("taskmaster")


def init_taskmaster(method: str = "cli") -> dict:
    cli = _find_binary()
    if not cli:
        return emit_json_error(
            "task-master binary not found in PATH",
            install_cmd="npm install -g task-master-ai",
            searched=["task-master", "task-master-ai", "taskmaster"],
        )

    project_root = Path.cwd()
    env = _build_env()

    # DETECT-FIRST (FR-6): task-master init overwrites an existing .mcp.json with
    # its own template (placeholder API keys), destroying e.g. a plugin's server
    # registration. Snapshot it and restore verbatim if init clobbers it.
    mcp_json = project_root / ".mcp.json"
    mcp_before = mcp_json.read_text() if mcp_json.is_file() else None

    # try full flag set, fall back if older taskmaster
    attempts = [
        [cli, "init", "--yes", "--store-tasks-in-git", "--rules=claude"],
        [cli, "init", "--yes"],
    ]
    last_error = None
    result = None
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60, cwd=project_root)
            if r.returncode == 0:
                result = {"ok": True, "project_root": str(project_root), "cmd": " ".join(cmd)}
                break
            last_error = r.stderr
        except Exception as e:
            last_error = str(e)

    mcp_protected = False
    if mcp_before is not None and mcp_json.is_file() and mcp_json.read_text() != mcp_before:
        mcp_json.write_text(mcp_before)
        mcp_protected = True

    if result is None:
        return emit_json_error(f"task-master init failed: {last_error}", project_root=str(project_root))

    result["mcp_json_protected"] = mcp_protected
    if mcp_protected:
        result["note"] = (
            ".mcp.json was restored to its pre-init contents (task-master init had "
            "overwritten it). Add TaskMaster's MCP server manually if you want it."
        )
    return result


def cmd_init_taskmaster(args) -> None:
    """CLI wrapper: protected task-master init (preserves an existing .mcp.json)."""
    from prd_taskmaster.lib import emit, fail

    result = init_taskmaster()
    if result.get("ok"):
        emit(result)
    else:
        fail(result.get("error", "task-master init failed"),
             **{k: v for k, v in result.items() if k not in ("ok", "error")})


def detect_taskmaster_method() -> str:
    """cli if binary found, mcp if MCP available, none otherwise."""
    # For v5.0 we only detect CLI presence; MCP probing is a future enhancement.
    if _find_binary():
        return "cli"
    return "none"
