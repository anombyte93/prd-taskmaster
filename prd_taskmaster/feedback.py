"""Atlas agent feedback JSONL store and summary helpers."""

import json
import time
from pathlib import Path
from typing import Any

from prd_taskmaster.lib import emit, fail, locked_update

FEEDBACK = Path(".atlas-ai") / "feedback.jsonl"
HARNESS_CHOICES = {"claude-code", "codex", "gemini", "api", "other"}
TEXT_FIELDS = ("what_went_well", "what_failed", "suggestions")


def _error(message: str, **extra: Any) -> dict:
    return {"ok": False, "error": message, **extra}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_text(row: dict, field: str) -> str | dict:
    value = row.get(field, "")
    if not isinstance(value, str):
        return _error(f"{field} must be a string", field=field)
    return value


def _normalize_feedback_row(row: Any) -> dict:
    if not isinstance(row, dict):
        return _error("feedback row must be a dict")

    agent = row.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        return _error("agent is required and must be a non-empty string", field="agent")

    harness = row.get("harness")
    if not isinstance(harness, str) or harness not in HARNESS_CHOICES:
        return _error(
            "harness must be one of claude-code, codex, gemini, api, other",
            field="harness",
        )

    rating = row.get("rating")
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        return _error("rating must be an integer from 1 to 5", field="rating")

    task_ref = row.get("task_ref", "")
    if not isinstance(task_ref, str):
        return _error("task_ref must be a string", field="task_ref")

    ts = row.get("ts", time.time())
    if not _is_number(ts):
        return _error("ts must be an epoch number", field="ts")

    normalized = {
        "ts": float(ts),
        "agent": agent,
        "harness": harness,
        "task_ref": task_ref,
        "rating": rating,
    }
    for field in TEXT_FIELDS:
        value = _normalize_text(row, field)
        if isinstance(value, dict):
            return value
        normalized[field] = value

    if "context" in row:
        context = row["context"]
        if not isinstance(context, dict):
            return _error("context must be a dict", field="context")
        normalized["context"] = context

    return {"ok": True, "row": normalized}


def append_feedback(row, path=None):
    """Append one validated feedback row to JSONL under a flock-guarded update."""
    try:
        normalized = _normalize_feedback_row(row)
        if not normalized.get("ok"):
            return normalized

        p = Path(path) if path else FEEDBACK
        payload = normalized["row"]
        line = json.dumps(payload, default=str) + "\n"
        locked_update(p, lambda current: current + line)
        return {"ok": True, "feedback_path": str(p), "row": payload}
    except Exception as exc:
        return _error("failed to append feedback", detail=str(exc), error_type=type(exc).__name__)


def _valid_rating(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5


def summarize_feedback(path=None):
    """Summarize Atlas agent feedback, skipping malformed JSONL lines."""
    p = Path(path) if path else FEEDBACK
    rows = []
    skipped = 0
    try:
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if not isinstance(parsed, dict):
                    skipped += 1
                    continue
                rows.append(parsed)
    except Exception as exc:
        return _error("failed to summarize feedback", detail=str(exc), error_type=type(exc).__name__)

    ratings = [row["rating"] for row in rows if _valid_rating(row.get("rating"))]
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        harness = str(row.get("harness", "unknown"))
        group = groups.setdefault(harness, {"harness": harness, "count": 0, "_ratings": []})
        group["count"] += 1
        if _valid_rating(row.get("rating")):
            group["_ratings"].append(row["rating"])

    per_harness = []
    for harness, group in sorted(groups.items()):
        group_ratings = group["_ratings"]
        per_harness.append({
            "harness": harness,
            "count": group["count"],
            "avg_rating": (sum(group_ratings) / len(group_ratings)) if group_ratings else None,
        })

    return {
        "ok": True,
        "total": len(rows),
        "avg_rating": (sum(ratings) / len(ratings)) if ratings else None,
        "per_harness": per_harness,
        "last_5": rows[-5:],
        "failed_count": sum(1 for row in rows if str(row.get("what_failed", "")).strip()),
        "skipped_lines": skipped,
        "feedback_path": str(p),
    }


def _emit_result(result: dict) -> None:
    if result.get("ok"):
        emit(result)
    extra = {k: v for k, v in result.items() if k not in {"ok", "error"}}
    fail(result.get("error", "feedback command failed"), **extra)


def cmd_feedback_add(args) -> None:
    row = {
        "agent": args.agent,
        "harness": args.harness,
        "task_ref": getattr(args, "task_ref", ""),
        "rating": args.rating,
        "what_went_well": getattr(args, "well", ""),
        "what_failed": getattr(args, "failed", ""),
        "suggestions": getattr(args, "suggest", ""),
    }
    _emit_result(append_feedback(row))


def cmd_feedback_report(args) -> None:
    _emit_result(summarize_feedback(getattr(args, "path", None)))
