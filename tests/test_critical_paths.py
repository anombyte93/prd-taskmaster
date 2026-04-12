"""Tests for critical paths identified by doubt agent audit.

Addresses:
1. init-taskmaster --method cli (when CLI is missing)
2. detect-taskmaster CLI/none detection
3. write-research from stdin
4. has_section with h4+ headings (regression test for bug fix)
5. rollback.sh syntax validation
6. log-progress with special characters
7. User stories section exists but no AC
8. Empty research file edge case
9. calc-tasks raw_calculation with negative input
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPT_PY, EXPAND_SCRIPT_PY, run_script


class TestInitTaskmasterCLI:
    """Tests for init-taskmaster --method cli (previously untested)."""

    def test_init_cli_no_taskmaster_installed(self):
        """CLI init fails gracefully when taskmaster binary is missing."""
        # Modify PATH to exclude taskmaster
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"  # minimal PATH without taskmaster
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PY), "init-taskmaster", "--method", "cli"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1
        out = json.loads(result.stdout)
        assert out["ok"] is False
        assert "not found" in out["error"].lower()


class TestDetectTaskmasterPaths:
    """Tests for all detect-taskmaster code paths."""

    def test_detect_none_when_no_config(self, tmp_path):
        """Returns 'none' when no MCP config and no CLI in PATH."""
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"  # minimal PATH without taskmaster
        env["HOME"] = str(tmp_path)  # no config files here
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PY), "detect-taskmaster"],
            capture_output=True, text=True, cwd=str(tmp_path), env=env,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["method"] == "none"  # no CLI in PATH, no MCP config

    def test_detect_mcp_malformed_config(self, tmp_path):
        """Handles malformed .mcp.json gracefully."""
        (tmp_path / ".mcp.json").write_text("{invalid json")
        rc, out = run_script(SCRIPT_PY, ["detect-taskmaster"], cwd=str(tmp_path))
        assert rc == 0
        assert out["ok"] is True
        assert out["method"] in ("none", "cli")  # not mcp since config is broken

    def test_detect_mcp_empty_servers(self, tmp_path):
        """Empty mcpServers doesn't detect MCP."""
        config = {"mcpServers": {}}
        (tmp_path / ".mcp.json").write_text(json.dumps(config))
        rc, out = run_script(SCRIPT_PY, ["detect-taskmaster"], cwd=str(tmp_path))
        assert rc == 0
        # Should not detect MCP from empty servers
        assert out["method"] != "mcp" or out["method"] in ("cli", "none")


class TestWriteResearchStdin:
    """Test write-research from stdin (previously untested code path)."""

    def test_write_research_from_stdin(self, tmp_path):
        """Write research content piped via stdin."""
        data = {
            "tasks": [{"id": 1, "title": "Test", "description": "Desc", "dependencies": []}]
        }
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps(data))

        result = subprocess.run(
            [sys.executable, str(EXPAND_SCRIPT_PY),
             "write-research", "--task-id", "1", "--research", "-",
             "--file", str(tasks_path)],
            input="## Research via stdin\n\nFindings here.",
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["success"] is True

        # Verify content was written
        updated = json.loads(tasks_path.read_text())
        task1 = updated["tasks"][0]
        assert task1["research_notes"] == "## Research via stdin\n\nFindings here."

    def test_write_research_empty_content(self, tmp_path):
        """Empty research content doesn't crash."""
        data = {"tasks": [{"id": 1, "title": "T", "description": "D", "dependencies": []}]}
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps(data))

        research_file = tmp_path / "empty.md"
        research_file.write_text("")

        rc, out = run_script(EXPAND_SCRIPT_PY, [
            "write-research", "--task-id", "1",
            "--research", str(research_file),
            "--file", str(tasks_path),
        ])
        assert rc == 0
        assert out["success"] is True
        assert out["research_length"] == 0


class TestHasSectionHeadingLevels:
    """Regression tests for has_section regex fix (#{1,3} -> #{1,6})."""

    @pytest.fixture(autouse=True)
    def _import_script(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("prd_script", str(SCRIPT_PY))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_h1_heading(self):
        assert self.mod.has_section("# Out of Scope\nContent", "Out of Scope") is True

    def test_h2_heading(self):
        assert self.mod.has_section("## Out of Scope\nContent", "Out of Scope") is True

    def test_h3_heading(self):
        assert self.mod.has_section("### Out of Scope\nContent", "Out of Scope") is True

    def test_h4_heading(self):
        """h4 heading must be detected (was broken before regex fix)."""
        assert self.mod.has_section("#### Out of Scope\nContent", "Out of Scope") is True

    def test_h5_heading(self):
        assert self.mod.has_section("##### Out of Scope\nContent", "Out of Scope") is True

    def test_h6_heading(self):
        assert self.mod.has_section("###### Out of Scope\nContent", "Out of Scope") is True

    def test_consistency_with_get_section_content(self):
        """has_section and get_section_content agree on heading existence."""
        text = "#### Deep Heading\nDeep content here"
        has = self.mod.has_section(text, "Deep Heading")
        content = self.mod.get_section_content(text, "Deep Heading")
        # Both should agree: if has_section says it exists, content should be non-empty
        assert has is True
        assert "Deep content" in content


class TestRollbackScript:
    """Test the generated rollback.sh script."""

    def test_rollback_script_syntax_valid(self, tmp_path):
        """rollback.sh passes bash syntax check."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        result = subprocess.run(
            ["bash", "-n", str(output_dir / "rollback.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_rollback_script_requires_argument(self, tmp_path):
        """rollback.sh exits with error when no task number provided."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        result = subprocess.run(
            ["bash", str(output_dir / "rollback.sh")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode != 0

    def test_rollback_script_missing_tag(self, tmp_path):
        """rollback.sh errors when checkpoint tag doesn't exist."""
        output_dir = tmp_path / "scripts"
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(output_dir)])

        # Init a git repo so git commands work but tag won't exist
        subprocess.run(["git", "init"], capture_output=True, cwd=str(tmp_path))
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"],
                       capture_output=True, cwd=str(tmp_path),
                       env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"})

        result = subprocess.run(
            ["bash", str(output_dir / "rollback.sh"), "999"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode != 0
        assert "not found" in result.stdout.lower() or "ERROR" in result.stdout


class TestLogProgressSpecialChars:
    """Test log-progress with special characters."""

    def test_progress_with_markdown_chars(self, tmp_project):
        """Titles with markdown chars don't corrupt progress.md."""
        rc, out = run_script(SCRIPT_PY, [
            "log-progress",
            "--task-id", "1",
            "--title", "Fix **bold** and # heading | pipe chars",
        ], cwd=str(tmp_project))
        assert rc == 0
        content = (tmp_project / ".taskmaster" / "docs" / "progress.md").read_text()
        assert "Fix **bold** and # heading | pipe chars" in content

    def test_progress_with_unicode(self, tmp_project):
        """Unicode characters in title are preserved."""
        rc, out = run_script(SCRIPT_PY, [
            "log-progress",
            "--task-id", "1",
            "--title", "Japanese: テスト German: Ärger",
        ], cwd=str(tmp_project))
        assert rc == 0
        content = (tmp_project / ".taskmaster" / "docs" / "progress.md").read_text()
        assert "テスト" in content


class TestUserStoriesVacuousPass:
    """Test check 5's vacuous pass behavior."""

    def test_stories_heading_no_content(self, tmp_path):
        """User Stories heading exists but no actual stories → passes vacuously."""
        prd = tmp_path / "prd.md"
        prd.write_text("""# PRD

## User Stories

Just some text, no actual story blocks.
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        check5 = next(c for c in out["checks"] if c["id"] == 5)
        # No Story blocks found, so ac_counts is empty → passes vacuously
        assert check5["passed"] is True
        assert "No user stories" in check5["detail"]

    def test_stories_with_one_ac(self, tmp_path):
        """Single acceptance criterion per story should fail."""
        prd = tmp_path / "prd.md"
        prd.write_text("""# PRD

## User Stories

### Story 1: Basic
As a user I want to login.
- [ ] Can enter credentials

### Story 2: Another
As a user I want to register.
- [ ] Can submit form
""")
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", str(prd)])
        check5 = next(c for c in out["checks"] if c["id"] == 5)
        assert check5["passed"] is False


class TestCalcTasksRawCalculation:
    """Verify raw_calculation field for edge cases."""

    def test_negative_raw_calculation(self):
        """Negative input produces negative raw calculation but clamped recommended."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "-5"])
        assert rc == 0
        assert out["raw_calculation"] == -7  # ceil(-5 * 1.5) = ceil(-7.5) = -7
        assert out["recommended"] == 10  # clamped to minimum

    def test_raw_vs_recommended_divergence(self):
        """Large inputs show divergence between raw and recommended."""
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "100"])
        assert rc == 0
        assert out["raw_calculation"] == 150
        assert out["recommended"] == 40
        # The divergence should be clear
        assert out["raw_calculation"] > out["recommended"]
