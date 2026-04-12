#!/usr/bin/env python3
"""prd-taskmaster-mcp — FastMCP server exposing script.py subcommands as tools.

Each tool is a thin wrapper over `python3 script.py <subcommand>` that returns
the parsed JSON dict directly. See mcp_server/lib.py for the subprocess shim
and CLAUDE.md for the architectural rationale (script.py owns determinism,
SKILL.md owns judgment, this server simply makes the deterministic layer
available as first-class MCP tools).

Register in ~/.claude.json or ~/.claude/settings/mcp.json:

    {
      "mcpServers": {
        "prd-taskmaster": {
          "command": "python3",
          "args": ["/absolute/path/to/mcp_server/server.py"]
        }
      }
    }

Every tool accepts an optional `cwd` parameter so that callers can target a
specific project directory. If omitted, the current working directory is used
(which is what script.py's relative-path subcommands expect).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from mcp_server.lib import ScriptError, run_script

mcp = FastMCP("prd-taskmaster")


def _invoke(subcommand: str, *, args: list[str] | None = None, cwd: str | None = None) -> dict[str, Any]:
    """Run a script.py subcommand and return the parsed JSON or a structured error dict."""
    try:
        return run_script(subcommand, args=args, cwd=cwd)
    except ScriptError as e:
        return {
            "ok": False,
            "error": str(e),
            "subcommand": subcommand,
            "stderr": e.stderr,
            "payload": e.payload,
        }


# ─── Environment detection ────────────────────────────────────────────────────


@mcp.tool()
def preflight(cwd: str | None = None) -> dict[str, Any]:
    """Detect environment state: .taskmaster dir, PRD file, task counts, taskmaster method, crash state.

    Runs `script.py preflight` in the given working directory (or current CWD).
    Returns the full preflight payload as documented in SKILL.md's Phase 1.
    """
    return _invoke("preflight", cwd=cwd)


@mcp.tool()
def detect_taskmaster(cwd: str | None = None) -> dict[str, Any]:
    """Detect which TaskMaster interface is available: MCP > CLI > none."""
    return _invoke("detect-taskmaster", cwd=cwd)


@mcp.tool()
def detect_capabilities(cwd: str | None = None) -> dict[str, Any]:
    """Scan for available skills, tools, and plugins that affect HANDOFF recommendations."""
    return _invoke("detect-capabilities", cwd=cwd)


# ─── PRD lifecycle ────────────────────────────────────────────────────────────


@mcp.tool()
def load_template(type: Literal["comprehensive", "minimal"]) -> dict[str, Any]:
    """Load a PRD template by type. Returns the full template text."""
    return _invoke("load-template", args=["--type", type])


@mcp.tool()
def validate_prd(input_path: str, cwd: str | None = None) -> dict[str, Any]:
    """Run the 13-check quality validation on a PRD file (placeholders, vague terms, required sections)."""
    return _invoke("validate-prd", args=["--input", input_path], cwd=cwd)


@mcp.tool()
def backup_prd(input_path: str, cwd: str | None = None) -> dict[str, Any]:
    """Create a timestamped backup copy of a PRD file."""
    return _invoke("backup-prd", args=["--input", input_path], cwd=cwd)


# ─── Task planning ────────────────────────────────────────────────────────────


@mcp.tool()
def calc_tasks(requirements_count: int) -> dict[str, Any]:
    """Calculate the recommended number of TaskMaster tasks for a given REQ count."""
    return _invoke("calc-tasks", args=["--requirements", str(requirements_count)])


@mcp.tool()
def gen_test_tasks(total: int) -> dict[str, Any]:
    """Generate USER-TEST task specs spaced across `total` implementation tasks."""
    return _invoke("gen-test-tasks", args=["--total", str(total)])


@mcp.tool()
def gen_scripts(output_dir: str, cwd: str | None = None) -> dict[str, Any]:
    """Create the five tracking scripts (progress, checkpoint, status, etc.) in the given directory."""
    return _invoke("gen-scripts", args=["--output-dir", output_dir], cwd=cwd)


# ─── Execution state ──────────────────────────────────────────────────────────


@mcp.tool()
def read_state(cwd: str | None = None) -> dict[str, Any]:
    """Read the crash-recovery execution state from .taskmaster/state/execution-state.json."""
    return _invoke("read-state", cwd=cwd)


@mcp.tool()
def log_progress(
    task_id: str,
    title: str,
    duration: str | None = None,
    subtasks: str | None = None,
    tests: str | None = None,
    issues: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Append a progress entry for a completed task to .taskmaster/notes/progress.md."""
    args = ["--task-id", task_id, "--title", title]
    if duration is not None:
        args.extend(["--duration", duration])
    if subtasks is not None:
        args.extend(["--subtasks", subtasks])
    if tests is not None:
        args.extend(["--tests", tests])
    if issues is not None:
        args.extend(["--issues", issues])
    return _invoke("log-progress", args=args, cwd=cwd)


@mcp.tool()
def init_taskmaster(method: Literal["cli", "mcp"], cwd: str | None = None) -> dict[str, Any]:
    """Initialize a TaskMaster project using the given method (CLI or MCP)."""
    return _invoke("init-taskmaster", args=["--method", method], cwd=cwd)


def main() -> None:
    """Entry point for `python3 -m mcp_server.server` or direct execution."""
    mcp.run()


if __name__ == "__main__":
    main()
