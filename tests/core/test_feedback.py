"""Feedback loop JSONL store, summary, and CLI contracts."""

import json
import subprocess
import sys
from pathlib import Path

from prd_taskmaster.feedback import append_feedback, summarize_feedback


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "script.py"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _run_cli(cwd: Path, *args: str, expect_exit: int = 0) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert proc.returncode == expect_exit, (
        f"exit={proc.returncode} expected={expect_exit}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    return json.loads(proc.stdout)


def test_append_feedback_writes_valid_jsonl_row(tmp_path):
    path = tmp_path / "feedback.jsonl"

    result = append_feedback(
        {
            "ts": 123.5,
            "agent": "Codex",
            "harness": "codex",
            "task_ref": "task-7",
            "rating": 5,
            "what_went_well": "TDD made the contract explicit.",
            "what_failed": "",
            "suggestions": "Keep the wrapper thin.",
            "context": {"phase": "execute"},
        },
        path=path,
    )

    assert result["ok"] is True
    assert result["feedback_path"] == str(path)
    assert _rows(path) == [
        {
            "ts": 123.5,
            "agent": "Codex",
            "harness": "codex",
            "task_ref": "task-7",
            "rating": 5,
            "what_went_well": "TDD made the contract explicit.",
            "what_failed": "",
            "suggestions": "Keep the wrapper thin.",
            "context": {"phase": "execute"},
        }
    ]


def test_append_feedback_rejects_invalid_rating_without_writing(tmp_path):
    path = tmp_path / "feedback.jsonl"

    for rating in (0, 6, "5", True):
        result = append_feedback(
            {
                "agent": "Codex",
                "harness": "codex",
                "rating": rating,
                "what_went_well": "",
                "what_failed": "",
                "suggestions": "",
            },
            path=path,
        )

        assert result["ok"] is False
        assert "rating" in result["error"]

    assert not path.exists()


def test_summarize_feedback_skips_corrupt_lines(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text(
        json.dumps({
            "ts": 1.0,
            "agent": "Codex",
            "harness": "codex",
            "rating": 4,
            "what_failed": "",
        })
        + "\nnot json\n"
    )

    report = summarize_feedback(path)

    assert report["ok"] is True
    assert report["total"] == 1
    assert report["skipped_lines"] == 1


def test_summarize_feedback_math_and_last_five(tmp_path):
    path = tmp_path / "feedback.jsonl"
    rows = [
        {"ts": 1.0, "agent": "A", "harness": "codex", "rating": 5, "what_failed": ""},
        {"ts": 2.0, "agent": "B", "harness": "claude-code", "rating": 4, "what_failed": "timeout"},
        {"ts": 3.0, "agent": "C", "harness": "codex", "rating": 3, "what_failed": " "},
        {"ts": 4.0, "agent": "D", "harness": "api", "rating": 2, "what_failed": "schema drift"},
        {"ts": 5.0, "agent": "E", "harness": "claude-code", "rating": 2, "what_failed": ""},
        {"ts": 6.0, "agent": "F", "harness": "codex", "rating": 5, "what_failed": ""},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    report = summarize_feedback(path)

    assert report["total"] == 6
    assert report["avg_rating"] == 3.5
    assert report["failed_count"] == 2
    assert report["last_5"] == rows[-5:]
    by_harness = {entry["harness"]: entry for entry in report["per_harness"]}
    assert by_harness["codex"] == {"harness": "codex", "count": 3, "avg_rating": 13 / 3}
    assert by_harness["claude-code"] == {"harness": "claude-code", "count": 2, "avg_rating": 3.0}
    assert by_harness["api"] == {"harness": "api", "count": 1, "avg_rating": 2.0}


def test_feedback_cli_add_and_report(tmp_path):
    add = _run_cli(
        tmp_path,
        "feedback-add",
        "--rating",
        "4",
        "--agent",
        "Codex",
        "--harness",
        "codex",
        "--task-ref",
        "task-7",
        "--well",
        "CLI writes JSON.",
        "--failed",
        "",
        "--suggest",
        "Keep reports terse.",
    )

    assert add["ok"] is True
    path = tmp_path / ".atlas-ai" / "feedback.jsonl"
    [row] = _rows(path)
    assert row["rating"] == 4
    assert row["agent"] == "Codex"
    assert row["harness"] == "codex"

    report = _run_cli(tmp_path, "feedback-report")

    assert report["ok"] is True
    assert report["total"] == 1
    assert report["avg_rating"] == 4.0
    assert report["feedback_path"] == str(Path(".atlas-ai") / "feedback.jsonl")
