"""Thin wrapper around script.py subcommands.

script.py's cmd_* functions call sys.exit() via emit()/fail(), so we cannot
import and call them directly without risking process termination. Instead,
we spawn script.py as a subprocess and parse its JSON stdout. This preserves
the "every subcommand outputs JSON on stdout" contract documented in CLAUDE.md
and keeps the MCP server truly thin (no duplicated logic).

If script.py is ever refactored so that cmd_* functions return dicts instead
of calling emit(), this module can be rewritten to import them directly with
no change to the MCP server's public tool surface.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PY = SKILL_ROOT / "script.py"


class ScriptError(RuntimeError):
    """Raised when script.py returns non-zero or invalid JSON."""

    def __init__(self, message: str, payload: dict | None = None, stderr: str = ""):
        super().__init__(message)
        self.payload = payload or {}
        self.stderr = stderr


def run_script(
    subcommand: str,
    *,
    args: list[str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Invoke script.py <subcommand> [args] and return parsed JSON.

    Parameters
    ----------
    subcommand : str
        The script.py subcommand to run (e.g. "preflight", "validate-prd").
    args : list[str], optional
        Additional CLI flags to pass after the subcommand.
    cwd : path-like, optional
        Working directory for the subprocess. Many subcommands (preflight,
        read-state, log-progress, init-taskmaster, gen-scripts, backup-prd)
        operate relative to the CWD, so callers should pass the project root.
    timeout : float
        Subprocess timeout in seconds.

    Returns
    -------
    dict
        Parsed JSON from script.py's stdout.

    Raises
    ------
    ScriptError
        If the script exits non-zero, emits invalid JSON, or times out.
    """
    if not SCRIPT_PY.is_file():
        raise ScriptError(f"script.py not found at {SCRIPT_PY}")

    cmd = ["python3", str(SCRIPT_PY), subcommand]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ScriptError(f"script.py {subcommand} timed out after {timeout}s", stderr=str(e)) from e

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # script.py always emits JSON on stdout (both success and failure paths).
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as e:
        raise ScriptError(
            f"script.py {subcommand} emitted invalid JSON: {e}",
            stderr=stderr,
        ) from e

    if result.returncode != 0:
        # fail() sets ok=False and exits 1. Surface it cleanly.
        raise ScriptError(
            payload.get("error", f"script.py {subcommand} exited {result.returncode}"),
            payload=payload,
            stderr=stderr,
        )

    return payload
