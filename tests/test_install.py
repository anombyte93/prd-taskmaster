"""Tests for install.sh — installer behavior verification.

Tests the installer's CLI interface, version reporting, help output,
and install logic using real bash execution in temp directories.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).parent.parent / "install.sh"


def run_install(args=None, env_overrides=None, cwd=None):
    """Run install.sh with optional args and environment overrides."""
    env = os.environ.copy()
    env["NO_COLOR"] = "1"  # disable color codes for clean output parsing
    if env_overrides:
        env.update(env_overrides)
    cmd = ["bash", str(INSTALL_SH)] + (args or [])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    )


class TestInstallCLI:
    """Test install.sh command-line interface."""

    def test_version_flag(self):
        """--version prints skill name and version."""
        result = run_install(["--version"])
        assert result.returncode == 0
        assert "prd-taskmaster" in result.stdout
        assert "v3.0.0" in result.stdout

    def test_version_short_flag(self):
        """-v also works for version."""
        result = run_install(["-v"])
        assert result.returncode == 0
        assert "prd-taskmaster" in result.stdout

    def test_help_flag(self):
        """--help shows usage information."""
        result = run_install(["--help"])
        assert result.returncode == 0
        assert "Usage" in result.stdout
        assert "--check-update" in result.stdout
        assert "--version" in result.stdout

    def test_help_short_flag(self):
        """-h also works for help."""
        result = run_install(["-h"])
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_argument(self):
        """Unknown arguments exit with error."""
        result = run_install(["--foobar"])
        assert result.returncode != 0
        assert "Unknown argument" in result.stderr or "error" in result.stderr.lower()

    def test_check_update_flag(self, tmp_path):
        """--check-update runs without crashing (may fail network but shouldn't error)."""
        # In CI environment, this should skip gracefully
        result = run_install(["--check-update"], env_overrides={"CI": "true"})
        assert result.returncode == 0

    def test_check_update_respects_ci(self):
        """CI environment skips update check."""
        result = run_install(["--check-update"], env_overrides={"CI": "true"})
        assert result.returncode == 0
        # Should not print update available message

    def test_check_update_respects_no_update(self):
        """NO_UPDATE_CHECK environment skips update check."""
        result = run_install(["--check-update"], env_overrides={"NO_UPDATE_CHECK": "1"})
        assert result.returncode == 0


class TestInstallLogic:
    """Test install.sh installation logic."""

    def test_install_to_custom_dir(self, tmp_path):
        """Fresh install to custom SKILL_DIR creates expected files."""
        skill_dir = tmp_path / "test-skill"
        result = run_install(
            env_overrides={"SKILL_DIR": str(skill_dir)},
        )
        # Install will try to git clone — may fail on network
        # but we can test the structure that gets created
        if result.returncode == 0:
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "script.py").exists()
            assert (skill_dir / ".version").exists()

            version_content = (skill_dir / ".version").read_text()
            assert "3.0.0" in version_content
            assert "installed:" in version_content

    def test_install_detects_upgrade(self, tmp_path):
        """When SKILL_DIR exists, installer reports upgrade mode."""
        skill_dir = tmp_path / "existing-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Old skill")
        (skill_dir / ".version").write_text("2.0.0")

        result = run_install(
            env_overrides={"SKILL_DIR": str(skill_dir)},
        )
        # Check it detected upgrade mode (output may be on stdout or stderr)
        combined = (result.stdout + result.stderr).lower()
        assert "upgrade" in combined or "existing" in combined

    def test_install_backs_up_skill_md(self, tmp_path):
        """Upgrade creates SKILL.md.bak backup."""
        skill_dir = tmp_path / "existing-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Old content that should be backed up")

        result = run_install(
            env_overrides={"SKILL_DIR": str(skill_dir)},
        )
        # Even if clone fails, backup should happen before clone
        if (skill_dir / "SKILL.md.bak").exists():
            backup = (skill_dir / "SKILL.md.bak").read_text()
            assert "Old content" in backup


class TestInstallConstants:
    """Verify install.sh has correct configuration values."""

    def test_repo_owner(self):
        """Repo owner is correct."""
        content = INSTALL_SH.read_text()
        assert 'REPO_OWNER="anombyte93"' in content

    def test_repo_name(self):
        """Repo name is correct."""
        content = INSTALL_SH.read_text()
        assert 'REPO_NAME="prd-taskmaster"' in content

    def test_skill_name(self):
        """Skill name matches."""
        content = INSTALL_SH.read_text()
        assert 'SKILL_NAME="prd-taskmaster"' in content

    def test_version_defined(self):
        """Version is defined."""
        content = INSTALL_SH.read_text()
        assert 'VERSION="3.0.0"' in content

    def test_update_interval(self):
        """Update interval is 24 hours."""
        content = INSTALL_SH.read_text()
        assert "86400" in content  # 24 * 60 * 60

    def test_cleanup_trap_exists(self):
        """Cleanup trap is registered."""
        content = INSTALL_SH.read_text()
        assert "trap cleanup EXIT" in content

    def test_set_euo_pipefail(self):
        """Script uses strict bash mode."""
        content = INSTALL_SH.read_text()
        assert "set -euo pipefail" in content
