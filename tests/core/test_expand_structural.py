"""Zero-AI structural expansion fallback (dogfood friction #9).

GENERATE.md and validate_setup both claim expand "degrades to a structural pass"
when no research/AI provider is reachable — but the native/agent expand paths
all require a provider and otherwise only return agent_action_required. These
tests pin the deterministic, offline decomposition that backs that claim.
"""

import json
from pathlib import Path

from prd_taskmaster.tasks import (
    _structural_subtasks,
    run_expand_structural,
)


def test_structural_subtasks_uses_detail_bullets():
    task = {
        "title": "Build the importer",
        "details": "Steps:\n- Parse the CSV\n- Validate rows\n* Write to DB\n1. Emit a report",
    }
    subs = _structural_subtasks(task)
    titles = [s["title"] for s in subs]
    assert titles == ["Parse the CSV", "Validate rows", "Write to DB", "Emit a report"]
    # ids are 1-based and chained as dependencies
    assert [s["id"] for s in subs] == [1, 2, 3, 4]
    assert subs[0]["dependencies"] == []
    assert subs[1]["dependencies"] == [1]
    assert all(s["status"] == "pending" for s in subs)


def test_structural_subtasks_dedupes_bullets():
    task = {"title": "T", "details": "- do x\n- Do X\n- do y"}
    titles = [s["title"] for s in _structural_subtasks(task)]
    assert titles == ["do x", "do y"]


def test_structural_subtasks_falls_back_to_lifecycle_when_no_bullets():
    # A plain task with no bullet breakdown still yields >= 2 verifiable subtasks.
    task = {"title": "Add a footer", "details": "Just a small tweak."}
    subs = _structural_subtasks(task)
    assert len(subs) >= 2
    assert all("Add a footer" in s["title"] for s in subs)


def test_structural_subtasks_always_meets_minimum():
    task = {"title": "Tiny", "details": "- only one bullet"}
    subs = _structural_subtasks(task, min_subtasks=2)
    # one bullet is below the minimum, so it falls back to lifecycle checkpoints
    assert len(subs) >= 2


def _write_tasks(tmp_path: Path, tasks: list) -> Path:
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps({"tasks": tasks}))
    return p


def test_run_expand_structural_expands_only_under_decomposed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_tasks(
        tmp_path,
        [
            {"id": 1, "title": "No subtasks", "details": "- a\n- b\n- c", "subtasks": []},
            {
                "id": 2,
                "title": "Already expanded",
                "details": "x",
                "subtasks": [
                    {"id": 1, "title": "s1"},
                    {"id": 2, "title": "s2"},
                ],
            },
        ],
    )

    result = run_expand_structural(str(path))

    assert result["ok"] is True
    assert result["method"] == "structural"
    assert result["expanded"] == [1]  # task 2 left untouched
    assert result["expanded_count"] == 1

    data = json.loads(path.read_text())
    by_id = {t["id"]: t for t in data["tasks"]}
    assert [s["title"] for s in by_id[1]["subtasks"]] == ["a", "b", "c"]
    # idempotent: task 2's original subtasks preserved
    assert [s["title"] for s in by_id[2]["subtasks"]] == ["s1", "s2"]


def test_run_expand_structural_guarantees_min_subtasks_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No API keys, no providers — the whole point of the fallback.
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = _write_tasks(
        tmp_path,
        [{"id": 1, "title": "Plain task", "details": "no breakdown here"}],
    )

    run_expand_structural(str(path))

    data = json.loads(path.read_text())
    assert len(data["tasks"][0]["subtasks"]) >= 2


def test_run_expand_structural_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_tasks(
        tmp_path, [{"id": 1, "title": "T", "details": "- a\n- b", "subtasks": []}]
    )
    first = run_expand_structural(str(path))
    assert first["expanded_count"] == 1
    second = run_expand_structural(str(path))
    assert second["expanded_count"] == 0  # nothing left to expand
