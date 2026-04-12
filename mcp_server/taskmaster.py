"""Thin wrapper around the `task-master` CLI (v0.43.1).

This module is deliberately separate from `lib.py`: that module wraps
`script.py` (the skill's deterministic Python subcommands), while this one
wraps the external `task-master` binary. Mixing them would muddy the split
between skill-owned logic and TaskMaster-native operations.

All helpers funnel through :func:`run_taskmaster`, which handles:
- Missing binary detection (returns a structured error with an install hint)
- stdout/stderr capture and JSON parsing (falls back to raw text)
- Normalized result dict: ``{"ok": bool, "stdout": str, "stderr": str, ...}``

Every MCP wrapper in ``server.py`` should stay under ~15 lines by delegating
argument assembly here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

TASK_MASTER_BIN = "task-master"
DEFAULT_TIMEOUT = 600.0  # parse-prd / analyze-complexity / expand can be slow


def _binary_missing() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "task-master CLI not found",
        "install_hint": "npm install -g task-master-ai",
    }


def run_taskmaster(
    *args: str,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    parse_json: bool = True,
) -> dict[str, Any]:
    """Invoke ``task-master`` with the given arguments.

    Parameters
    ----------
    *args : str
        Positional CLI args appended after the ``task-master`` binary.
    cwd : path-like, optional
        Working directory. Most subcommands read/write ``.taskmaster/`` in cwd.
    timeout : float
        Subprocess timeout in seconds.
    parse_json : bool
        If True, attempt to parse stdout as JSON and return it under the
        ``"json"`` key alongside the raw stdout. If parsing fails, only
        ``stdout`` is populated.

    Returns
    -------
    dict
        ``{"ok": bool, "returncode": int, "stdout": str, "stderr": str,
        "json": Any | None}`` on success, or a structured error dict on
        failure (missing binary, non-zero exit, timeout).
    """
    if shutil.which(TASK_MASTER_BIN) is None:
        return _binary_missing()

    cmd = [TASK_MASTER_BIN, *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "error": f"task-master {' '.join(args)} timed out after {timeout}s",
            "stderr": str(e),
        }

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    parsed: Any = None
    if parse_json and stdout.strip():
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "json": parsed,
    }


# ─── Helpers specific to `models` output parsing ─────────────────────────────

# `task-master models` emits a human-formatted table (boxes + colour codes), not
# JSON. We extract the three "Active <role> Model" rows by regex-stripping ANSI
# and matching the leading "Main:" / "Research:" / "Fallback:" labels that
# TaskMaster uses as row headers.

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_models_output(stdout: str) -> dict[str, Any]:
    """Best-effort extraction of active model rows from `task-master models` output.

    Returns a dict with keys ``main``, ``research``, ``fallback`` — each is
    either a dict like ``{"provider": ..., "model_id": ..., "line": ...}`` or
    None if that row could not be identified. The full de-ANSI'd text is also
    returned under ``raw_clean`` for debugging.
    """
    clean = _ANSI_RE.sub("", stdout)
    roles: dict[str, Any] = {"main": None, "research": None, "fallback": None}

    # TaskMaster prints rows like:
    #   │ Main           │ anthropic      │ claude-sonnet-4-5  │ ...
    # After ANSI strip we can split on │ and match the role label in col 1.
    for line in clean.splitlines():
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if len(parts) < 3:
            continue
        label = parts[0].lower()
        for role in ("main", "research", "fallback"):
            if label == role or label.startswith(f"{role} "):
                roles[role] = {
                    "provider": parts[1] if len(parts) > 1 else None,
                    "model_id": parts[2] if len(parts) > 2 else None,
                    "line": line.strip(),
                }
                break

    return {"roles": roles, "raw_clean": clean}
