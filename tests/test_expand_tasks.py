"""Tests for companion-skills/expand-tasks/script.py.

Tests read-tasks, gen-prompt, write-research, and status subcommands
with real tasks.json files and real file I/O.
"""

import json
import sys
import subprocess
from pathlib import Path

import pytest

from conftest import EXPAND_SCRIPT_PY, run_script


@pytest.fixture
def tasks_json_flat(tmp_path):
    """Create a flat tasks.json (top-level tasks array)."""
    data = {
        "tasks": [
            {
                "id": 1,
                "title": "Setup database migrations",
                "description": "Create initial schema for user_2fa and backup_codes tables",
                "status": "pending",
                "dependencies": [],
                "subtasks": [
                    {"id": "1.1", "title": "Design schema"},
                    {"id": "1.2", "title": "Write migration files"},
                ],
            },
            {
                "id": 2,
                "title": "Implement TOTP service",
                "description": "Build TOTP verification using pyotp library",
                "status": "pending",
                "dependencies": [1],
                "subtasks": [],
            },
            {
                "id": 3,
                "title": "Build SMS integration",
                "description": "Twilio Verify API integration",
                "status": "done",
                "dependencies": [1],
                "research_notes": "Already researched Twilio",
                "subtasks": [],
            },
        ]
    }
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data, indent=2))
    return path


@pytest.fixture
def tasks_json_nested(tmp_path):
    """Create a nested tasks.json (master.tasks structure)."""
    data = {
        "master": {
            "tasks": [
                {"id": 1, "title": "Task A", "description": "Desc A", "dependencies": []},
                {"id": 2, "title": "Task B", "description": "Desc B", "dependencies": [1]},
            ]
        }
    }
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data, indent=2))
    return path


@pytest.fixture
def tasks_json_list(tmp_path):
    """Create a bare list tasks.json (no wrapper object)."""
    data = [
        {"id": 1, "title": "Solo Task", "description": "Just a list", "dependencies": []},
    ]
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data, indent=2))
    return path


@pytest.fixture
def prd_file(tmp_path):
    """Create a PRD file for gen-prompt context."""
    content = "# PRD: Auth System\n\n## Executive Summary\nBuild 2FA for security.\n\n## Requirements\nREQ-001: TOTP support\n"
    path = tmp_path / "prd.md"
    path.write_text(content)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# READ-TASKS
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadTasks:
    """Test read-tasks subcommand."""

    def test_read_tasks_flat(self, tasks_json_flat):
        """Reads flat tasks.json and returns correct counts."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_json_flat)])
        assert rc == 0
        assert out["total"] == 3
        assert out["expanded"] == 1  # task 3 has research_notes
        assert out["pending_expansion"] == 2

    def test_read_tasks_nested(self, tasks_json_nested):
        """Reads nested master.tasks structure."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_json_nested)])
        assert rc == 0
        assert out["total"] == 2
        assert out["expanded"] == 0
        assert out["pending_expansion"] == 2

    def test_read_tasks_bare_list(self, tasks_json_list):
        """Reads bare list tasks.json."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_json_list)])
        assert rc == 0
        assert out["total"] == 1

    def test_read_tasks_missing_file(self, tmp_path):
        """Reports error for missing file."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tmp_path / "nope.json")])
        assert rc == 1
        assert "error" in out

    def test_read_tasks_task_metadata(self, tasks_json_flat):
        """Each task includes correct metadata fields."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_json_flat)])
        task1 = next(t for t in out["tasks"] if t["id"] == 1)
        assert task1["title"] == "Setup database migrations"
        assert task1["status"] == "pending"
        assert task1["has_research"] is False
        assert task1["subtask_count"] == 2
        assert task1["dependencies"] == []

    def test_read_tasks_dependencies_stringified(self, tasks_json_flat):
        """Dependencies are converted to strings."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_json_flat)])
        task2 = next(t for t in out["tasks"] if t["id"] == 2)
        assert task2["dependencies"] == ["1"]  # int 1 -> str "1"


# ═══════════════════════════════════════════════════════════════════════════════
# GEN-PROMPT
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenPrompt:
    """Test gen-prompt subcommand."""

    def test_gen_prompt_basic(self, tasks_json_flat):
        """Generates a research prompt for a valid task."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "1", "--file", str(tasks_json_flat),
        ])
        assert rc == 0
        assert out["task_id"] == 1
        assert out["title"] == "Setup database migrations"
        assert "prompt" in out
        assert len(out["prompt"]) > 100
        assert "research_questions" in out
        assert len(out["research_questions"]) == 5

    def test_gen_prompt_includes_task_context(self, tasks_json_flat):
        """Prompt includes task description and title."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "1", "--file", str(tasks_json_flat),
        ])
        prompt = out["prompt"]
        assert "Setup database migrations" in prompt
        assert "initial schema" in prompt

    def test_gen_prompt_includes_dependencies(self, tasks_json_flat):
        """Prompt for task with dependencies includes dependency context."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "2", "--file", str(tasks_json_flat),
        ])
        prompt = out["prompt"]
        assert "DEPENDENCY" in prompt or "Task 1" in prompt

    def test_gen_prompt_includes_subtasks(self, tasks_json_flat):
        """Prompt for task with subtasks includes subtask list."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "1", "--file", str(tasks_json_flat),
        ])
        prompt = out["prompt"]
        assert "Design schema" in prompt
        assert "Write migration files" in prompt

    def test_gen_prompt_with_prd(self, tasks_json_flat, prd_file):
        """Prompt includes PRD context when --prd points to existing file."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "1",
            "--file", str(tasks_json_flat),
            "--prd", str(prd_file),
        ])
        prompt = out["prompt"]
        assert "PRD CONTEXT" in prompt
        assert "Auth System" in prompt

    def test_gen_prompt_invalid_task_id(self, tasks_json_flat):
        """Returns error for non-existent task ID."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "999", "--file", str(tasks_json_flat),
        ])
        assert rc == 1
        assert "error" in out

    def test_gen_prompt_research_questions_relevant(self, tasks_json_flat):
        """Research questions include the task title for relevance."""
        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "2", "--file", str(tasks_json_flat),
        ])
        for q in out["research_questions"]:
            assert "Implement TOTP service" in q


# ═══════════════════════════════════════════════════════════════════════════════
# WRITE-RESEARCH
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteResearch:
    """Test write-research subcommand."""

    def test_write_research_basic(self, tasks_json_flat, tmp_path):
        """Writes research content back into the task."""
        research_file = tmp_path / "research.md"
        research_file.write_text("## Research Findings\n\nUse pyotp for TOTP.\n")

        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_json_flat),
        ])
        assert rc == 0
        assert out["success"] is True
        assert out["research_length"] > 0

        # Verify the file was actually updated
        updated = json.loads(tasks_json_flat.read_text())
        task1 = next(t for t in updated["tasks"] if t["id"] == 1)
        assert task1["research_notes"] == "## Research Findings\n\nUse pyotp for TOTP.\n"
        assert task1["_research_expanded"] is True

    def test_write_research_appends_to_details(self, tasks_json_flat, tmp_path):
        """Research is appended to existing details."""
        # First set some existing details
        data = json.loads(tasks_json_flat.read_text())
        data["tasks"][0]["details"] = "Existing implementation notes"
        tasks_json_flat.write_text(json.dumps(data))

        research_file = tmp_path / "research.md"
        research_file.write_text("New research findings")

        run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_json_flat),
        ])

        updated = json.loads(tasks_json_flat.read_text())
        task1 = next(t for t in updated["tasks"] if t["id"] == 1)
        assert "Existing implementation notes" in task1["details"]
        assert "New research findings" in task1["details"]

    def test_write_research_invalid_task(self, tasks_json_flat, tmp_path):
        """Returns error for non-existent task ID."""
        research_file = tmp_path / "research.md"
        research_file.write_text("Some research")

        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "999",
            "--research", str(research_file),
            "--file", str(tasks_json_flat),
        ])
        assert rc == 1
        assert "error" in out

    def test_write_research_preserves_other_tasks(self, tasks_json_flat, tmp_path):
        """Writing research to one task doesn't modify others."""
        original = json.loads(tasks_json_flat.read_text())
        task2_before = json.dumps(next(t for t in original["tasks"] if t["id"] == 2))

        research_file = tmp_path / "research.md"
        research_file.write_text("Research for task 1 only")

        run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_json_flat),
        ])

        updated = json.loads(tasks_json_flat.read_text())
        task2_after = json.dumps(next(t for t in updated["tasks"] if t["id"] == 2))
        assert task2_before == task2_after

    def test_write_research_nested_structure(self, tasks_json_nested, tmp_path):
        """Works with nested master.tasks structure."""
        research_file = tmp_path / "research.md"
        research_file.write_text("Nested research")

        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_json_nested),
        ])
        assert rc == 0

        updated = json.loads(tasks_json_nested.read_text())
        task1 = next(t for t in updated["master"]["tasks"] if t["id"] == 1)
        assert task1["research_notes"] == "Nested research"


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatus:
    """Test status subcommand."""

    def test_status_mixed(self, tasks_json_flat):
        """Shows correct expanded vs pending counts."""
        rc, out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(tasks_json_flat)])
        assert rc == 0
        assert out["total"] == 3
        assert out["expanded"] == 1  # task 3 has research_notes
        assert out["pending"] == 2
        assert out["all_expanded"] is False

    def test_status_all_expanded(self, tmp_path):
        """Reports all_expanded when every task has research."""
        data = {
            "tasks": [
                {"id": 1, "title": "A", "research_notes": "Done"},
                {"id": 2, "title": "B", "_research_expanded": True},
            ]
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(data))

        rc, out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(path)])
        assert rc == 0
        assert out["all_expanded"] is True
        assert out["pending"] == 0

    def test_status_empty_tasks(self, tmp_path):
        """Handles empty tasks list."""
        data = {"tasks": []}
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(data))

        rc, out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(path)])
        assert rc == 0
        assert out["total"] == 0
        assert out["all_expanded"] is True  # vacuously true

    def test_status_after_write_research(self, tasks_json_flat, tmp_path):
        """Status reflects changes after write-research."""
        # Before: 1 expanded
        rc, out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(tasks_json_flat)])
        assert out["expanded"] == 1

        # Write research to task 1
        research_file = tmp_path / "research.md"
        research_file.write_text("New research")
        run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_json_flat),
        ])

        # After: 2 expanded
        rc, out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(tasks_json_flat)])
        assert out["expanded"] == 2
