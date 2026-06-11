#!/usr/bin/env python3
"""FastMCP server for prd-taskmaster.

Registers 20 tools wrapping the sibling modules (pipeline, capabilities,
taskmaster, validation, templates) plus server-native helpers
(calc_tasks, backup_prd, append_workflow, debrief, log_progress,
gen_test_tasks, read_state, gen_scripts, compute_fleet_waves).

No explicit process termination — mcp.run() is the event loop and
returns naturally when the transport closes.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Ensure the prd_taskmaster package (repo root) imports when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from prd_taskmaster import pipeline as P
from prd_taskmaster import validation as V
from prd_taskmaster import mode_recommend as C
from prd_taskmaster import taskmaster as TM
from prd_taskmaster import templates as TPL
from prd_taskmaster import lib as LIB
from prd_taskmaster import fleet as F
from prd_taskmaster import batch as B
from prd_taskmaster import license_activate as LA

mcp = FastMCP("prd-taskmaster")


# ─── Delegation tools (11) ────────────────────────────────────────────────────

@mcp.tool()
def preflight(cwd: str | None = None) -> dict:
    """Inspect project state and recommend the next pipeline action."""
    return P.preflight(cwd)


@mcp.tool()
def engine_preflight(configure: bool = True) -> dict:
    """One-call Phase 1: preflight + taskmaster + provider config/detect +
    capabilities, with a human-presentable summary. Prefer this over the
    individual probes."""
    return B.run_engine_preflight(configure=configure)


@mcp.tool()
def current_phase() -> dict:
    """Return the current pipeline phase plus completed-phase history."""
    return P.current_phase()


@mcp.tool()
def advance_phase(expected_current: str | None, target: str, evidence: dict) -> dict:
    """Atomic compare-and-swap phase transition with evidence attached."""
    return P.advance_phase(expected_current, target, evidence)


@mcp.tool()
def check_gate(phase: str, evidence: dict) -> dict:
    """Evaluate the gate rules for a phase against the supplied evidence."""
    return P.check_gate(phase, evidence)


@mcp.tool()
def detect_taskmaster() -> dict:
    """Detect taskmaster availability (MCP > CLI > none)."""
    return C.detect_taskmaster()


@mcp.tool()
def detect_capabilities() -> dict:
    """Scan for plugins, skills, and external AI tools; recommend a mode."""
    return C.detect_capabilities()


@mcp.tool()
def license_activate(key: str) -> dict:
    """Activate an Atlas Pro license key and return status plus resulting tier."""
    result = LA._activation_result(key)
    capabilities = C.detect_capabilities()
    return {
        **result,
        "tier": capabilities.get("tier", "free"),
        "license_status": capabilities.get("license_status"),
    }


@mcp.tool()
def validate_setup() -> dict:
    """Run the 6 Phase-0 SETUP checks and return per-check pass/fail."""
    return C.validate_setup()


@mcp.tool()
def init_taskmaster(method: str = "cli") -> dict:
    """Initialise TaskMaster in the current project via the CLI."""
    return TM.init_taskmaster(method)


@mcp.tool()
def validate_prd(input_path: str, ai: bool = False) -> dict:
    """Run the deterministic PRD quality checks and return a graded report."""
    return V.run_validate_prd(input_path)


@mcp.tool()
def load_template(type: str = "comprehensive") -> dict:
    """Load the named PRD template bundled with the plugin."""
    return TPL.run_load_template(type)


@mcp.tool()
def compute_fleet_waves(concurrency: int = 3, tag: str = "") -> dict:
    """Compute Atlas Fleet dependency waves for the selected TaskMaster tag."""
    return F.run_fleet_waves(concurrency, tag)


# ─── Server-native tools (8) ──────────────────────────────────────────────────

@mcp.tool()
def read_state() -> dict:
    """Alias for current_phase — read-only pipeline state snapshot."""
    return P.current_phase()


@mcp.tool()
def calc_tasks(
    requirements_count: int,
    team_size: int = 1,
    scope_phase: str = "greenfield",
    thematic_groups: int = 0,
) -> dict:
    """Recommend a task count from requirements, team, and scope phase."""
    base = max(8, requirements_count)
    if scope_phase == "final_phase":
        base = min(base, 12)
    if team_size > 1:
        base = min(base + (team_size - 1) * 2, 30)
    return {"ok": True, "recommended": base}


@mcp.tool()
def gen_test_tasks(total: int) -> dict:
    """Return a placeholder test-task projection (count only, no bodies)."""
    return {"ok": True, "count": total // 5, "tasks": []}


@mcp.tool()
def backup_prd(input_path: str) -> dict:
    """Copy a PRD to a timestamped prd-backup-YYYYMMDD-HHMMSS.md sibling."""
    src = Path(input_path)
    if not src.exists():
        return {"ok": False, "error": f"source missing: {input_path}"}
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = src.parent / f"prd-backup-{ts}.md"
    dst.write_text(src.read_text())
    return {"ok": True, "backup_path": str(dst)}


@mcp.tool()
def append_workflow(target: str, content_file: str, dry_run: bool = False) -> dict:
    """Append a plugin-managed workflow block (fenced by BEGIN/END markers)."""
    BEGIN = "<!-- BEGIN atlas-ai plugin workflow -->"
    END = "<!-- END atlas-ai plugin workflow -->"

    target_path = Path(target)
    content_path = Path(content_file)
    if not content_path.exists():
        return {"ok": False, "error": f"content_file missing: {content_file}"}
    payload = content_path.read_text()
    block = f"\n{BEGIN}\n{payload}\n{END}\n"

    if target_path.exists():
        existing = target_path.read_text()
        if BEGIN in existing and END in existing:
            return {"ok": True, "action": "skipped", "reason": "markers_present"}
        if dry_run:
            return {"ok": True, "action": "would_append"}
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = target_path.with_name(
            target_path.name + f".prd-taskmaster-backup-{ts}"
        )
        backup_path.write_text(existing)
        LIB.atomic_write(target_path, existing + block)
        return {"ok": True, "action": "appended", "backup_path": str(backup_path)}
    else:
        if dry_run:
            return {"ok": True, "action": "would_create"}
        LIB.atomic_write(target_path, block.lstrip())
        return {"ok": True, "action": "created"}


@mcp.tool()
def debrief(
    slug: str,
    grade: str = "",
    output_dir: str = "docs/v4-release",
    force: bool = False,
) -> dict:
    """Write a dogfood-debrief markdown stub under output_dir."""
    d = Path(output_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"dogfood-{slug}-{datetime.now().strftime('%Y%m%d')}.md"
    if out.exists() and not force:
        return {
            "ok": False,
            "error": "exists; pass force=true to overwrite",
            "path": str(out),
        }
    body = (
        f"# Dogfood Debrief: {slug}\n\n"
        f"- grade: {grade or 'unset'}\n"
        f"- generated: {datetime.now().isoformat()}\n\n"
        "## Notes\n\n"
        "(placeholder — fill in after run)\n"
    )
    out.write_text(body)
    return {"ok": True, "output_path": str(out)}


@mcp.tool()
def log_progress(task_id: str, title: str) -> dict:
    """Append an ISO-timestamped progress line to .atlas-ai/progress.md."""
    progress = Path(".atlas-ai") / "progress.md"
    progress.parent.mkdir(parents=True, exist_ok=True)
    line = f"- [{datetime.now().isoformat()}] task {task_id}: {title}\n"
    with progress.open("a") as f:
        f.write(line)
    return {"ok": True, "progress_file": str(progress)}


@mcp.tool()
def gen_scripts(output_dir: str = ".atlas-ai/scripts") -> dict:
    """Write stub scripts (ship-check.py, progress.sh, summary.py) if absent."""
    d = Path(output_dir)
    d.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name in ("ship-check.py", "progress.sh", "summary.py"):
        p = d / name
        if not p.exists():
            p.write_text(f"# {name} stub\n")
            created.append(str(p))
    return {"ok": True, "created": created}


if __name__ == "__main__":
    mcp.run()
