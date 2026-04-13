"""Edge case and integration tests for prd-taskmaster.

Tests boundary conditions, malformed inputs, and cross-subcommand workflows
that exercise real production paths.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPT_PY, EXPAND_SCRIPT_PY, run_script


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationEdgeCases:
    """Edge cases for PRD validation — the most critical code path."""

    def test_validate_prd_with_only_vague_language(self, tmp_path):
        """PRD with maximum vague language gets maximum penalty."""
        prd = tmp_path / "vague.md"
        prd.write_text("""# PRD: Vague Feature

## Executive Summary
We need something fast, secure, scalable, flexible, and performant.
It should be user-friendly and easy to use. The system needs to be good
and not bad or poor. It should be simple and efficient and quick.

## Problem Statement
Users need something secure and safe.

## Goals
Make it fast and good.

## Requirements
The system should be fast.
It must be secure.
It needs to be scalable and flexible and performant and efficient.
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        assert rc == 0
        assert out["vague_penalty"] == 5  # capped at 5
        vague_warnings = [w for w in out["warnings"] if w["type"] == "vague_language"]
        assert len(vague_warnings) >= 5

    def test_validate_section_heading_levels(self, tmp_path):
        """Sections at different heading levels are detected."""
        prd = tmp_path / "levels.md"
        prd.write_text("""# Top Level

## Executive Summary
This is a 50 word executive summary that should pass validation.
It describes the feature we are building and why it matters to users.
The goal is to improve performance metrics by 50% within 30 days of launch.

### Goals
metric: baseline 100, target 200, timeframe 30 days, measurement automated

#### Technical
The architecture uses a microservice design pattern with component isolation.
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        assert rc == 0
        # Executive Summary at ## level should be found
        check1 = next(c for c in out["checks"] if c["id"] == 1)
        assert check1["passed"] is True

    def test_validate_req_numbering_deduplication(self, tmp_path):
        """Duplicate REQ-NNN entries are counted once."""
        prd = tmp_path / "dupes.md"
        prd.write_text("""# PRD

## Requirements
REQ-001: First requirement
REQ-001: Same number used again
REQ-002: Second requirement
REQ-002: Duplicate
REQ-003: Third
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        check8 = next(c for c in out["checks"] if c["id"] == 8)
        assert check8["passed"] is True
        assert "3" in check8["detail"]  # 3 unique REQ numbers

    def test_validate_user_stories_fewer_than_3_ac(self, tmp_path):
        """Stories with fewer than 3 acceptance criteria fail check 5."""
        prd = tmp_path / "few_ac.md"
        prd.write_text("""# PRD

## User Stories

### Story 1: Basic flow
As a user I want to login.
- [ ] Can enter username
- [ ] Can enter password

### Story 2: Another flow
As a user I want to logout.
- [ ] Can click logout
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        check5 = next(c for c in out["checks"] if c["id"] == 5)
        assert check5["passed"] is False

    def test_validate_scoring_math(self, tmp_path):
        """Score = sum of passed check points - vague penalty, clamped to 0."""
        prd = tmp_path / "math.md"
        # Write a PRD that passes some checks and has vague language
        prd.write_text("""# PRD

## Executive Summary
This is a fast, secure, scalable, flexible, performant, efficient system
that we need to build for users who are affected by poor performance.
The business impact includes significant revenue loss of $50K/month. We need
to improve metrics from baseline 100 to target 200 within 30 days measurement.

## Problem Statement
### User Impact
Users are affected by slow response times.
### Business Impact
Revenue loss of $50K/month due to poor strategic alignment.

## Goals
metric: baseline 100, target 200, timeframe 30, measurement automated

## Functional Requirements
Must have: REQ-001 system should be fast
P0 priority

## Technical
architecture and system design for component integration

## Out of Scope
Nothing is out of scope for now and forever and always and then some more text.
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        assert rc == 0
        passed_points = sum(c["points"] for c in out["checks"] if c["passed"])
        expected_score = max(0, passed_points - out["vague_penalty"])
        assert out["score"] == expected_score

    def test_validate_percentage_calculation(self, tmp_path):
        """Percentage is correctly calculated from score/max_score."""
        prd = tmp_path / "pct.md"
        prd.write_text("# Empty-ish PRD")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        expected_pct = round(out["score"] / out["max_score"] * 100, 1) if out["max_score"] > 0 else 0
        assert out["percentage"] == expected_pct

    def test_validate_nfr_units_recognized(self, tmp_path):
        """Various unit formats are recognized in NFR targets."""
        prd = tmp_path / "nfr.md"
        prd.write_text("""# PRD

## Non-Functional Requirements
- Response time under 200ms
- Support 1000 requests/s
- Storage limit 500MB
- Uptime 99.9%
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        check10 = next(c for c in out["checks"] if c["id"] == 10)
        assert check10["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION EXTRACTION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestSectionExtractionEdges:
    """Edge cases for get_section_content helper."""

    @pytest.fixture(autouse=True)
    def _import_script(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("prd_script", str(SCRIPT_PY))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_nested_headings_stop_at_same_level(self):
        """Extraction stops at next same-level heading, not deeper."""
        text = "## Goals\nGoal 1\n### Sub-goal\nSub detail\n## Next Section\nOther"
        content = self.mod.get_section_content(text, "Goals")
        assert "Goal 1" in content
        assert "Sub-goal" in content
        assert "Sub detail" in content
        assert "Other" not in content

    def test_last_section_captures_to_end(self):
        """Last section captures everything to end of file."""
        text = "## First\nContent 1\n## Last\nContent 2\nMore content\nEnd"
        content = self.mod.get_section_content(text, "Last")
        assert "Content 2" in content
        assert "End" in content

    def test_partial_heading_match(self):
        """Partial matches in heading text work."""
        text = "## Technical Considerations and Architecture\nArch details"
        assert self.mod.has_section(text, "Technical") is True

    def test_heading_with_special_chars(self):
        """Headings with special characters are escaped properly."""
        text = "## Out of Scope (v1.0)\nNot building X"
        assert self.mod.has_section(text, "Out of Scope") is True


# ═══════════════════════════════════════════════════════════════════════════════
# TASK COUNT EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcTasksEdges:
    """Edge cases for task count calculation under the v4.1 formula."""

    def test_negative_requirements_clamps(self):
        """Negative input still clamps to minimum (floor 3)."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "-5"])
        assert rc == 0
        # base = max(1, ceil(-5/4)) = 1, adjust = 1.2 → raw 1.2 → clamped to 3
        assert out["recommended"] == 3

    def test_very_large_requirements(self):
        """Very large number clamps to ceiling 25."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "1000"])
        assert rc == 0
        # base = ceil(1000/4) = 250, adjust 1.2 → raw 300 → clamped to 25
        assert out["recommended"] == 25


# ═══════════════════════════════════════════════════════════════════════════════
# GEN-TEST-TASKS EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenTestTasksEdges:
    """Edge cases for test task generation."""

    def test_zero_tasks(self):
        """Zero implementation tasks = zero test tasks."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "0"])
        assert rc == 0
        assert out["test_tasks_generated"] == 0
        assert out["final_total"] == 0

    def test_large_task_count(self):
        """40 tasks produces 8 checkpoints."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "40"])
        assert rc == 0
        assert out["test_tasks_generated"] == 8
        assert out["final_total"] == 48

    def test_checkpoint_numbering_sequential(self):
        """Checkpoint numbers are sequential starting from 1."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "20"])
        for i, task in enumerate(out["tasks"]):
            assert task["checkpoint_number"] == i + 1

    def test_task_ranges_non_overlapping(self):
        """Task coverage ranges don't overlap."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "20"])
        ranges = [t["covers_tasks"] for t in out["tasks"]]
        assert ranges == ["1-5", "6-10", "11-15", "16-20"]


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end workflows across multiple subcommands."""

    def test_full_workflow_preflight_to_validate(self, tmp_project, sample_prd, sample_tasks_json):
        """Complete workflow: preflight -> validate -> calc-tasks -> gen-test-tasks."""
        # Step 1: Preflight
        rc, preflight = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert preflight["has_taskmaster"] is True
        assert preflight["prd_path"] is not None

        # Step 2: Validate the PRD
        rc, validation = run_script(SCRIPT_PY, ["validate-prd", "--input", preflight["prd_path"]])
        assert rc == 0
        assert validation["grade"] in ("EXCELLENT", "GOOD", "ACCEPTABLE")

        # Step 3: Calculate tasks based on requirement count
        # Our sample PRD has REQ-001 through REQ-006
        rc, calc = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "6"])
        assert rc == 0

        # Step 4: Generate test tasks
        rc, test_tasks = run_script(SCRIPT_PY, [
            "gen-test-tasks", "--total", str(calc["recommended"])
        ])
        assert rc == 0
        assert test_tasks["test_tasks_generated"] > 0

    def test_backup_then_validate_backup(self, sample_prd):
        """Backup creates a file that validates identically to original."""
        # Validate original
        rc, original_validation = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        assert rc == 0

        # Create backup
        rc, backup = run_script(SCRIPT_PY, ["backup-prd", "--input", str(sample_prd)])
        assert rc == 0

        # Validate backup — should have identical results
        rc, backup_validation = run_script(SCRIPT_PY, ["validate-prd", "--input", backup["backup_path"]])
        assert rc == 0
        assert backup_validation["score"] == original_validation["score"]
        assert backup_validation["grade"] == original_validation["grade"]

    def test_gen_scripts_then_full_lifecycle(self, tmp_path):
        """Generated scripts work together: start -> complete -> accuracy."""
        # Generate scripts
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        # Start tracking task 1
        subprocess.run(
            [sys.executable, str(output_dir / "track-time.py"), "start", "1"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )

        # Complete task 1
        result = subprocess.run(
            [sys.executable, str(output_dir / "track-time.py"), "complete", "1"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        complete_out = json.loads(result.stdout)
        assert complete_out["ok"] is True

        # Check accuracy analysis
        result = subprocess.run(
            [sys.executable, str(output_dir / "learn-accuracy.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        accuracy_out = json.loads(result.stdout)
        assert accuracy_out["ok"] is True
        assert accuracy_out["tasks_analyzed"] == 1

    def test_expand_tasks_end_to_end(self, tmp_path):
        """Full expand-tasks workflow: read -> gen-prompt -> write-research -> status."""
        # Create tasks.json
        data = {
            "tasks": [
                {"id": 1, "title": "Build API", "description": "REST API for auth", "dependencies": []},
                {"id": 2, "title": "Write tests", "description": "Unit tests", "dependencies": [1]},
            ]
        }
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps(data))

        # Step 1: Read tasks
        rc, read_out = run_script(EXPAND_SCRIPT_PY, ["read-tasks", "--file", str(tasks_path)])
        assert rc == 0
        assert read_out["pending_expansion"] == 2

        # Step 2: Generate prompt for task 1
        rc, prompt_out = run_script(EXPAND_SCRIPT_PY, [
            "gen-prompt", "--task-id", "1", "--file", str(tasks_path),
        ])
        assert rc == 0
        assert "Build API" in prompt_out["prompt"]

        # Step 3: Write research for task 1
        research_file = tmp_path / "research.md"
        research_file.write_text("## Research: Build API\n\nUse FastAPI with Pydantic v2.")
        rc, write_out = run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_path),
        ])
        assert rc == 0

        # Step 4: Check status
        rc, status_out = run_script(EXPAND_SCRIPT_PY, ["status", "--file", str(tasks_path)])
        assert rc == 0
        assert status_out["expanded"] == 1
        assert status_out["pending"] == 1
        assert status_out["all_expanded"] is False

    def test_preflight_reflects_logged_progress(self, tmp_project, sample_tasks_json):
        """Preflight and log-progress work together correctly."""
        # Log progress for a task
        run_script(SCRIPT_PY, [
            "log-progress", "--task-id", "1", "--title", "Auth scaffold",
            "--duration", "1h30m", "--tests", "5 passed",
        ], cwd=str(tmp_project))

        # Verify progress file exists
        progress = tmp_project / ".taskmaster" / "docs" / "progress.md"
        assert progress.exists()
        assert "Auth scaffold" in progress.read_text()

    def test_execution_state_lifecycle(self, tmp_path):
        """Execution state tracks full task lifecycle."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        es = str(output_dir / "execution-state.py")

        # Status: empty
        r = subprocess.run([sys.executable, es, "status"], capture_output=True, text=True, cwd=str(tmp_path))
        assert json.loads(r.stdout)["has_incomplete"] is False

        # Start task 1
        r = subprocess.run([sys.executable, es, "start", "1", "1.1", "sequential"],
                          capture_output=True, text=True, cwd=str(tmp_path))

        # Status: in progress
        r = subprocess.run([sys.executable, es, "status"], capture_output=True, text=True, cwd=str(tmp_path))
        assert json.loads(r.stdout)["has_incomplete"] is True

        # Complete task 1
        r = subprocess.run([sys.executable, es, "complete", "1"],
                          capture_output=True, text=True, cwd=str(tmp_path))

        # Status: idle
        r = subprocess.run([sys.executable, es, "status"], capture_output=True, text=True, cwd=str(tmp_path))
        out = json.loads(r.stdout)
        assert out["has_incomplete"] is False
        assert "1" in out.get("completed_tasks", [])


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestTemplateValidation:
    """Verify templates are valid and contain required content."""

    def test_comprehensive_template_validates_well(self):
        """Comprehensive template structure should enable high validation scores."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "comprehensive"])
        assert rc == 0
        content = out["content"]
        # Template should have all required sections
        required_sections = [
            "Executive Summary",
            "Problem",
            "Goals",
            "Requirements",
            "Technical",
            "Out of Scope",
        ]
        for section in required_sections:
            assert section in content, f"Template missing section: {section}"

    def test_comprehensive_template_has_req_placeholders(self):
        """Template has REQ-NNN placeholder format."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "comprehensive"])
        assert "REQ-" in out["content"]

    def test_minimal_template_is_usable(self):
        """Minimal template has minimum viable structure."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "minimal"])
        content = out["content"]
        assert "Requirements" in content
        assert "REQ-" in content
        assert "Out of Scope" in content

    def test_templates_are_different(self):
        """Comprehensive and minimal templates are meaningfully different."""
        _, comp = run_script(SCRIPT_PY, ["load-template", "--type", "comprehensive"])
        _, mini = run_script(SCRIPT_PY, ["load-template", "--type", "minimal"])
        # Comprehensive should be at least 3x longer
        assert len(comp["content"]) > len(mini["content"]) * 3
