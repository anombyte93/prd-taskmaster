"""Atlas agent suggestion JSONL store and summary helpers.

Free-text improvement suggestions about using the Atlas engine — dogfooding
pain points, missing tools, rough edges — captured durably so they can be
reviewed and triaged later, rather than lost in a transcript.

Sibling to ``feedback.py`` (which is structured rating feedback). The store
path is env-overridable (``ATLAS_SUGGESTIONS_PATH``) so the engine and the
launcher can be pointed at ONE aggregated, human-reviewable log.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

from prd_taskmaster.lib import locked_update

DEFAULT_SUGGESTIONS = Path(".atlas-ai") / "suggestions.jsonl"
# Optional free-text/string metadata fields, all carried through verbatim.
STR_FIELDS = ("context", "source_repo", "session", "agent", "task_ref")


def _store_path(path: str | Path | None = None) -> Path:
    """Resolve the suggestions log path.

    Precedence: explicit ``path`` arg → ``ATLAS_SUGGESTIONS_PATH`` env →
    repo-local ``.atlas-ai/suggestions.jsonl``. Point the env at a shared file
    to unify engine + launcher suggestions into one reviewable log.
    """
    if path:
        return Path(path)
    env = os.environ.get("ATLAS_SUGGESTIONS_PATH", "").strip()
    return Path(env) if env else DEFAULT_SUGGESTIONS


def _error(message: str, **extra: Any) -> dict:
    return {"ok": False, "error": message, **extra}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_suggestion_row(row: Any) -> dict:
    if not isinstance(row, dict):
        return _error("suggestion row must be a dict")

    text = row.get("text")
    if not isinstance(text, str) or not text.strip():
        return _error("text is required and must be a non-empty string", field="text")

    ts = row.get("ts", time.time())
    if not _is_number(ts):
        return _error("ts must be an epoch number", field="ts")

    normalized: dict[str, Any] = {"ts": float(ts), "text": text.strip()}
    for field in STR_FIELDS:
        value = row.get(field, "")
        if not isinstance(value, str):
            return _error(f"{field} must be a string", field=field)
        if value:
            normalized[field] = value

    if "context_obj" in row:
        context_obj = row["context_obj"]
        if not isinstance(context_obj, dict):
            return _error("context_obj must be a dict", field="context_obj")
        normalized["context_obj"] = context_obj

    return {"ok": True, "row": normalized}


def append_suggestion(row, path=None):
    """Append one validated suggestion row to JSONL under a flock-guarded update."""
    try:
        normalized = _normalize_suggestion_row(row)
        if not normalized.get("ok"):
            return normalized

        p = _store_path(path)
        payload = normalized["row"]
        line = json.dumps(payload, default=str) + "\n"
        locked_update(p, lambda current: current + line)
        return {"ok": True, "suggestions_path": str(p), "row": payload}
    except Exception as exc:
        return _error("failed to append suggestion", detail=str(exc), error_type=type(exc).__name__)


def summarize_suggestions(path=None):
    """Summarize the suggestions log, skipping malformed JSONL lines."""
    p = _store_path(path)
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
        return _error("failed to summarize suggestions", detail=str(exc), error_type=type(exc).__name__)

    by_repo: dict[str, int] = {}
    for row in rows:
        repo = str(row.get("source_repo", "") or "unspecified")
        by_repo[repo] = by_repo.get(repo, 0) + 1

    return {
        "ok": True,
        "total": len(rows),
        "by_source_repo": dict(sorted(by_repo.items())),
        "last_5": rows[-5:],
        "skipped_lines": skipped,
        "suggestions_path": str(p),
    }
