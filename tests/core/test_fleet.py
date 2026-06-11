"""Unit tests for the Atlas Fleet wave scheduler."""

from prd_taskmaster.fleet import compute_waves, ready_set


def _task(task_id, status="pending", dependencies=None):
    return {
        "id": task_id,
        "status": status,
        "dependencies": [] if dependencies is None else dependencies,
    }


def test_compute_waves_linear_chain():
    tasks = [
        _task(1),
        _task(2, dependencies=[1]),
        _task(3, dependencies=[2]),
    ]

    assert ready_set(tasks) == [1]
    assert compute_waves(tasks) == {
        "waves": [[1], [2], [3]],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_diamond_dependency_preserves_input_order():
    tasks = [
        _task(1),
        _task(3, dependencies=[1]),
        _task(2, dependencies=[1]),
        _task(4, dependencies=[2, 3]),
    ]

    assert compute_waves(tasks) == {
        "waves": [[1], [3, 2], [4]],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_deadlock_cycle_lists_blocked_members():
    tasks = [
        _task(1, dependencies=[2]),
        _task(2, dependencies=[1]),
    ]

    assert compute_waves(tasks) == {
        "waves": [],
        "blocked": [1, 2],
        "deadlocked": True,
    }


def test_compute_waves_chunks_frontier_by_concurrency_in_input_order():
    tasks = [
        _task(5),
        _task(1),
        _task(4),
        _task(2),
        _task(3),
    ]

    assert compute_waves(tasks, max_concurrency=2) == {
        "waves": [[5, 1], [4, 2], [3]],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_empty_graph():
    assert compute_waves([]) == {
        "waves": [],
        "blocked": [],
        "deadlocked": False,
    }


def test_compute_waves_all_done_graph():
    tasks = [
        _task(1, status="done"),
        _task(2, status="done", dependencies=[1]),
    ]

    assert ready_set(tasks) == []
    assert compute_waves(tasks) == {
        "waves": [],
        "blocked": [],
        "deadlocked": False,
    }
