"""TaskMaster-compatible task selection and status updates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from prd_taskmaster import fleet, parallel
from prd_taskmaster.lib import CommandError, emit, fail, locked_update

# Tiers that require a reachability verdict before done is accepted.
_GATED_TIERS = {"wired", "live"}
# Reachability verdicts that allow done.
_PASSING_VERDICTS = {"WIRED", "EXEMPT"}

VALID_STATUSES = {
    "pending",
    "in-progress",
    "done",
    "review",
    "deferred",
    "cancelled",
    "blocked",
    "scaffold",  # auto-downgraded orphan: code exists but not wired into the system;
                 # NOT done, NOT deferred (deferred = deliberate); blocks the ship gate.
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


def _select_next_task(resolved_tag: str, tasks: list[dict]) -> dict:
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


def run_next_task(tag: str | None = None) -> dict:
    """Return the next TaskMaster-compatible task or subtask selection."""
    resolved_tag, _raw, _tag_key, tasks = _resolve_tasks(tag)
    return _select_next_task(resolved_tag, tasks)


def _claim_selected_task(tasks: list[dict], selected: dict) -> dict:
    selected_id = str(selected.get("id"))
    parent_id = str(selected.get("parent_id", "") or "")
    if parent_id and "." in selected_id:
        subtask_id = selected_id.split(".", 1)[1]
        for task in tasks:
            if str(task.get("id")) != parent_id:
                continue
            for subtask in task.get("subtasks") or []:
                if str(subtask.get("id")) == subtask_id:
                    subtask["status"] = "in-progress"
                    return _subtask_envelope(task, subtask)
    else:
        for task in tasks:
            if str(task.get("id")) == selected_id:
                task["status"] = "in-progress"
                return dict(task)
    raise CommandError(f"unknown id: {selected_id}")


def run_claim_task(tag: str | None = None) -> dict:
    """Atomically select the next task or subtask and mark it in-progress."""
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

        selected = _select_next_task(resolved_tag, tasks)
        if selected["task"] is None:
            result.update(selected)
            result["ok"] = False
            result["claimed"] = False
            return current

        claimed_task = _claim_selected_task(tasks, selected["task"])
        result.update(selected)
        result["task"] = claimed_task
        result["claimed"] = True
        return json.dumps(raw, indent=2, default=str)

    locked_update(parallel.TASKS, transform)
    return result


def _split_id(id_str: str) -> tuple[str, str | None]:
    parts = str(id_str).split(".")
    if len(parts) == 1 and parts[0]:
        return parts[0], None
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    raise CommandError(f"unknown id: {id_str}")


def run_set_status(
    id_str: str,
    status: str,
    tag: str | None = None,
    evidence_ref: str | None = None,
    reachability: dict | None = None,
) -> dict:
    """Set a parent task or subtask status under a file lock.

    For status != "done": evidence_ref and reachability are accepted but ignored.
    For status == "done" on a wired/live task: a reachability dict with verdict
    in {WIRED, EXEMPT} is required; absence or a blocking verdict (ORPHAN, ERROR)
    raises CommandError.

    When evidence_ref or reachability is provided (any tier), the proof is
    persisted on the task object as doneEvidence / reachability fields.
    """
    if status not in VALID_STATUSES:
        raise CommandError(f"unknown status: {status}")

    parent_id, subtask_id = _split_id(id_str)
    resolved_tag = parallel.current_tag(tag)
    result: dict[str, Any] = {}

    # Auto-read reachability from CDD card when marking done without an explicit verdict.
    # This allows `set-status done` to work transparently after the sweep has run and
    # written the verdict into the card (execute-task Step 9 → Step 10 flow).
    if reachability is None and status == "done" and subtask_id is None:
        reachability = _read_cdd_reachability(parent_id)

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
                # Tier-gated reachability check for parent tasks marked done.
                if status == "done":
                    tier = (
                        (task.get("phaseConfig") or {}).get("tier")
                        or task.get("tier")
                        or "domain-model"
                    )
                    if tier in _GATED_TIERS:
                        if reachability is None:
                            raise CommandError(
                                f"cannot mark task {id_str} (tier={tier}) done without a"
                                f" reachability verdict — run the reachability sweep"
                            )
                        verdict = reachability.get("verdict")
                        if verdict not in _PASSING_VERDICTS:
                            raise CommandError(
                                f"cannot mark task {id_str} done: reachability {verdict}"
                                f" — wire the module(s) into the running system or"
                                f" re-status deferred/scaffold"
                            )
                task["status"] = status
                # Persist evidence additively when provided (any tier).
                if evidence_ref is not None:
                    task["doneEvidence"] = {
                        "evidence_ref": evidence_ref,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                if reachability is not None:
                    task["reachability"] = reachability
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


def cmd_claim_task(args: argparse.Namespace) -> None:
    try:
        emit(run_claim_task(getattr(args, "tag", None)))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def _parse_reachability_arg(value: "str | None") -> "dict | None":
    """Parse the --reachability CLI argument.

    Accepts:
      - None             → None (not provided)
      - "WIRED"          → {"verdict": "WIRED"}
      - "EXEMPT"         → {"verdict": "EXEMPT"}
      - "ORPHAN"         → {"verdict": "ORPHAN"}
      - '{"verdict":…}'  → parsed JSON dict

    Raises CommandError on invalid input.
    """
    if value is None:
        return None
    value = value.strip()
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CommandError(f"--reachability: invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise CommandError("--reachability: JSON value must be an object")
        return parsed
    # Bare verdict string.
    if value in ("WIRED", "EXEMPT", "ORPHAN", "ERROR"):
        return {"verdict": value}
    raise CommandError(
        f"--reachability: expected WIRED, EXEMPT, ORPHAN, or a JSON dict; got {value!r}"
    )


def _read_cdd_reachability(task_id: str) -> "dict | None":
    """Attempt to read the reachability block from the task's CDD card.

    Looks for .atlas-ai/cdd/task-<id>.json (direct) or a combined card
    whose hyphen-separated id-list contains the id (matching ship-check logic).
    Returns the dict under the "reachability" key, or None if unavailable.
    """
    from pathlib import Path as _Path

    cdd_dir = _Path(".atlas-ai") / "cdd"
    if not cdd_dir.exists():
        return None

    tid_str = str(task_id)
    # Direct card.
    direct = cdd_dir / f"task-{tid_str}.json"
    card_path = None
    if direct.exists():
        card_path = direct
    else:
        # Combined card fallback.
        for card in cdd_dir.glob("task-*.json"):
            stem = card.stem
            if not stem.startswith("task-"):
                continue
            ids = stem[len("task-"):].split("-")
            if tid_str in ids:
                card_path = card
                break

    if card_path is None:
        return None

    try:
        card = json.loads(card_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    reach = card.get("reachability")
    return reach if isinstance(reach, dict) else None


def cmd_set_status(args: argparse.Namespace) -> None:
    # Parse --reachability flag (bare verdict string or JSON dict).
    try:
        reachability = _parse_reachability_arg(getattr(args, "reachability", None))
    except CommandError as exc:
        fail(exc.message, **exc.extra)
        return

    # Auto-read fallback: if marking done and --reachability not given, try the CDD card.
    if reachability is None and args.status == "done":
        # Only the parent task id matters for CDD card lookup.
        parent_id = str(args.id).split(".")[0]
        reachability = _read_cdd_reachability(parent_id)

    evidence_ref = getattr(args, "evidence_ref", None)

    try:
        emit(
            run_set_status(
                args.id,
                args.status,
                getattr(args, "tag", None),
                evidence_ref=evidence_ref,
                reachability=reachability,
            )
        )
    except CommandError as exc:
        fail(exc.message, **exc.extra)
