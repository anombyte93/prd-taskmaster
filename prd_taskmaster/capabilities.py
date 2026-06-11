"""Capability detection command."""

import argparse
from pathlib import Path

from prd_taskmaster.lib import (
    CommandError,
    emit,
    fail,
    _detect_taskmaster_method,
)
from prd_taskmaster import license
from prd_taskmaster.mode_recommend import ATLAS_FLEET_REASON, detect_atlas_launcher


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

    atlas_launcher = detect_atlas_launcher()
    license_status = license.get_status()
    try:
        saved_license = license.load_license()
        if saved_license is not None and license.should_refresh(saved_license):
            license.refresh_if_needed()
            license_status = license.get_status()
    except Exception:
        pass
    has_atlas_launcher_premium = (
        atlas_launcher["mcp_registered"]
        and license_status["status"] in {"active", "grace"}
    )

    # Determine recommended mode — same decision logic as the handoff skill:
    # atlas-launcher MCP -> Atlas Fleet (D); superpowers + loop runner ->
    # Verified Loop (C); superpowers only -> Plan & Drive (A);
    # taskmaster only -> Auto-Execute (B); fallback -> A.
    if has_atlas_launcher_premium:
        recommended = "D"
        reason = ATLAS_FLEET_REASON
    elif capabilities["superpowers"] and capabilities["ralph-loop"]:
        recommended = "C"
        reason = "Verified Loop — superpowers + loop runner detected (evidence-gated execution)"
    elif capabilities["superpowers"]:
        recommended = "A"
        reason = "Plan & Drive — superpowers detected, no loop runner installed"
    elif capabilities["taskmaster-cli"]:
        recommended = "B"
        reason = "Auto-Execute — TaskMaster CLI available, native loop"
    else:
        recommended = "A"
        reason = "Plan & Drive — universal fallback, no execution tooling detected"

    tier = "premium" if has_atlas_launcher_premium else "free"

    return {
        "ok": True,
        "tier": tier,
        "license_status": license_status,
        "capabilities": capabilities,
        "recommended_mode": recommended,
        "recommended_reason": reason,
    }


def cmd_detect_capabilities(args: argparse.Namespace) -> None:
    try:
        emit(run_detect_capabilities())
    except CommandError as e:
        fail(e.message, **e.extra)
