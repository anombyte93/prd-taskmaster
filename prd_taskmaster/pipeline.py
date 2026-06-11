"""
Pipeline state machine for the plugin. ATOMIC compare-and-swap transitions.
Phases: SETUP -> DISCOVER -> GENERATE -> HANDOFF -> EXECUTE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from prd_taskmaster.lib import atomic_write, locked_update, read_json, emit_json_error, now_iso

ATLAS_AI_DIR = Path(".atlas-ai")
STATE_DIR = ATLAS_AI_DIR / "state"
PIPELINE_FILE = STATE_DIR / "pipeline.json"
TASKMASTER_DIR = Path(".taskmaster")
TASKMASTER_STATE_FILE = TASKMASTER_DIR / "state.json"
TASKS_FILE = TASKMASTER_DIR / "tasks" / "tasks.json"
PRD_FILE = TASKMASTER_DIR / "docs" / "prd.md"

PHASES = ["SETUP", "DISCOVER", "GENERATE", "HANDOFF", "EXECUTE"]

LEGAL_TRANSITIONS = {
    None: ["SETUP"],
    "SETUP": ["DISCOVER"],
    "DISCOVER": ["GENERATE"],
    "GENERATE": ["HANDOFF"],
    "HANDOFF": ["EXECUTE"],
    "EXECUTE": [],
}


def _load_state() -> dict:
    if not PIPELINE_FILE.exists():
        return {"current_phase": None, "phases_completed": [], "phase_evidence": {}, "version": "5.0.0"}
    return read_json(PIPELINE_FILE)


def current_phase() -> dict:
    state = _load_state()
    return {
        "ok": True,
        "current_phase": state.get("current_phase"),
        "phases_completed": state.get("phases_completed", []),
        "phase_evidence": state.get("phase_evidence", {}),
    }


def advance_phase(expected_current: Optional[str], target: str, evidence: dict) -> dict:
    if target not in PHASES:
        return emit_json_error(f"unknown target phase: {target}", phases=PHASES)

    def transform(content: str) -> str:
        state = json.loads(content) if content.strip() else {"current_phase": None, "phases_completed": [], "phase_evidence": {}, "version": "5.0.0"}
        actual = state.get("current_phase")
        if actual != expected_current:
            raise _CASMiss(actual)
        if target not in LEGAL_TRANSITIONS.get(actual, []):
            raise _IllegalTransition(actual, target)
        state["current_phase"] = target
        completed = state.get("phases_completed", [])
        if expected_current and expected_current not in completed:
            completed.append(expected_current)
        state["phases_completed"] = completed
        state.setdefault("phase_evidence", {})[target] = {
            "entered_at": now_iso(),
            "from": expected_current,
            "evidence": evidence,
        }
        return json.dumps(state, indent=2, default=str)

    try:
        locked_update(PIPELINE_FILE, transform)
    except _CASMiss as e:
        return emit_json_error(
            f"stale expected_current: caller expected {expected_current}, actual is {e.actual}",
            expected=expected_current, actual=e.actual
        )
    except _IllegalTransition as e:
        return emit_json_error(
            f"illegal transition: {e.source} -> {e.target}",
            legal=LEGAL_TRANSITIONS.get(e.source, []),
        )

    return {"ok": True, "new_phase": target, "previous": expected_current}


def check_gate(phase: str, evidence: dict) -> dict:
    violations = []
    if phase == "SETUP":
        vs = evidence.get("validate_setup", {})
        if not vs.get("ready") or vs.get("critical_failures", 1) > 0:
            violations.append("validate_setup must report ready=true with 0 critical failures")
    elif phase == "DISCOVER":
        if not (evidence.get("user_approved") or (evidence.get("auto_classification") == "CLEAR" and evidence.get("assumptions_documented"))):
            violations.append("DISCOVER gate requires user_approved=true OR auto_classification=CLEAR with assumptions_documented=true")
    elif phase == "GENERATE":
        if evidence.get("validation_grade") not in ("EXCELLENT", "GOOD"):
            violations.append("validation_grade must be EXCELLENT or GOOD")
        if evidence.get("task_count", 0) == 0:
            violations.append("tasks must be parsed (task_count > 0)")
        if evidence.get("subtask_coverage", 0) < 1.0:
            violations.append("all tasks must have subtasks (coverage must be 1.0)")
    elif phase == "HANDOFF":
        if not evidence.get("user_mode_choice"):
            violations.append("user_mode_choice must be recorded (from AskUserQuestion)")
        if not evidence.get("plan_file_exists"):
            violations.append("writing-plans must have written the plan file")

    return {
        "ok": True,
        "gate_passed": len(violations) == 0,
        "violations": violations,
        "phase": phase,
    }


def _read_taskmaster_state() -> dict:
    if not TASKMASTER_STATE_FILE.exists():
        return {}
    try:
        return read_json(TASKMASTER_STATE_FILE)
    except Exception:
        return {}


def _read_taskmaster_tasks() -> dict:
    if not TASKS_FILE.exists():
        return {}
    try:
        tasks = read_json(TASKS_FILE)
        return tasks if isinstance(tasks, dict) else {}
    except Exception:
        return {}


def _tag_task_lists(tasks: dict) -> dict[str, list[dict]]:
    if isinstance(tasks.get("tasks"), list):
        return {"master": tasks["tasks"]}

    tags: dict[str, list[dict]] = {}
    for key, value in tasks.items():
        if isinstance(value, dict) and isinstance(value.get("tasks"), list):
            tags[key] = value["tasks"]
    return tags


def _count_tasks(items: list[dict]) -> dict[str, int]:
    total = len(items)
    done = sum(1 for item in items if item.get("status") == "done")
    return {
        "total": total,
        "pending": total - done,
        "done": done,
    }


def _current_tag(state: dict, tag_lists: dict[str, list[dict]]) -> str:
    configured = state.get("currentTag")
    if isinstance(configured, str) and configured:
        return configured
    if "master" in tag_lists:
        return "master"
    return next(iter(tag_lists), "master")


def _recommended_pending_tag(tag_counts: dict[str, dict[str, int]]) -> str | None:
    ready_tags = [
        (tag, counts)
        for tag, counts in tag_counts.items()
        if counts.get("pending", 0) > 0
    ]
    if not ready_tags:
        return None
    ready_tags.sort(key=lambda item: (item[0] != "master", item[0]))
    return ready_tags[0][0]


def preflight(cwd: Optional[str] = None) -> dict:
    if cwd:
        import os
        os.chdir(cwd)

    state = _load_state()
    cp = state.get("current_phase")

    prd_exists = PRD_FILE.exists()
    tm_state = _read_taskmaster_state()
    task_lists = _tag_task_lists(_read_taskmaster_tasks())
    tag_counts = {
        tag: _count_tasks(items)
        for tag, items in task_lists.items()
    }
    current_tag = _current_tag(tm_state, task_lists)
    current_counts = tag_counts.get(current_tag, {"total": 0, "pending": 0, "done": 0})
    tasks_count = current_counts["total"]
    pending_count = current_counts["pending"]
    recommended_tag = current_tag

    has_taskmaster = TASKMASTER_DIR.exists()
    alternate_pending_tag = _recommended_pending_tag(tag_counts)

    if has_taskmaster and pending_count > 0:
        rec = "resume_existing_tasks"
    elif prd_exists and tasks_count == 0:
        rec = "parse_prd"
    elif has_taskmaster and not prd_exists:
        rec = "generate_prd"
    elif not has_taskmaster:
        rec = "run_setup"
    elif alternate_pending_tag and alternate_pending_tag != current_tag:
        rec = "select_taskmaster_tag"
        recommended_tag = alternate_pending_tag
    elif tasks_count > 0 and pending_count == 0:
        rec = "complete"
    elif cp == "EXECUTE" and tasks_count > 0:
        rec = "resume"
    else:
        rec = "run_setup"

    return {
        "ok": True,
        "current_phase": cp,
        "prd_path": str(PRD_FILE) if prd_exists else None,
        "task_count": tasks_count,
        "pending_task_count": pending_count,
        "has_taskmaster": has_taskmaster,
        "taskmaster_root": str(TASKMASTER_DIR),
        "tasks_path": str(TASKS_FILE) if TASKS_FILE.exists() else None,
        "current_tag": current_tag,
        "recommended_tag": recommended_tag,
        "tag_counts": tag_counts,
        "recommended_action": rec,
    }


class _CASMiss(Exception):
    def __init__(self, actual): self.actual = actual

class _IllegalTransition(Exception):
    def __init__(self, source, target):
        self.source = source
        self.target = target
