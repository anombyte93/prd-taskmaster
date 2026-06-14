"""Tests for prd_taskmaster.mode_recommend — detect_taskmaster, detect_capabilities, validate_setup.

Retargeted from the plugin's capabilities.py (now prd_taskmaster/mode_recommend.py).
Direct function calls (no sys.exit, pure dicts). Uses monkeypatch for env isolation.
"""

import json

import pytest

from prd_taskmaster.mode_recommend import detect_taskmaster, detect_capabilities, validate_setup


# ─── detect_taskmaster ────────────────────────────────────────────────────────


class TestDetectTaskmaster:
    """detect_taskmaster() — MCP/CLI/none detection."""

    def test_detect_taskmaster_finds_cli(self, monkeypatch, tmp_path):
        """Returns method='cli' when a task-master binary is found in PATH."""

        # Create a fake task-master script that outputs a version line.
        fake_bin = tmp_path / "task-master"
        fake_bin.write_text("#!/bin/sh\necho 0.99.0\n")
        fake_bin.chmod(0o755)

        monkeypatch.setenv("PATH", str(tmp_path))
        # Ensure no MCP config files exist in tmp_path (CWD isolation)
        monkeypatch.chdir(tmp_path)

        result = detect_taskmaster()

        assert result["ok"] is True
        assert result["method"] == "cli"
        assert result["path"] is not None

    def test_detect_taskmaster_returns_none_when_missing(self, monkeypatch, tmp_path):
        """Returns method='none' when no CLI or MCP config is found."""
        monkeypatch.setenv("PATH", str(tmp_path))  # empty dir — no binaries
        monkeypatch.chdir(tmp_path)

        result = detect_taskmaster()

        assert result["ok"] is True
        assert result["method"] == "none"
        assert result["path"] is None

    def test_detect_taskmaster_finds_mcp_from_dotmcp_json(self, monkeypatch, tmp_path):
        """Returns method='mcp' when .mcp.json contains a task-master server entry."""
        mcp_config = {
            "mcpServers": {
                "task-master-ai": {"command": "npx", "args": ["task-master-ai"]}
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp_config))
        monkeypatch.setenv("PATH", str(tmp_path))  # no CLI binary
        monkeypatch.chdir(tmp_path)

        result = detect_taskmaster()

        assert result["ok"] is True
        assert result["method"] == "mcp"

    def test_detect_taskmaster_always_returns_ok_true(self, monkeypatch, tmp_path):
        """ok is always True — no sys.exit, result is always a dict."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_taskmaster()

        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["method"] in ("mcp", "cli", "none")


# ─── detect_capabilities ──────────────────────────────────────────────────────


class TestDetectCapabilities:
    """detect_capabilities() — tier, flags, and tool inventory."""

    def test_detect_capabilities_returns_tier_and_flags(self, monkeypatch, tmp_path):
        """Returns expected top-level keys including has_atlas_premium and tier."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_capabilities()

        assert result["ok"] is True
        assert result["tier"] in ("free", "premium")
        assert "has_atlas_premium" in result
        assert "has_superpowers" in result
        assert "has_taskmaster" in result
        assert "capabilities" in result
        assert isinstance(result["capabilities"], dict)

    def test_detect_capabilities_has_atlas_premium_key(self, monkeypatch, tmp_path):
        """has_atlas_premium MUST be a top-level key (adversarial spec requirement)."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_capabilities()

        # has_atlas_premium must exist at top level, not just inside 'capabilities'
        assert "has_atlas_premium" in result
        assert isinstance(result["has_atlas_premium"], bool)

    def test_detect_capabilities_free_tier_without_atlas_skills(self, monkeypatch, tmp_path):
        """Reports free tier when atlas-loop and atlas-cdd skills are absent."""
        # Use a home dir that has no .claude/skills directory at all
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_capabilities()

        assert result["ok"] is True
        assert result["tier"] == "free"
        assert result["has_atlas_premium"] is False

    def test_detect_capabilities_premium_tier_with_atlas_skills(self, monkeypatch, tmp_path):
        """Reports premium tier when both atlas-loop and atlas-cdd skills exist."""
        skills_dir = tmp_path / ".claude" / "skills"
        for skill in ("atlas-loop", "atlas-cdd"):
            skill_dir = skills_dir / skill
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {skill} skill\n")

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_capabilities()

        assert result["ok"] is True
        assert result["tier"] == "premium"
        assert result["has_atlas_premium"] is True

    def test_detect_capabilities_returns_recommended_mode(self, monkeypatch, tmp_path):
        """recommended_mode and recommended_reason are always present."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = detect_capabilities()

        assert "recommended_mode" in result
        assert "recommended_reason" in result
        assert result["recommended_mode"] in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")


# ─── validate_setup ───────────────────────────────────────────────────────────


class TestValidateSetup:
    """validate_setup() — 6-check Phase 0 diagnostic."""

    def test_validate_setup_returns_6_checks(self, monkeypatch, tmp_path):
        """checks list MUST have exactly 6 entries (spec §5)."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = validate_setup()

        assert result["ok"] is True
        assert "checks" in result
        assert len(result["checks"]) == 6

    def test_validate_setup_check_ids_match_spec(self, monkeypatch, tmp_path):
        """Each check has the correct id (spec §5 check IDs)."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = validate_setup()

        ids = [c["id"] for c in result["checks"]]
        assert ids == ["binary", "version", "project", "config", "provider_main", "provider_research"]

    def test_validate_setup_each_check_has_fix_hint(self, monkeypatch, tmp_path):
        """Every check dict has a 'fix' key (may be None when passed)."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = validate_setup()

        for check in result["checks"]:
            assert "id" in check
            assert "passed" in check
            assert "fix" in check

    def test_validate_setup_fails_without_binary(self, monkeypatch, tmp_path):
        """binary check fails when task-master is not in PATH."""
        monkeypatch.setenv("PATH", str(tmp_path))  # empty dir — no binary
        monkeypatch.chdir(tmp_path)

        result = validate_setup()

        binary_check = next(c for c in result["checks"] if c["id"] == "binary")
        assert binary_check["passed"] is False
        assert binary_check["fix"] is not None
        assert result["ready"] is False

    def test_validate_setup_passes_with_full_project(self, monkeypatch, tmp_path):
        """ready=True when CLI exists, project initialized, and the main model's
        provider is genuinely reachable (a real provider + a usable credential —
        not merely a model-id string)."""
        # Create fake task-master binary
        fake_bin = tmp_path / "bin" / "task-master"
        fake_bin.parent.mkdir(parents=True)
        fake_bin.write_text("#!/bin/sh\necho 0.99.0\n")
        fake_bin.chmod(0o755)

        # Create .taskmaster/ with config.json — providers named, and a credential
        # present so the gate's reachability check passes for the right reason.
        tm_dir = tmp_path / "project" / ".taskmaster"
        tm_dir.mkdir(parents=True)
        config = {
            "models": {
                "main": {"provider": "anthropic", "modelId": "claude-sonnet-4-5"},
                "research": {"provider": "anthropic", "modelId": "claude-opus-4"},
                "fallback": {"provider": "anthropic", "modelId": "claude-haiku-3"},
            }
        }
        (tm_dir / "config.json").write_text(json.dumps(config))

        monkeypatch.setenv("PATH", str(tmp_path / "bin"))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.chdir(tmp_path / "project")

        result = validate_setup()

        assert result["ok"] is True
        assert result["ready"] is True
        assert result["critical_failures"] == 0

    def test_validate_setup_critical_failures_count(self, monkeypatch, tmp_path):
        """critical_failures counts non-warning failed checks only."""
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = validate_setup()

        critical_ids = [
            c["id"] for c in result["checks"]
            if not c["passed"] and c.get("severity") != "warning"
        ]
        assert result["critical_failures"] == len(critical_ids)
