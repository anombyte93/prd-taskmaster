"""TaskMaster-compatible task selection and status updates."""

from __future__ import annotations

import argparse
import json
from typing import Any

from prd_taskmaster import fleet, parallel
from prd_taskmaster.lib import CommandError, emit, fail, locked_update

VALID_STATUSES = {
    "pending",
    "in-progress",
    "done",
    "review",
    "deferred",
    "cancelled",
    "blocked",
}

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _priority_rank(task: dict) -> int:
    return _PRIORITY_RANK.get(str(task.get("priority", "medium")).lower(), 1)


def _sortable_id(value: Any) -> tuple[int, int | str]:
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text)


def _status(item: dict) -> str:
    return str(item.get("status", "pending"))


def _dependencies(item: dict) -> list:
    deps = item.get("dependencies") or []
    return deps if isinstance(deps, list) else []


def _resolve_tasks(tag: str | None) -> tuple[str, dict, str | None, list[dict]]:
    resolved_tag = parallel.current_tag(tag)
    raw, tag_key = fleet._load_tagged_or_raise(resolved_tag)
    try:
        tasks = parallel.get_tasks(raw, tag_key)
    except (KeyError, TypeError) as exc:
        raise CommandError(
            f"tasks missing for tag '{resolved_tag}' in {parallel.TASKS}"
        ) from exc
    return resolved_tag, raw, tag_key, tasks


def _tag_key_for_raw(raw: dict, tag: str) -> str | None:
    if tag in raw and isinstance(raw.get(tag), dict):
        return tag
    if "tasks" in raw and isinstance(raw["tasks"], list):
        return None
    raise CommandError(f"tag '{tag}' not found in {parallel.TASKS}")


def _ready_subtask(parent: dict) -> dict | None:
    subtasks = parent.get("subtasks") or []
    done_ids = {
        str(subtask.get("id"))
        for subtask in subtasks
        if _status(subtask) == "done"
    }
    pending = [
        subtask
        for subtask in subtasks
        if _status(subtask) == "pending"
        and all(str(dep_id) in done_ids for dep_id in _dependencies(subtask))
    ]
    if not pending:
        return None
    return sorted(pending, key=lambda subtask: _sortable_id(subtask.get("id")))[0]


def _subtask_envelope(parent: dict, subtask: dict) -> dict:
    parent_id = str(parent.get("id"))
    subtask_id = str(subtask.get("id"))
    envelope = dict(subtask)
    envelope["id"] = f"{parent_id}.{subtask_id}"
    envelope.setdefault("priority", parent.get("priority", "medium"))
    envelope.setdefault("subtasks", [])
    envelope["parent_id"] = parent_id
    envelope["parent_title"] = parent.get("title", "")
    envelope["parentId"] = parent_id
    return envelope


def _in_progress_candidates(tasks: list[dict]) -> list[dict]:
    candidates = [
        task
        for task in tasks
        if _status(task) == "in-progress"
        and any(_status(subtask) == "pending" for subtask in (task.get("subtasks") or []))
    ]
    return sorted(
        candidates,
        key=lambda task: (_priority_rank(task), _sortable_id(task.get("id"))),
    )


def _ready_candidates(tasks: list[dict], ready_ids: list) -> list[dict]:
    ready = {str(task_id) for task_id in ready_ids}
    candidates = [task for task in tasks if str(task.get("id")) in ready]
    return sorted(
        candidates,
        key=lambda task: (
            _priority_rank(task),
            len(_dependencies(task)),
            _sortable_id(task.get("id")),
        ),
    )


def run_next_task(tag: str | None = None) -> dict:
    """Return the next TaskMaster-compatible task or subtask selection."""
    resolved_tag, _raw, _tag_key, tasks = _resolve_tasks(tag)
    ready_ids = fleet.ready_set(tasks)

    for parent in _in_progress_candidates(tasks):
        subtask = _ready_subtask(parent)
        selected = _subtask_envelope(parent, subtask) if subtask is not None else parent
        return {
            "ok": True,
            "tag": resolved_tag,
            "task": selected,
            "ready_count": len(ready_ids),
            "source": "in-progress",
        }

    ready = _ready_candidates(tasks, ready_ids)
    if ready:
        return {
            "ok": True,
            "tag": resolved_tag,
            "task": ready[0],
            "ready_count": len(ready_ids),
            "source": "ready",
        }

    return {
        "ok": True,
        "tag": resolved_tag,
        "task": None,
        "ready_count": len(ready_ids),
        "source": "none",
    }


def _split_id(id_str: str) -> tuple[str, str | None]:
    parts = str(id_str).split(".")
    if len(parts) == 1 and parts[0]:
        return parts[0], None
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    raise CommandError(f"unknown id: {id_str}")


def run_set_status(id_str: str, status: str, tag: str | None = None) -> dict:
    """Set a parent task or subtask status under a file lock."""
    if status not in VALID_STATUSES:
        raise CommandError(f"unknown status: {status}")

    parent_id, subtask_id = _split_id(id_str)
    resolved_tag = parallel.current_tag(tag)
    result: dict[str, Any] = {}

    def transform(current: str) -> str:
        if not current.strip():
            raise CommandError(f"{parallel.TASKS} not found")
        try:
            raw = json.loads(current)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Failed to parse {parallel.TASKS}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CommandError(f"Failed to parse {parallel.TASKS}: root must be an object")

        tag_key = _tag_key_for_raw(raw, resolved_tag)
        try:
            tasks = parallel.get_tasks(raw, tag_key)
        except (KeyError, TypeError) as exc:
            raise CommandError(
                f"tasks missing for tag '{resolved_tag}' in {parallel.TASKS}"
            ) from exc

        for task in tasks:
            if str(task.get("id")) != parent_id:
                continue
            if subtask_id is None:
                task["status"] = status
                result.update({
                    "ok": True,
                    "tag": resolved_tag,
                    "id": str(id_str),
                    "status": status,
                    "kind": "task",
                })
                return json.dumps(raw, indent=2, default=str)

            for subtask in task.get("subtasks") or []:
                if str(subtask.get("id")) == subtask_id:
                    subtask["status"] = status
                    result.update({
                        "ok": True,
                        "tag": resolved_tag,
                        "id": str(id_str),
                        "status": status,
                        "kind": "subtask",
                    })
                    return json.dumps(raw, indent=2, default=str)
            raise CommandError(f"unknown id: {id_str}")

        raise CommandError(f"unknown id: {id_str}")

    locked_update(parallel.TASKS, transform)
    return result


def cmd_next_task(args: argparse.Namespace) -> None:
    try:
        emit(run_next_task(getattr(args, "tag", None)))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def cmd_set_status(args: argparse.Namespace) -> None:
    try:
        emit(run_set_status(args.id, args.status, getattr(args, "tag", None)))
    except CommandError as exc:
        fail(exc.message, **exc.extra)
