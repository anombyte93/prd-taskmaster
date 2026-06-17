"""Unit tests for the golden-parity harness normalizer + differ + extractor.

These are PURE-function tests — they do NOT call any model, backend, or
subprocess. They lock two contracts:
  1. the harness compares the STRUCTURE of two task graphs (parity-relevant
     shape) and not volatile fields;
  2. the harness extracts tasks from DISK (.taskmaster/tasks/tasks.json) after
     parse_prd, NOT from the parse_prd result dict — which carries only
     {ok, task_count, tag, backend} and has NO "tasks" key (backend.py:409-419,
     735-738). Test #2 is the regression guard for the disk-vs-result bug.

Spec: docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md §9.3
Skill: AI-golden-parity-refactor
"""

import json
from pathlib import Path

from tests.parity.golden_parity import (
    diff_graphs,
    extract_graph_from_disk,
    normalize_graph,
)


def _graph(*titles):
    return {
        "tasks": [
            {
                "id": i + 1,
                "title": t,
                "description": f"desc {t}",
                "details": "volatile per-run details that must be ignored",
                "testStrategy": "volatile too",
                "status": "pending",
                "dependencies": [],
                "priority": "high",
                "subtasks": [],
            }
            for i, t in enumerate(titles)
        ]
    }


def test_normalize_keeps_structural_fields_drops_volatile():
    norm = normalize_graph(_graph("Set up project", "Write tests"))
    assert norm == {
        "task_count": 2,
        "tasks": [
            {"id": 1, "title": "Set up project", "dependencies": [], "subtask_count": 0, "priority": "high"},
            {"id": 2, "title": "Write tests", "dependencies": [], "subtask_count": 0, "priority": "high"},
        ],
    }
    # details / testStrategy / description must NOT appear — they are prose that
    # legitimately differs run-to-run and is not a parity signal.
    assert "details" not in norm["tasks"][0]
    assert "description" not in norm["tasks"][0]


def test_diff_identical_graphs_is_clean():
    a = normalize_graph(_graph("A", "B"))
    b = normalize_graph(_graph("A", "B"))
    result = diff_graphs(a, b)
    assert result["parity"] is True
    assert result["diffs"] == []


def test_diff_reports_task_count_mismatch():
    a = normalize_graph(_graph("A", "B"))
    b = normalize_graph(_graph("A"))
    result = diff_graphs(a, b)
    assert result["parity"] is False
    assert any("task_count" in d for d in result["diffs"])


def test_diff_reports_dependency_shape_change():
    g1 = _graph("A", "B")
    g2 = _graph("A", "B")
    g2["tasks"][1]["dependencies"] = [1]
    result = diff_graphs(normalize_graph(g1), normalize_graph(g2))
    assert result["parity"] is False
    assert any("dependencies" in d for d in result["diffs"])


def test_diff_honors_intended_whitelist():
    """A pre-declared intended diff (e.g. a deliberate title rephrase on task 2)
    is allowed and does NOT fail parity — per the skill, declare the whitelist
    BEFORE running."""
    a = normalize_graph(_graph("A", "B"))
    g2 = _graph("A", "B-renamed")
    b = normalize_graph(g2)
    result = diff_graphs(a, b, intended={"tasks[1].title"})
    assert result["parity"] is True
    assert result["intended_applied"] == ["tasks[1].title"]


def test_diff_empty_vs_empty_fails_gate():
    """Empty-vs-empty must NOT pass the parity gate.

    Two empty graphs compare structurally equal, but passing them means
    capture produced no tasks at all — which is a broken capture, not parity.
    The gate must fail with a clear reason for both sides.
    """
    empty = normalize_graph({"tasks": []})
    result = diff_graphs(empty, empty)
    assert result["parity"] is False
    assert any("empty graph" in d and "gold" in d for d in result["diffs"])
    assert any("empty graph" in d and "new" in d for d in result["diffs"])


def test_diff_empty_gold_fails_gate():
    """An empty gold graph must fail the gate even when new has tasks."""
    empty = normalize_graph({"tasks": []})
    populated = normalize_graph(_graph("A", "B"))
    result = diff_graphs(empty, populated)
    assert result["parity"] is False
    assert any("empty graph" in d and "gold" in d for d in result["diffs"])


def test_diff_empty_new_fails_gate():
    """An empty new graph must fail the gate even when gold has tasks."""
    populated = normalize_graph(_graph("A", "B"))
    empty = normalize_graph({"tasks": []})
    result = diff_graphs(populated, empty)
    assert result["parity"] is False
    assert any("empty graph" in d and "new" in d for d in result["diffs"])


def test_extract_reads_tasks_from_disk_not_from_parse_result(tmp_path, monkeypatch):
    """REGRESSION GUARD for the disk-vs-result bug: parse_prd returns a dict with
    {ok, task_count} and NO "tasks"/"raw" key (backend.py:409-419, 735-738).
    extract_graph_from_disk must read the graph from .taskmaster/tasks/tasks.json
    via parallel.load_tagged + parallel.get_tasks — NOT from the result dict.

    We simulate a completed parse: write a realistic parse_prd-shaped result dict
    (no "tasks" key) AND a tasks.json on disk, then assert the extractor returns
    the DISK tasks and would have returned nothing useful from the result dict.
    """
    monkeypatch.chdir(tmp_path)
    tm = tmp_path / ".taskmaster" / "tasks"
    tm.mkdir(parents=True)
    (tmp_path / ".taskmaster" / "state.json").write_text(json.dumps({"currentTag": "master"}))
    disk_tasks = [
        {"id": 1, "title": "From disk A", "dependencies": [], "priority": "high", "subtasks": []},
        {"id": 2, "title": "From disk B", "dependencies": [1], "priority": "medium", "subtasks": []},
    ]
    (tm / "tasks.json").write_text(json.dumps({"master": {"tasks": disk_tasks}}, indent=2))

    # Exactly the shape both backends return — NO "tasks", NO "raw".
    parse_result = {"ok": True, "task_count": 2, "tag": "master", "backend": "native", "ai": "api"}
    assert "tasks" not in parse_result and "raw" not in parse_result  # the trap

    graph = extract_graph_from_disk(parse_result)
    assert [t["title"] for t in graph["tasks"]] == ["From disk A", "From disk B"]
    # And the normalized shape reflects the on-disk dependency edge, proving we
    # did not silently fall back to an empty list from the result dict.
    norm = normalize_graph(graph)
    assert norm["task_count"] == 2
    assert norm["tasks"][1]["dependencies"] == [1]
