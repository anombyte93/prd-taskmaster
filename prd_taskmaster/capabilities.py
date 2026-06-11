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

    # Determine recommended mode — same decision logic as the handoff skill:
    # superpowers + loop runner -> Verified Loop (C); superpowers only ->
    # Plan & Drive (A); taskmaster only -> Auto-Execute (B); fallback -> A.
    if capabilities["superpowers"] and capabilities["ralph-loop"]:
        recommended = "C"
        reason = "Verified Loop — superpowers + ralph-loop detected (evidence-gated execution)"
    elif capabilities["superpowers"]:
        recommended = "A"
        reason = "Plan & Drive — superpowers detected, no loop runner installed"
    elif capabilities["taskmaster-cli"]:
        recommended = "B"
        reason = "Auto-Execute — TaskMaster CLI available, native loop"
    else:
        recommended = "A"
        reason = "Plan & Drive — universal fallback, no execution tooling detected"

    # Tier: "premium" requires a licensed atlas-launcher (detection ships with
    # Atlas Fleet / Phase B); until then the standalone skill is always free.
    tier = "free"

    return {
        "ok": True,
        "tier": tier,
        "capabilities": capabilities,
        "recommended_mode": recommended,
        "recommended_reason": reason,
    }


def cmd_detect_capabilities(args: argparse.Namespace) -> None:
    try:
        emit(run_detect_capabilities())
    except CommandError as e:
        fail(e.message, **e.extra)
