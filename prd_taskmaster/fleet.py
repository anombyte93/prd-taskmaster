"""Atlas Fleet dependency scheduler.

The scheduler core operates on a plain list of task dicts. The run_* and
cmd_* wrappers resolve TaskMaster tags for CLI/MCP callers.
"""

import argparse
import json

from prd_taskmaster import parallel
from prd_taskmaster.lib import CommandError, emit, fail


def _task_id(task):
    return task.get("id")


def _status(task):
    return str(task.get("status", "pending"))


def _is_done(task):
    return _status(task) == "done"


def _is_pending(task):
    return _status(task) == "pending"


def _dependencies(task):
    return task.get("dependencies") or []


def _chunk(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def _load_tagged_or_raise(tag):
    if not parallel.TASKS.is_file():
        raise CommandError(f"{parallel.TASKS} not found")
    try:
        raw = json.loads(parallel.TASKS.read_text())
    except json.JSONDecodeError as exc:
        raise CommandError(f"Failed to parse {parallel.TASKS}: {exc}") from exc

    if tag not in raw or not isinstance(raw.get(tag), dict):
        if "tasks" in raw and isinstance(raw["tasks"], list):
            return raw, None
        raise CommandError(f"tag '{tag}' not found in {parallel.TASKS}")
    return raw, tag


def ready_set(tasks):
    """Return pending task IDs whose dependencies are all done."""
    done_ids = {_task_id(task) for task in tasks if _is_done(task)}
    return [
        _task_id(task)
        for task in tasks
        if _is_pending(task)
        and all(dep_id in done_ids for dep_id in _dependencies(task))
    ]


def compute_waves(tasks, max_concurrency=3):
    """Return dependency-ordered execution waves for pending tasks."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")

    completed = {_task_id(task) for task in tasks if _is_done(task)}
    remaining = [task for task in tasks if _is_pending(task)]
    waves = []

    while remaining:
        frontier = [
            task
            for task in remaining
            if all(dep_id in completed for dep_id in _dependencies(task))
        ]
        if not frontier:
            return {
                "waves": waves,
                "blocked": [_task_id(task) for task in remaining],
                "deadlocked": True,
            }

        frontier_ids = [_task_id(task) for task in frontier]
        waves.extend(_chunk(frontier_ids, max_concurrency))
        completed.update(frontier_ids)

        frontier_objects = {id(task) for task in frontier}
        remaining = [
            task for task in remaining
            if id(task) not in frontier_objects
        ]

    return {
        "waves": waves,
        "blocked": [],
        "deadlocked": False,
    }


def run_fleet_waves(concurrency=3, tag=""):
    """Resolve TaskMaster tasks and return fleet wave scheduling JSON."""
    if concurrency < 1:
        raise CommandError("concurrency must be >= 1")

    resolved_tag = parallel.current_tag(argparse.Namespace(tag=tag or None))
    raw, tag_key = _load_tagged_or_raise(resolved_tag)
    try:
        tasks = parallel.get_tasks(raw, tag_key)
    except (KeyError, TypeError) as exc:
        raise CommandError(
            f"tasks missing for tag '{resolved_tag}' in {parallel.TASKS}"
        ) from exc

    waves = compute_waves(tasks, concurrency)
    return {
        "ok": True,
        "tag": resolved_tag,
        "waves": waves["waves"],
        "blocked": waves["blocked"],
        "deadlocked": waves["deadlocked"],
        "ready": ready_set(tasks),
        "concurrency": concurrency,
    }


def cmd_fleet_waves(args):
    """CLI wrapper for fleet-waves."""
    try:
        emit(run_fleet_waves(args.concurrency, getattr(args, "tag", "")))
    except CommandError as exc:
        fail(exc.message, **exc.extra)
