#!/usr/bin/env python3
"""FastMCP server for prd-taskmaster.

Registers 31 tools wrapping the sibling modules (pipeline, capabilities,
taskmaster, backend, validation, templates) plus server-native helpers
(calc_tasks, backup_prd, append_workflow, debrief, log_progress,
gen_test_tasks, read_state, gen_scripts, compute_fleet_waves, context_pack,
feedback, suggestion).

No explicit process termination — mcp.run() is the event loop and
returns naturally when the transport closes.
"""
from __future__ import annotations

import functools
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Ensure the prd_taskmaster package (repo root) imports when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from prd_taskmaster import pipeline as P
from prd_taskmaster import validation as V
from prd_taskmaster import mode_recommend as C
from prd_taskmaster import templates as TPL
from prd_taskmaster import lib as LIB
from prd_taskmaster import fleet as F
from prd_taskmaster import batch as B
from prd_taskmaster import task_state as TS
from prd_taskmaster import cli as CLI
from prd_taskmaster import feedback as FB
from prd_taskmaster import suggestions as SG
from prd_taskmaster.context_pack import build_context_pack

_mcp = FastMCP("prd-taskmaster")


class _HardenedMCP:
    """Wraps FastMCP so a single tool can never crash the stdio transport.

    BUG3: an unhandled exception inside a tool body (e.g. ``backup_prd`` doing
    raw ``Path.read_text()`` on a directory / unreadable file / full disk)
    propagated out of the tool function and tore down the whole MCP process —
    the operator saw "MCP error -32000: Connection closed" and ALL tools
    vanished from the session at once. Tools must fail *closed* with a
    structured ``{"ok": False, "error": ...}`` payload, never by terminating
    the host. This wrapper installs that contract on every ``@mcp.tool()``
    uniformly, regardless of whether the individual body remembered to catch.
    """

    def __init__(self, inner: FastMCP) -> None:
        self._inner = inner

    def tool(self, *t_args, **t_kwargs):
        inner_decorator = self._inner.tool(*t_args, **t_kwargs)

        def decorator(fn):
            @functools.wraps(fn)
            def guarded(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except LIB.CommandError as exc:
                    return {"ok": False, "error": exc.message, **getattr(exc, "extra", {})}
                except SystemExit as exc:
                    # A backend op called sys.exit(); surface it, don't let it
                    # bubble up and stop mcp.run().
                    return {"ok": False, "error": "tool exited", "exit": exc.code}
                except BaseException as exc:  # noqa: BLE001 — fail closed, never crash the host
                    # Diagnostics go to stderr (captured by the MCP host log),
                    # never to stdout (which carries the JSON-RPC stream).
                    print(
                        f"[prd-taskmaster] tool {fn.__name__!r} raised "
                        f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "tool": fn.__name__,
                    }

            return inner_decorator(guarded)

        return decorator

    def __getattr__(self, name):
        return getattr(self._inner, name)


mcp = _HardenedMCP(_mcp)


# ─── Delegation tools (17) ────────────────────────────────────────────────────

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
def validate_setup() -> dict:
    """Run the 6 Phase-0 SETUP checks and return per-check pass/fail."""
    return C.validate_setup()


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


@mcp.tool()
def next_task(tag: str = "") -> dict:
    """Select the next TaskMaster-compatible task or subtask."""
    try:
        return TS.run_next_task(tag=tag or None)
    except LIB.CommandError as exc:
        return {"ok": False, "error": exc.message, **exc.extra}


@mcp.tool()
def claim_task(tag: str = "") -> dict:
    """Atomically select and mark the next task or subtask in-progress."""
    try:
        return TS.run_claim_task(tag=tag or None)
    except LIB.CommandError as exc:
        return {"ok": False, "error": exc.message, **exc.extra}


@mcp.tool()
def set_task_status(id: str, status: str, tag: str = "") -> dict:
    """Set a task or subtask status without terminating the MCP host."""
    try:
        return TS.run_set_status(id_str=id, status=status, tag=tag or None)
    except LIB.CommandError as exc:
        return {"ok": False, "error": exc.message, **exc.extra}


def _backend_tool_call(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except LIB.CommandError as exc:
        return {"ok": False, "error": exc.message, **exc.extra}
    except SystemExit as exc:
        return {"ok": False, "error": "backend operation exited", "exit": exc.code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def init_project() -> dict:
    """Initialise the resolved backend project state."""
    return _backend_tool_call(CLI.run_init_project)


@mcp.tool()
def parse_prd(prd_path: str, num_tasks: int, tag: str = "") -> dict:
    """Parse a PRD through the resolved backend.

    When the resolved native backend's ai_ops is "agent", this can return ok=false with
    agent_action_required instead of doing headless AI work.
    """
    return _backend_tool_call(CLI.run_parse_prd, prd_path, num_tasks, tag=tag or None)


@mcp.tool()
def expand_tasks(
    task_ids: list | None = None,
    research: bool = True,
    tag: str = "",
) -> dict:
    """Expand selected or all pending tasks through the resolved backend.

    When the resolved native backend's ai_ops is "agent", this can return ok=false with
    agent_action_required instead of doing headless AI work.
    """
    return _backend_tool_call(
        CLI.run_expand,
        task_ids=task_ids,
        research=research,
        tag=tag or None,
    )


@mcp.tool()
def rate_tasks(tag: str = "", research: bool = True) -> dict:
    """Rate task complexity through the resolved backend.

    When the resolved native backend's ai_ops is "agent", this can return ok=false with
    agent_action_required instead of doing headless AI work.
    """
    return _backend_tool_call(CLI.run_rate, tag=tag or None, research=research)


@mcp.tool()
def context_pack(files: list, include_private: bool = False) -> dict:
    """Extract AST-based Python signature context for files."""
    return build_context_pack(files, include_private=include_private)


# ─── Server-native tools (10) ─────────────────────────────────────────────────

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
    """Copy a PRD to a timestamped prd-backup-YYYYMMDD-HHMMSS.md sibling.

    Hardened (BUG3): the source may be a directory, unreadable, non-UTF-8, or
    the destination may be unwritable / on a full disk. Every such case returns
    a structured error instead of raising — a failed backup must not close the
    MCP transport.
    """
    src = Path(input_path)
    if not src.exists():
        return {"ok": False, "error": f"source missing: {input_path}"}
    if not src.is_file():
        return {"ok": False, "error": f"source is not a file: {input_path}"}
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = src.parent / f"prd-backup-{ts}.md"
    try:
        # Binary copy: tolerates non-UTF-8 PRDs that read_text() would choke on.
        dst.write_bytes(src.read_bytes())
    except OSError as exc:
        return {"ok": False, "error": f"backup failed: {exc}", "source": str(src)}
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
def feedback_submit(
    rating: int,
    agent: str,
    harness: str,
    what_went_well: str = "",
    what_failed: str = "",
    suggestions: str = "",
    task_ref: str = "",
) -> dict:
    """Append one Atlas agent feedback row to .atlas-ai/feedback.jsonl."""
    return FB.append_feedback({
        "rating": rating,
        "agent": agent,
        "harness": harness,
        "what_went_well": what_went_well,
        "what_failed": what_failed,
        "suggestions": suggestions,
        "task_ref": task_ref,
    })


@mcp.tool()
def feedback_report() -> dict:
    """Summarize .atlas-ai/feedback.jsonl."""
    return FB.summarize_feedback()


@mcp.tool()
def suggestion(
    text: str,
    context: str = "",
    source_repo: str = "",
    session: str = "",
    agent: str = "",
) -> dict:
    """Capture a free-text improvement suggestion about using the Atlas engine.

    Appends a row to the suggestions log (``.atlas-ai/suggestions.jsonl`` by
    default, or ``ATLAS_SUGGESTIONS_PATH`` if set — point it at a shared file to
    unify with the launcher's suggestion log). For dogfooding pain points,
    missing tools, and rough edges so they are durably recorded, not lost in a
    transcript. Use ``feedback_submit`` instead for structured 1-5 ratings.
    """
    return SG.append_suggestion({
        "text": text,
        "context": context,
        "source_repo": source_repo,
        "session": session,
        "agent": agent,
    })


@mcp.tool()
def suggestion_report() -> dict:
    """Summarize the suggestions log (counts, by-repo, last 5)."""
    return SG.summarize_suggestions()


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


@mcp.tool()
def render_status(phase: str = "", fmt: str = "boxed") -> dict:
    """Render Atlas progress panels (phase tracker, validation scorecard,
    ship-check gates, ...) from real pipeline state. fmt: boxed|ascii|json.
    The human-readable panel text is in the `rendered` field."""
    from prd_taskmaster.status import run_render_status
    try:
        return run_render_status(phase=phase or None, fmt=fmt)
    except LIB.CommandError as exc:
        return {"ok": False, "error": exc.message, **exc.extra}


if __name__ == "__main__":
    mcp.run()
