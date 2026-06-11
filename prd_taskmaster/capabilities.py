"""Capability detection command."""

import argparse
from pathlib import Path

from prd_taskmaster.lib import (
    CommandError,
    emit,
    fail,
    _detect_taskmaster_method,
)


def run_detect_capabilities() -> dict:
    """Scan for available skills, tools, and plugins that enable execution modes."""
    capabilities = {}

    # Check superpowers plugin
    superpowers_paths = [
        Path.home() / ".claude" / "plugins" / "cache" / "claude-plugins-official" / "superpowers",
        Path.home() / ".claude" / "plugins" / "superpowers",
    ]
    capabilities["superpowers"] = any(p.is_dir() for p in superpowers_paths)

    # Check specific skills
    skills_dir = Path.home() / ".claude" / "skills"
    for skill_name in ["cdd", "ralph-loop", "atlas-user-test", "expand-tasks", "phase-executor", "org-tree"]:
        skill_path = skills_dir / skill_name / "SKILL.md"
        capabilities[skill_name] = skill_path.is_file()

    # Check TaskMaster
    tm = _detect_taskmaster_method()
    capabilities["taskmaster-mcp"] = tm["method"] == "mcp"
    capabilities["taskmaster-cli"] = tm["method"] in ("mcp", "cli")

    # Determine recommended mode
    if capabilities["superpowers"]:
        recommended = "A"
        reason = "Superpowers plugin detected — full AI-assisted pipeline available"
    elif capabilities["taskmaster-cli"]:
        recommended = "B"
        reason = "TaskMaster CLI available — native auto-execute"
    else:
        recommended = "C"
        reason = "Manual control — universal fallback"

    return {
        "ok": True,
        "capabilities": capabilities,
        "recommended_mode": recommended,
        "recommended_reason": reason,
    }


def cmd_detect_capabilities(args: argparse.Namespace) -> None:
    try:
        emit(run_detect_capabilities())
    except CommandError as e:
        fail(e.message, **e.extra)
