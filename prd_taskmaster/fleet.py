"""Atlas Fleet dependency scheduler.

The public functions in this module operate on a plain list of task dicts.
Tag resolution belongs to CLI/MCP layers, not this scheduler core.
"""


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
