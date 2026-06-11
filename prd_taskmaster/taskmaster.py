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

    # try full flag set, fall back if older taskmaster
    attempts = [
        [cli, "init", "--yes", "--store-tasks-in-git", "--rules=claude"],
        [cli, "init", "--yes"],
    ]
    last_error = None
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60, cwd=project_root)
            if r.returncode == 0:
                return {"ok": True, "project_root": str(project_root), "cmd": " ".join(cmd)}
            last_error = r.stderr
        except Exception as e:
            last_error = str(e)
    return emit_json_error(f"task-master init failed: {last_error}", project_root=str(project_root))


def detect_taskmaster_method() -> str:
    """cli if binary found, mcp if MCP available, none otherwise."""
    # For v5.0 we only detect CLI presence; MCP probing is a future enhancement.
    if _find_binary():
        return "cli"
    return "none"
