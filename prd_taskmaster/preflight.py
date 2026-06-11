"""Environment / taskmaster detection commands."""

import argparse
import json
from pathlib import Path

from prd_taskmaster.lib import (
    TASKMASTER_DIR,
    TASKMASTER_DOCS,
    TASKMASTER_TASKS,
    CommandError,
    emit,
    fail,
    _detect_taskmaster_method,
    _read_execution_state,
    _resolve_tasks_payload,
)


def run_preflight() -> dict:
    """Detect environment: .taskmaster, PRD, task count, taskmaster method, CLAUDE.md, crash state."""
    has_taskmaster = TASKMASTER_DIR.is_dir()
    prd_path = None
    task_count = 0
    tasks_completed = 0
    tasks_pending = 0

    if has_taskmaster:
        # Find PRD
        for candidate in [TASKMASTER_DOCS / "prd.md", TASKMASTER_DOCS / "prd.txt"]:
            if candidate.is_file():
                prd_path = str(candidate)
                break
        if not prd_path:
            # Glob for any .md in docs
            docs = list(TASKMASTER_DOCS.glob("*.md")) if TASKMASTER_DOCS.is_dir() else []
            if docs:
                prd_path = str(docs[0])

        # Count tasks
        tasks_json = TASKMASTER_TASKS / "tasks.json"
        if tasks_json.is_file():
            try:
                with open(tasks_json) as f:
                    data = json.load(f)
                tasks, _ = _resolve_tasks_payload(data)
                if isinstance(tasks, list):
                    task_count = len(tasks)
                    tasks_completed = sum(1 for t in tasks if t.get("status") == "done")
                    tasks_pending = task_count - tasks_completed
            except (json.JSONDecodeError, KeyError):
                pass

    # Detect taskmaster method
    tm_method = _detect_taskmaster_method()

    # Check CLAUDE.md
    has_claude_md = Path("CLAUDE.md").is_file()

    # Check crash state
    crash_state = _read_execution_state()

    return {
        "ok": True,
        "has_taskmaster": has_taskmaster,
        "prd_path": prd_path,
        "task_count": task_count,
        "tasks_completed": tasks_completed,
        "tasks_pending": tasks_pending,
        "taskmaster_method": tm_method["method"],
        "has_claude_md": has_claude_md,
        "has_crash_state": crash_state.get("has_incomplete", False),
        "crash_state": crash_state if crash_state.get("has_incomplete") else None,
    }


def cmd_preflight(args: argparse.Namespace) -> None:
    try:
        emit(run_preflight())
    except CommandError as e:
        fail(e.message, **e.extra)


def run_detect_taskmaster() -> dict:
    """Detect taskmaster method: MCP > CLI > none."""
    result = _detect_taskmaster_method()
    return {"ok": True, **result}


def cmd_detect_taskmaster(args: argparse.Namespace) -> None:
    try:
        emit(run_detect_taskmaster())
    except CommandError as e:
        fail(e.message, **e.extra)
