"""Tests for script.py — all 11 subcommands with real file I/O.

Every test creates real files, runs the real script, and validates real JSON output.
No mocking. No smoke tests. Real behavior verification.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPT_PY, TEMPLATE_DIR, run_script


# ═══════════════════════════════════════════════════════════════════════════════
# PREFLIGHT
# ═══════════════════════════════════════════════════════════════════════════════


class TestPreflight:
    """Test cmd_preflight — environment detection."""

    def test_preflight_empty_directory(self, tmp_path):
        """In an empty dir, preflight reports no taskmaster, no PRD, no crash."""
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_path))
        assert rc == 0
        assert out["ok"] is True
        assert out["has_taskmaster"] is False
        assert out["prd_path"] is None
        assert out["task_count"] == 0
        assert out["tasks_completed"] == 0
        assert out["tasks_pending"] == 0
        assert out["has_crash_state"] is False
        assert out["crash_state"] is None

    def test_preflight_with_taskmaster_and_prd(self, tmp_project, sample_prd):
        """Detects existing .taskmaster dir and PRD file."""
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["ok"] is True
        assert out["has_taskmaster"] is True
        assert out["prd_path"] is not None
        assert "prd.md" in out["prd_path"]

    def test_preflight_with_tasks(self, tmp_project, sample_tasks_json):
        """Detects task counts from tasks.json."""
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["task_count"] == 3
        assert out["tasks_completed"] == 1  # task 3 is "done"
        assert out["tasks_pending"] == 2

    def test_preflight_with_crash_state(self, tmp_project, execution_state):
        """Detects in-progress crash state."""
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["has_crash_state"] is True
        assert out["crash_state"]["last_task"] == "3"
        assert out["crash_state"]["last_subtask"] == "3.2"
        assert out["crash_state"]["mode"] == "sequential"
        assert out["crash_state"]["checkpoint"] == "2"

    def test_preflight_detects_claude_md(self, tmp_project):
        """Detects CLAUDE.md in project root."""
        (tmp_project / "CLAUDE.md").write_text("# Project guide")
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["has_claude_md"] is True

    def test_preflight_no_claude_md(self, tmp_project):
        """Reports missing CLAUDE.md."""
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["has_claude_md"] is False

    def test_preflight_malformed_tasks_json(self, tmp_project):
        """Handles malformed tasks.json gracefully."""
        tasks_path = tmp_project / ".taskmaster" / "tasks" / "tasks.json"
        tasks_path.write_text("not valid json {{{")
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["ok"] is True
        assert out["task_count"] == 0  # graceful fallback

    def test_preflight_completed_execution_state(self, tmp_project):
        """Completed execution state should NOT report as crash."""
        state = {"status": "idle", "current_task": None, "last_checkpoint": "5"}
        state_path = tmp_project / ".taskmaster" / "state" / "execution-state.json"
        state_path.write_text(json.dumps(state))
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd=str(tmp_project))
        assert rc == 0
        assert out["has_crash_state"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# DETECT-TASKMASTER
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectTaskmaster:
    """Test cmd_detect_taskmaster — MCP/CLI/none detection."""

    def test_detect_returns_valid_json(self, tmp_path):
        """Always returns valid JSON with method field."""
        rc, out = run_script(SCRIPT_PY, ["detect-taskmaster"], cwd=str(tmp_path))
        assert rc == 0
        assert out["ok"] is True
        assert out["method"] in ("mcp", "cli", "none")

    def test_detect_mcp_from_dotmcp(self, tmp_path):
        """Detects MCP when .mcp.json has task-master entry."""
        mcp_config = {
            "mcpServers": {
                "task-master-ai": {"command": "npx", "args": ["task-master-ai"]}
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp_config))
        rc, out = run_script(SCRIPT_PY, ["detect-taskmaster"], cwd=str(tmp_path))
        assert rc == 0
        assert out["method"] == "mcp"


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD-TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadTemplate:
    """Test cmd_load_template — template loading."""

    def test_load_comprehensive_template(self):
        """Loads comprehensive template with real content."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "comprehensive"])
        assert rc == 0
        assert out["ok"] is True
        assert out["type"] == "comprehensive"
        assert "content" in out
        assert len(out["content"]) > 1000  # comprehensive template is substantial
        assert out["line_count"] > 50
        # Verify template has expected placeholder structure
        assert "Executive Summary" in out["content"]
        assert "REQ-" in out["content"]

    def test_load_minimal_template(self):
        """Loads minimal template — shorter but valid."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "minimal"])
        assert rc == 0
        assert out["ok"] is True
        assert out["type"] == "minimal"
        assert len(out["content"]) > 100
        assert len(out["content"]) < len(
            run_script(SCRIPT_PY, ["load-template", "--type", "comprehensive"])[1]["content"]
        )

    def test_load_invalid_template_type(self):
        """Rejects invalid template type with error."""
        rc, out = run_script(SCRIPT_PY, ["load-template", "--type", "nonexistent"])
        # argparse rejects invalid choices before our code runs
        assert rc != 0


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATE-PRD
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatePrd:
    """Test cmd_validate_prd — the 14-check quality validation.

    v4 added check 14 (placeholder reason attribution) per inbox 1559.
    Max score = 9*5 (required) + 4*3 (taskmaster-specific) + 1*5 (check 14) = 62.
    """

    def test_validate_comprehensive_prd(self, sample_prd):
        """Well-crafted PRD scores EXCELLENT."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        assert rc == 0
        assert out["ok"] is True
        assert out["checks_total"] == 14  # v4: added check 14
        assert out["grade"] in ("EXCELLENT", "GOOD")
        assert out["score"] > 0
        assert out["max_score"] == 62  # 9*5 + 4*3 + 1*5

    def test_validate_checks_executive_summary(self, sample_prd):
        """Check 1: Executive summary exists and has appropriate length."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check1 = next(c for c in out["checks"] if c["id"] == 1)
        assert check1["passed"] is True
        assert check1["category"] == "required"
        assert "words" in check1["detail"].lower()

    def test_validate_checks_user_impact(self, sample_prd):
        """Check 2: Problem statement includes user impact."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check2 = next(c for c in out["checks"] if c["id"] == 2)
        assert check2["passed"] is True

    def test_validate_checks_business_impact(self, sample_prd):
        """Check 3: Problem statement includes business impact."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check3 = next(c for c in out["checks"] if c["id"] == 3)
        assert check3["passed"] is True

    def test_validate_checks_smart_goals(self, sample_prd):
        """Check 4: Goals have SMART metrics."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check4 = next(c for c in out["checks"] if c["id"] == 4)
        assert check4["passed"] is True

    def test_validate_checks_user_stories_ac(self, sample_prd):
        """Check 5: User stories have acceptance criteria (min 3)."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check5 = next(c for c in out["checks"] if c["id"] == 5)
        assert check5["passed"] is True

    def test_validate_checks_testable_requirements(self, sample_prd):
        """Check 6: Functional requirements are testable (no vague language)."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check6 = next(c for c in out["checks"] if c["id"] == 6)
        # Our sample PRD uses specific, measurable language — no vague terms
        assert check6["passed"] is True
        assert "specific" in check6["detail"].lower() or "vague" not in check6["detail"].lower()

    def test_validate_checks_priority_labels(self, sample_prd):
        """Check 7: Requirements have priority labels."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check7 = next(c for c in out["checks"] if c["id"] == 7)
        assert check7["passed"] is True

    def test_validate_checks_req_numbering(self, sample_prd):
        """Check 8: Requirements are numbered (REQ-NNN)."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check8 = next(c for c in out["checks"] if c["id"] == 8)
        assert check8["passed"] is True
        assert "6" in check8["detail"]  # we have REQ-001 through REQ-006

    def test_validate_checks_architecture(self, sample_prd):
        """Check 9: Technical considerations address architecture."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check9 = next(c for c in out["checks"] if c["id"] == 9)
        assert check9["passed"] is True

    def test_validate_checks_nfr_targets(self, sample_prd):
        """Check 10: Non-functional requirements have specific targets."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check10 = next(c for c in out["checks"] if c["id"] == 10)
        assert check10["passed"] is True
        assert check10["category"] == "taskmaster"

    def test_validate_checks_task_hints(self, sample_prd):
        """Check 11: Task breakdown hints exist."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check11 = next(c for c in out["checks"] if c["id"] == 11)
        assert check11["passed"] is True

    def test_validate_checks_dependencies(self, sample_prd):
        """Check 12: Dependencies identified."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check12 = next(c for c in out["checks"] if c["id"] == 12)
        assert check12["passed"] is True

    def test_validate_checks_out_of_scope(self, sample_prd):
        """Check 13: Out of scope section exists with content."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        check13 = next(c for c in out["checks"] if c["id"] == 13)
        assert check13["passed"] is True

    def test_validate_minimal_prd_scores_lower(self, minimal_prd):
        """Minimal/vague PRD scores significantly lower than comprehensive."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(minimal_prd)])
        assert rc == 0
        assert out["grade"] in ("NEEDS_WORK", "ACCEPTABLE")
        assert out["score"] < 40  # substantially lower

    def test_validate_vague_language_detected(self, minimal_prd):
        """Vague language warnings are generated."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(minimal_prd)])
        assert rc == 0
        assert len(out["warnings"]) > 0
        vague_warnings = [w for w in out["warnings"] if w["type"] == "vague_language"]
        assert len(vague_warnings) > 0
        # Our minimal PRD has "user-friendly", "fast", "performant"
        vague_terms = {w["term"].lower() for w in vague_warnings}
        assert "user-friendly" in vague_terms or "fast" in vague_terms or "performant" in vague_terms

    def test_validate_vague_penalty_applied(self, minimal_prd):
        """Vague language penalty reduces score."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(minimal_prd)])
        assert rc == 0
        assert out["vague_penalty"] > 0
        # Score should be less than sum of passed checks due to penalty
        passed_points = sum(c["points"] for c in out["checks"] if c["passed"])
        assert out["score"] <= passed_points

    def test_validate_missing_file_fails(self, tmp_path):
        """Non-existent file returns error."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(tmp_path / "nope.md")])
        assert rc == 1
        assert out["ok"] is False
        assert "not found" in out["error"].lower()

    def test_validate_empty_prd(self, tmp_project):
        """Empty PRD file gets lowest grade with most checks failing."""
        empty_prd = tmp_project / ".taskmaster" / "docs" / "prd.md"
        empty_prd.write_text("")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(empty_prd)])
        assert rc == 0
        assert out["grade"] == "NEEDS_WORK"
        # 4 checks pass vacuously on empty PRD:
        #   ch 5: no stories found → pass
        #   ch 6: no vague reqs → pass
        #   ch 10: no NFR section → pass
        #   ch 14: no placeholders → pass (v4 addition)
        assert out["checks_passed"] == 4
        assert out["score"] == 18  # 5 + 5 + 3 + 5

    def test_validate_grade_boundaries(self, tmp_project):
        """Verify grade boundary calculations match documented thresholds."""
        # Test each grade boundary with crafted PRDs
        # NEEDS_WORK: < 75% of 57 = < 42.75 points
        prd_path = tmp_project / ".taskmaster" / "docs" / "prd.md"

        # Empty PRD: 13 points / 57 max = 22.8% -> NEEDS_WORK
        prd_path.write_text("")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd_path)])
        assert out["grade"] == "NEEDS_WORK"
        assert out["percentage"] < 75

    def test_validate_grade_excellent_threshold(self, sample_prd):
        """Comprehensive PRD should achieve EXCELLENT (91%+) or GOOD (83%+)."""
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(sample_prd)])
        assert out["percentage"] >= 83  # At minimum GOOD
        assert out["grade"] in ("EXCELLENT", "GOOD")


# ═══════════════════════════════════════════════════════════════════════════════
# CALC-TASKS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcTasks:
    """Test cmd_calc_tasks — task count calculation."""

    def test_calc_tasks_formula(self):
        """Verify formula: ceil(requirements * 1.5), clamped [10, 40]."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "15"])
        assert rc == 0
        assert out["ok"] is True
        assert out["requirements_count"] == 15
        assert out["raw_calculation"] == 23  # ceil(15 * 1.5) = 23
        assert out["recommended"] == 23

    def test_calc_tasks_minimum_clamp(self):
        """Small requirement count clamps to minimum 10."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "3"])
        assert rc == 0
        assert out["raw_calculation"] == 5  # ceil(3 * 1.5) = 5
        assert out["recommended"] == 10  # clamped to minimum

    def test_calc_tasks_maximum_clamp(self):
        """Large requirement count clamps to maximum 40."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "50"])
        assert rc == 0
        assert out["raw_calculation"] == 75  # ceil(50 * 1.5) = 75
        assert out["recommended"] == 40  # clamped to maximum

    def test_calc_tasks_exact_boundary_10(self):
        """Requirements that produce exactly 10 tasks."""
        # ceil(7 * 1.5) = ceil(10.5) = 11, ceil(6 * 1.5) = 9 -> clamp to 10
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "6"])
        assert rc == 0
        assert out["recommended"] == 10  # 9 clamped to 10

    def test_calc_tasks_exact_boundary_40(self):
        """Requirements that produce exactly 40 tasks."""
        # ceil(27 * 1.5) = ceil(40.5) = 41 -> clamp to 40
        # ceil(26 * 1.5) = 39
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "26"])
        assert rc == 0
        assert out["recommended"] == 39  # just under clamp

    def test_calc_tasks_zero_requirements(self):
        """Zero requirements clamps to minimum."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "0"])
        assert rc == 0
        assert out["recommended"] == 10  # clamped

    def test_calc_tasks_one_requirement(self):
        """Single requirement clamps to minimum."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "1"])
        assert rc == 0
        assert out["raw_calculation"] == 2  # ceil(1.5) = 2
        assert out["recommended"] == 10


# ═══════════════════════════════════════════════════════════════════════════════
# GEN-TEST-TASKS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenTestTasks:
    """Test cmd_gen_test_tasks — USER-TEST checkpoint generation."""

    def test_gen_test_tasks_basic(self):
        """Generates one test task per 5 implementation tasks."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "15"])
        assert rc == 0
        assert out["ok"] is True
        assert out["total_implementation_tasks"] == 15
        assert out["test_tasks_generated"] == 3  # 15 / 5 = 3 checkpoints
        assert out["final_total"] == 18  # 15 + 3

    def test_gen_test_tasks_content_structure(self):
        """Generated tasks have correct structure and content."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "10"])
        tasks = out["tasks"]
        assert len(tasks) == 2

        # First checkpoint
        t1 = tasks[0]
        assert t1["checkpoint_number"] == 1
        assert t1["insert_after_task"] == 5
        assert t1["covers_tasks"] == "1-5"
        assert t1["priority"] == "high"
        assert "5" in t1["dependencies"]
        assert "USER-TEST-1" in t1["template"]
        assert "Tasks 1" in t1["template"]

    def test_gen_test_tasks_small_total(self):
        """Total < 5 produces zero test tasks."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "3"])
        assert rc == 0
        assert out["test_tasks_generated"] == 0
        assert out["final_total"] == 3

    def test_gen_test_tasks_exact_five(self):
        """Exactly 5 tasks produces 1 test task."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "5"])
        assert rc == 0
        assert out["test_tasks_generated"] == 1

    def test_gen_test_tasks_template_has_checklists(self):
        """Template includes testing checklists."""
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "10"])
        template = out["tasks"][0]["template"]
        assert "Functionality Tests" in template
        assert "Integration Tests" in template
        assert "Acceptance Criteria" in template
        assert "If Tests Fail" in template


# ═══════════════════════════════════════════════════════════════════════════════
# GEN-SCRIPTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenScripts:
    """Test cmd_gen_scripts — automation script generation."""

    def test_gen_scripts_creates_five_files(self, tmp_path):
        """Creates exactly 5 scripts in the output directory."""
        output_dir = tmp_path / "scripts"
        rc, out = run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        assert rc == 0
        assert out["ok"] is True
        assert out["count"] == 5
        expected = ["track-time.py", "rollback.sh", "learn-accuracy.py", "security-audit.py", "execution-state.py"]
        assert sorted(out["files_created"]) == sorted(expected)

    def test_gen_scripts_files_exist_on_disk(self, tmp_path):
        """All generated scripts actually exist as files."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        for name in ["track-time.py", "rollback.sh", "learn-accuracy.py", "security-audit.py", "execution-state.py"]:
            path = output_dir / name
            assert path.exists(), f"{name} not created"
            assert path.stat().st_size > 0, f"{name} is empty"

    def test_gen_scripts_are_executable(self, tmp_path):
        """Generated scripts have executable permissions."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        for name in ["track-time.py", "rollback.sh", "learn-accuracy.py", "security-audit.py", "execution-state.py"]:
            path = output_dir / name
            assert os.access(path, os.X_OK), f"{name} is not executable"

    def test_gen_scripts_track_time_runs(self, tmp_path):
        """track-time.py actually runs and tracks time."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        # Run track-time start
        result = subprocess.run(
            [sys.executable, str(output_dir / "track-time.py"), "start", "1"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        start_out = json.loads(result.stdout)
        assert start_out["ok"] is True
        assert start_out["action"] == "started"

        # Run track-time complete
        result = subprocess.run(
            [sys.executable, str(output_dir / "track-time.py"), "complete", "1"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        complete_out = json.loads(result.stdout)
        assert complete_out["ok"] is True
        assert complete_out["action"] == "completed"
        assert "duration" in complete_out

    def test_gen_scripts_execution_state_runs(self, tmp_path):
        """execution-state.py actually runs and manages state."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        # Start a task
        result = subprocess.run(
            [sys.executable, str(output_dir / "execution-state.py"), "start", "1", "1.1", "sequential"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["ok"] is True
        assert out["current_task"] == "1"

        # Check status
        result = subprocess.run(
            [sys.executable, str(output_dir / "execution-state.py"), "status"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["has_incomplete"] is True

    def test_gen_scripts_learn_accuracy_no_data(self, tmp_path):
        """learn-accuracy.py handles no data gracefully."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        result = subprocess.run(
            [sys.executable, str(output_dir / "learn-accuracy.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        # Should fail gracefully — no time tracking data
        out = json.loads(result.stdout)
        assert out["ok"] is False or out.get("count") == 0

    def test_gen_scripts_security_audit_runs(self, tmp_path):
        """security-audit.py runs and produces a checklist."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        # Create a dummy python file with patterns
        (tmp_path / "app.py").write_text("password = os.environ['DB_PASS']\nquery = 'SELECT * FROM users'")

        result = subprocess.run(
            [sys.executable, str(output_dir / "security-audit.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["ok"] is True
        assert len(out["checklist"]) > 0

    def test_gen_scripts_creates_parent_dirs(self, tmp_path):
        """Creates parent directories if they don't exist."""
        deep_dir = tmp_path / "a" / "b" / "c" / "scripts"
        rc, out = run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(deep_dir)])
        assert rc == 0
        assert deep_dir.exists()

    def test_gen_scripts_idempotent(self, tmp_path):
        """Running gen-scripts twice doesn't error."""
        output_dir = tmp_path / "scripts"
        rc1, _ = run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        rc2, out2 = run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])
        assert rc1 == 0
        assert rc2 == 0
        assert out2["count"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# BACKUP-PRD
# ═══════════════════════════════════════════════════════════════════════════════


class TestBackupPrd:
    """Test cmd_backup_prd — timestamped backup."""

    def test_backup_creates_file(self, sample_prd):
        """Creates a timestamped backup file."""
        rc, out = run_script(SCRIPT_PY, ["backup-prd", "--input", str(sample_prd)])
        assert rc == 0
        assert out["ok"] is True
        backup_path = Path(out["backup_path"])
        assert backup_path.exists()
        assert backup_path.name.startswith("prd-backup-")
        assert backup_path.name.endswith(".md")

    def test_backup_preserves_content(self, sample_prd):
        """Backup file has identical content to original."""
        original_content = sample_prd.read_text()
        rc, out = run_script(SCRIPT_PY, ["backup-prd", "--input", str(sample_prd)])
        backup_content = Path(out["backup_path"]).read_text()
        assert backup_content == original_content

    def test_backup_missing_file_fails(self, tmp_path):
        """Non-existent file returns error."""
        rc, out = run_script(SCRIPT_PY, ["backup-prd", "--input", str(tmp_path / "nope.md")])
        assert rc == 1
        assert out["ok"] is False

    def test_backup_multiple_creates_unique_files(self, sample_prd):
        """Multiple backups create files — both must exist after creation."""
        _, out1 = run_script(SCRIPT_PY, ["backup-prd", "--input", str(sample_prd)])
        import time; time.sleep(1.1)  # ensure different timestamp
        _, out2 = run_script(SCRIPT_PY, ["backup-prd", "--input", str(sample_prd)])
        assert Path(out1["backup_path"]).exists()
        assert Path(out2["backup_path"]).exists()
        assert out1["backup_path"] != out2["backup_path"]  # must be unique files


# ═══════════════════════════════════════════════════════════════════════════════
# READ-STATE
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadState:
    """Test cmd_read_state — crash recovery state reading."""

    def test_read_state_no_state(self, tmp_path):
        """No state file returns has_incomplete: False."""
        rc, out = run_script(SCRIPT_PY, ["read-state"], cwd=str(tmp_path))
        assert rc == 0
        assert out["ok"] is True
        assert out["has_incomplete"] is False

    def test_read_state_in_progress(self, tmp_project, execution_state):
        """In-progress state is correctly read."""
        rc, out = run_script(SCRIPT_PY, ["read-state"], cwd=str(tmp_project))
        assert rc == 0
        assert out["has_incomplete"] is True
        assert out["last_task"] == "3"
        assert out["mode"] == "sequential"


# ═══════════════════════════════════════════════════════════════════════════════
# LOG-PROGRESS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogProgress:
    """Test cmd_log_progress — progress entry appending."""

    def test_log_progress_creates_file(self, tmp_project):
        """Creates progress.md if it doesn't exist."""
        rc, out = run_script(SCRIPT_PY, [
            "log-progress",
            "--task-id", "1",
            "--title", "Setup auth service",
            "--duration", "2h 15m",
            "--subtasks", "3/3",
            "--tests", "12 passed",
        ], cwd=str(tmp_project))
        assert rc == 0
        assert out["ok"] is True
        progress_path = tmp_project / ".taskmaster" / "docs" / "progress.md"
        assert progress_path.exists()
        content = progress_path.read_text()
        assert "Setup auth service" in content
        assert "2h 15m" in content
        assert "12 passed" in content

    def test_log_progress_appends(self, tmp_project):
        """Multiple log entries append, don't overwrite."""
        run_script(SCRIPT_PY, [
            "log-progress", "--task-id", "1", "--title", "First task",
        ], cwd=str(tmp_project))
        run_script(SCRIPT_PY, [
            "log-progress", "--task-id", "2", "--title", "Second task",
        ], cwd=str(tmp_project))
        progress_path = tmp_project / ".taskmaster" / "docs" / "progress.md"
        content = progress_path.read_text()
        assert "First task" in content
        assert "Second task" in content

    def test_log_progress_optional_fields(self, tmp_project):
        """Works with only required fields (task-id and title)."""
        rc, out = run_script(SCRIPT_PY, [
            "log-progress", "--task-id", "1", "--title", "Minimal entry",
        ], cwd=str(tmp_project))
        assert rc == 0
        progress_path = tmp_project / ".taskmaster" / "docs" / "progress.md"
        content = progress_path.read_text()
        assert "N/A" in content  # default for missing optional fields


# ═══════════════════════════════════════════════════════════════════════════════
# INIT-TASKMASTER
# ═══════════════════════════════════════════════════════════════════════════════


class TestInitTaskmaster:
    """Test cmd_init_taskmaster — project initialization."""

    def test_init_mcp_returns_instructions(self):
        """MCP init returns the correct tool call params."""
        rc, out = run_script(SCRIPT_PY, ["init-taskmaster", "--method", "mcp"])
        assert rc == 0
        assert out["ok"] is True
        assert out["method"] == "mcp"
        assert "params" in out
        assert out["params"]["yes"] is True
        assert out["params"]["storeTasksInGit"] is True

    def test_init_invalid_method(self):
        """Invalid method rejected by argparse."""
        rc, _ = run_script(SCRIPT_PY, ["init-taskmaster", "--method", "invalid"])
        assert rc != 0  # argparse rejects invalid choice


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (unit-level)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """Test helper functions directly by importing the module."""

    @pytest.fixture(autouse=True)
    def _import_script(self):
        """Import script.py as module for direct function testing."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("prd_script", str(SCRIPT_PY))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_word_count(self):
        assert self.mod.word_count("hello world") == 2
        assert self.mod.word_count("one") == 1
        assert self.mod.word_count("three words here") == 3

    def test_word_count_empty(self):
        """Empty string edge case."""
        result = self.mod.word_count("")
        # "".split() returns [] so len([]) = 0
        assert result == 0

    def test_count_requirements(self):
        text = "REQ-001 is first, REQ-002 is second, REQ-001 again (deduped)"
        assert self.mod.count_requirements(text) == 2  # unique only

    def test_count_requirements_none(self):
        assert self.mod.count_requirements("no requirements here") == 0

    def test_has_section(self):
        text = "# Title\n## Executive Summary\nContent here\n## Next Section"
        assert self.mod.has_section(text, "Executive Summary") is True
        assert self.mod.has_section(text, "Nonexistent") is False

    def test_has_section_case_insensitive(self):
        text = "## executive summary\nContent"
        assert self.mod.has_section(text, "Executive Summary") is True

    def test_get_section_content(self):
        text = "# Title\n## Goals\nGoal 1\nGoal 2\n## Next\nOther content"
        content = self.mod.get_section_content(text, "Goals")
        assert "Goal 1" in content
        assert "Goal 2" in content
        assert "Other content" not in content

    def test_get_section_content_empty(self):
        text = "# Title\nNo sections here"
        content = self.mod.get_section_content(text, "Goals")
        assert content == ""

    def test_vague_pattern_detection(self):
        """VAGUE_PATTERN matches vague terms."""
        matches = self.mod.VAGUE_PATTERN.findall("The system should be fast and secure")
        assert "fast" in [m.lower() for m in matches]
        assert "secure" in [m.lower() for m in matches]

    def test_vague_pattern_no_false_positives(self):
        """VAGUE_PATTERN doesn't match specific language."""
        matches = self.mod.VAGUE_PATTERN.findall(
            "Response time under 200ms with AES-256 encryption"
        )
        assert len(matches) == 0

    def test_now_iso_format(self):
        """now_iso returns valid ISO format."""
        result = self.mod.now_iso()
        assert "T" in result
        assert "+" in result or "Z" in result
