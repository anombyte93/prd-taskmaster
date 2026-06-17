"""CLI command core for `reachability-sweep`.

run_reachability_sweep(task_id, start_commit, cwd=None) -> dict
  - Loads the task from .taskmaster/tasks/tasks.json
  - Runs reachability.sweep_task(repo_root, task, start_commit)
  - Writes the verdict dict into the task's CDD card
    .atlas-ai/cdd/task-<id>.json under the "reachability" key
    (atomic, additive — preserves all other card keys)
  - Returns the full sweep verdict dict

Exit code convention (enforced by cmd_reachability_sweep):
  0 → verdict in {WIRED, EXEMPT}
  1 → verdict in {ORPHAN, ERROR} or any CommandError

CDD card format written:
  {
      ...existing card keys...,
      "reachability": {
          "verdict": "WIRED" | "ORPHAN" | "EXEMPT" | "ERROR",
          "tier":         str,
          "modules":      [...],
          "checked_at":   str (ISO-8601),
          "start_commit": str,
          ...
      }
  }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from prd_taskmaster import parallel
from prd_taskmaster.lib import CommandError, atomic_write
from prd_taskmaster.reachability import sweep_task

# Verdicts that map to exit 0.
_PASS_VERDICTS = {"WIRED", "EXEMPT"}


def _cdd_dir(repo_root: Path) -> Path:
    return repo_root / ".atlas-ai" / "cdd"


def _card_path(repo_root: Path, task_id: str) -> "Path | None":
    """Return the CDD card path for *task_id*, or None if it doesn't exist.

    Mirrors ship-check._card_path_for: prefers task-<id>.json; falls back to
    combined cards whose hyphen-separated id-list contains the id.
    """
    cdd = _cdd_dir(repo_root)
    if not cdd.exists():
        return None

    direct = cdd / f"task-{task_id}.json"
    if direct.exists():
        return direct

    for card in cdd.glob("task-*.json"):
        stem = card.stem
        if not stem.startswith("task-"):
            continue
        ids = stem[len("task-"):].split("-")
        if task_id in ids:
            return card

    return None


def _load_task(repo_root: Path, task_id: str) -> dict:
    """Load the task dict from .taskmaster/tasks/tasks.json.

    Looks for task_id in every tag's tasks list (and the flat-tasks fallback).
    Raises CommandError if not found.
    """
    tasks_path = repo_root / ".taskmaster" / "tasks" / "tasks.json"
    if not tasks_path.exists():
        raise CommandError(f"tasks.json not found at {tasks_path}")

    try:
        raw = json.loads(tasks_path.read_text())
    except json.JSONDecodeError as exc:
        raise CommandError(f"tasks.json is invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise CommandError("tasks.json root must be an object")

    # Search all tag namespaces (plus flat "tasks" list).
    candidates: list[dict] = []
    if isinstance(raw.get("tasks"), list):
        candidates.extend(raw["tasks"])
    for value in raw.values():
        if isinstance(value, dict) and isinstance(value.get("tasks"), list):
            candidates.extend(value["tasks"])

    for task in candidates:
        if str(task.get("id")) == task_id:
            return task

    raise CommandError(f"task {task_id!r} not found in tasks.json")


def run_reachability_sweep(
    task_id: str,
    start_commit: str,
    cwd: "str | None" = None,
) -> dict:
    """Run the reachability sweep for *task_id* and write the result into its CDD card.

    Parameters
    ----------
    task_id:
        The task id (string, may be "1" or "1.2" — only parent IDs supported for sweep).
    start_commit:
        The git sha to compare HEAD against (the sha recorded when work started on the task).
    cwd:
        Optional explicit repo root.  Defaults to the current working directory.

    Returns
    -------
    The sweep verdict dict from reachability.sweep_task.

    Raises
    ------
    CommandError
        If the task is not found, or if the CDD card cannot be updated.
    """
    repo_root = Path(cwd).resolve() if cwd else Path.cwd().resolve()

    # 1. Load the task.
    task = _load_task(repo_root, task_id)

    # 2. Run the sweep.
    verdict = sweep_task(repo_root, task, start_commit)

    # 3. Write the verdict into the CDD card, additively.
    card_path = _card_path(repo_root, task_id)
    if card_path is None:
        # Attempt to use the direct path if it doesn't exist yet — but only if
        # the cdd directory itself exists (the task must have a card already).
        cdd = _cdd_dir(repo_root)
        if not cdd.exists():
            raise CommandError(
                f"task {task_id}: .atlas-ai/cdd/ directory does not exist — "
                f"generate the CDD card (execute-task Step 5) before running the sweep"
            )
        # No existing card: raise with a clear message.
        raise CommandError(
            f"task {task_id}: no CDD card found in .atlas-ai/cdd/ — "
            f"generate the CDD card (execute-task Step 5) before running the sweep"
        )

    # Read existing card, add "reachability", write back atomically.
    try:
        existing: dict[str, Any] = json.loads(card_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(
            f"task {task_id}: cannot read CDD card at {card_path}: {exc}"
        ) from exc

    existing["reachability"] = verdict
    atomic_write(card_path, json.dumps(existing, indent=2, default=str))

    return verdict


# ─── CLI wrapper ──────────────────────────────────────────────────────────────

def cmd_reachability_sweep(args) -> None:
    """CLI entry point for `prd-taskmaster reachability-sweep`."""
    import json as _json
    import sys as _sys

    from prd_taskmaster.lib import fail

    try:
        verdict = run_reachability_sweep(
            task_id=args.task,
            start_commit=args.start_commit,
            cwd=getattr(args, "cwd", None),
        )
    except CommandError as exc:
        fail(exc.message, **exc.extra)
        return  # never reached; fail() exits

    print(_json.dumps(verdict, indent=2, default=str))
    _sys.exit(0 if verdict.get("verdict") in _PASS_VERDICTS else 1)
