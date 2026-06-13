"""Assemble Atlas progress panels from real on-disk state.

`run_render_status` is a pure reader: it reads .atlas-ai/state/pipeline.json,
.atlas-ai/state/validation.json (persisted by validate-prd), the TaskMaster
tasks.json, and a dry-run ship-check, then renders the panel(s) for the current
(or a requested) phase via the pure functions in `render.py`.
"""

from __future__ import annotations

from prd_taskmaster import pipeline, render, shipcheck
from prd_taskmaster.lib import read_json
from prd_taskmaster.pipeline import (
    PIPELINE_FILE,
    STATE_DIR,
    _count_tasks,
    _current_tag,
    _read_taskmaster_state,
    _read_taskmaster_tasks,
    _tag_task_lists,
)

VALIDATION_FILE = STATE_DIR / "validation.json"


def _subtask_count(items: list[dict]) -> int:
    return sum(len(t.get("subtasks", []) or []) for t in items)


def _task_counts() -> dict | None:
    tasks = _read_taskmaster_tasks()
    if not tasks:
        return None
    tag_lists = _tag_task_lists(tasks)
    if not tag_lists:
        return None
    tag = _current_tag(_read_taskmaster_state(), tag_lists)
    items = tag_lists.get(tag, next(iter(tag_lists.values()), []))
    counts = _count_tasks(items)
    counts["subtasks"] = _subtask_count(items)
    counts["tag"] = tag
    return counts


def _validation() -> dict | None:
    data = read_json(VALIDATION_FILE)
    return data or None


def run_render_status(phase: str | None = None, fmt: str = "boxed", show_all: bool = False) -> dict:
    """Render the progress panel(s) for the current (or requested) phase.

    fmt: "boxed" (unicode), "ascii" (bracket fallbacks), or "json" (structured only).
    """
    ascii_mode = fmt == "ascii" or render._ascii_mode()
    state = read_json(PIPELINE_FILE) or {"current_phase": None, "phases_completed": []}
    cur = (phase or state.get("current_phase") or "").upper() or None
    counts = _task_counts()
    validation = _validation()

    panels: dict[str, str] = {}
    panels["tracker"] = render.phase_tracker(state, ascii_mode=ascii_mode)
    panels["oneline"] = render.oneline_summary(validation, counts, ascii_mode=ascii_mode)

    if show_all or cur in (None, "SETUP"):
        try:
            pf = pipeline.preflight()
        except Exception:
            pf = {"ok": bool(state.get("current_phase")), "has_taskmaster": None, "backend": None}
        panels["preflight"] = render.preflight_panel(pf, ascii_mode=ascii_mode)
    if show_all or cur in ("GENERATE", "HANDOFF", "EXECUTE"):
        panels["generate"] = render.validation_scorecard(validation, counts, ascii_mode=ascii_mode)
    if show_all or cur == "HANDOFF":
        panels["handoff"] = render.handoff_panel(validation, counts, ascii_mode=ascii_mode)
    if show_all or cur == "EXECUTE":
        panels["execute"] = render.execute_panel(counts or {"total": 0, "done": 0}, ascii_mode=ascii_mode)
        try:
            sc = shipcheck.run_ship_check(dry_run=True)
        except Exception as exc:  # never let a status render crash
            sc = {"passed": False, "failures": [str(exc)]}
        panels["shipcheck"] = render.shipcheck_panel(sc, ascii_mode=ascii_mode)

    # Choose what to show as the primary rendered output.
    if show_all:
        order = ["tracker", "preflight", "generate", "handoff", "execute", "shipcheck"]
        body = "\n\n".join(panels[k] for k in order if k in panels)
    else:
        primary = {
            None: "preflight", "SETUP": "preflight", "DISCOVER": "tracker",
            "GENERATE": "generate", "HANDOFF": "handoff", "EXECUTE": "execute",
        }.get(cur, "tracker")
        body = panels.get(primary, panels["tracker"])
        body = panels["tracker"] + "\n\n" + body if primary != "tracker" else body

    rendered = panels["oneline"] + "\n\n" + body
    return {
        "ok": True,
        "phase": cur,
        "format": fmt,
        "rendered": rendered,
        "panels": panels,
    }
