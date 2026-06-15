"""Suggestion JSONL store + summary contracts (sibling to test_feedback)."""

import json
from pathlib import Path

from prd_taskmaster.suggestions import append_suggestion, summarize_suggestions


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_append_suggestion_writes_valid_jsonl_row(tmp_path):
    path = tmp_path / "suggestions.jsonl"

    result = append_suggestion(
        {
            "ts": 123.5,
            "text": "Unify the engine + launcher suggestion logs.",
            "context": "phase: integrate",
            "source_repo": "prd-taskmaster-plugin",
            "session": "claude-prd-taskmaster-plugin",
        },
        path=path,
    )

    assert result["ok"] is True
    assert result["suggestions_path"] == str(path)
    assert _rows(path) == [
        {
            "ts": 123.5,
            "text": "Unify the engine + launcher suggestion logs.",
            "context": "phase: integrate",
            "source_repo": "prd-taskmaster-plugin",
            "session": "claude-prd-taskmaster-plugin",
        }
    ]


def test_append_suggestion_rejects_empty_text_without_writing(tmp_path):
    path = tmp_path / "suggestions.jsonl"

    for text in ("", "   ", None, 5):
        result = append_suggestion({"text": text}, path=path)
        assert result["ok"] is False
        assert "text" in result["error"]

    assert not path.exists()


def test_env_override_resolves_store_path(tmp_path, monkeypatch):
    target = tmp_path / "shared" / "suggestions.jsonl"
    monkeypatch.setenv("ATLAS_SUGGESTIONS_PATH", str(target))

    result = append_suggestion({"text": "lands at the shared path"})

    assert result["ok"] is True
    assert result["suggestions_path"] == str(target)
    assert target.is_file()


def test_summarize_suggestions_counts_and_skips_corrupt(tmp_path):
    path = tmp_path / "suggestions.jsonl"
    path.write_text(
        json.dumps({"ts": 1.0, "text": "a", "source_repo": "repo-x"})
        + "\nnot json\n"
        + json.dumps({"ts": 2.0, "text": "b", "source_repo": "repo-x"})
        + "\n"
    )

    report = summarize_suggestions(path)

    assert report["ok"] is True
    assert report["total"] == 2
    assert report["skipped_lines"] == 1
    assert report["by_source_repo"] == {"repo-x": 2}
    assert len(report["last_5"]) == 2
