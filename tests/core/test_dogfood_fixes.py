"""Regression tests for the four 2026-06-11 dogfood findings
(docs/dogfood-phase-b-2026-06-11.md)."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from prd_taskmaster.capabilities import run_detect_capabilities
from prd_taskmaster.lib import CommandError
from prd_taskmaster.providers import run_configure_providers
from prd_taskmaster.taskmaster import init_taskmaster
from prd_taskmaster.tasks import run_calc_tasks


# ── Finding 1 (P0): init must protect an existing .mcp.json ────────────────

def _fake_task_master(bin_dir: Path, clobber: bool) -> None:
    """A fake task-master binary; optionally clobbers .mcp.json like the real init."""
    script = bin_dir / "task-master"
    body = "#!/bin/sh\n"
    if clobber:
        body += "echo '{\"mcpServers\": {\"task-master-ai\": {}}}' > .mcp.json\n"
    body += "exit 0\n"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def test_init_restores_clobbered_mcp_json(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_task_master(bin_dir, clobber=True)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)

    original = '{\n  "go": {"command": "python3"}\n}\n'
    (tmp_path / ".mcp.json").write_text(original)

    result = init_taskmaster()
    assert result["ok"] is True
    assert result["mcp_json_protected"] is True
    assert (tmp_path / ".mcp.json").read_text() == original


def test_init_reports_unprotected_when_no_clobber(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_task_master(bin_dir, clobber=False)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)

    original = '{"go": {}}'
    (tmp_path / ".mcp.json").write_text(original)

    result = init_taskmaster()
    assert result["ok"] is True
    assert result["mcp_json_protected"] is False
    assert (tmp_path / ".mcp.json").read_text() == original


def test_init_without_preexisting_mcp_json(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_task_master(bin_dir, clobber=True)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)

    result = init_taskmaster()
    # no original file -> nothing to protect; whatever init wrote stays
    assert result["ok"] is True
    assert result["mcp_json_protected"] is False


# ── Finding 2 (P1): configure-providers points at the protected init ────────

def test_configure_providers_recommends_protected_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .taskmaster/config.json here
    with pytest.raises(CommandError) as exc:
        run_configure_providers()
    assert exc.value.extra["recommended_action"] == "init_taskmaster"
    assert "init-taskmaster" in exc.value.extra["fix"]


def _seed_taskmaster_config(root: Path, models: dict) -> None:
    taskmaster = root / ".taskmaster"
    taskmaster.mkdir()
    (taskmaster / "config.json").write_text(json.dumps({"models": models}, indent=2))


def _read_taskmaster_config(root: Path) -> dict:
    return json.loads((root / ".taskmaster" / "config.json").read_text())


def _patch_provider_detection(monkeypatch, *, claude: bool = False, codex: bool = False) -> None:
    def fake_which(name: str) -> str | None:
        if name == "claude" and claude:
            return "/fake/bin/claude"
        if name == "codex" and codex:
            return "/fake/bin/codex"
        return None

    monkeypatch.setattr("prd_taskmaster.providers.shutil.which", fake_which)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_BASE_URL", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_FREE_BASE_URL", raising=False)


def test_configure_providers_conservative_rewrites_engine_default_main_to_fast_tier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch)
    _seed_taskmaster_config(
        tmp_path,
        {
            "main": {
                "provider": "claude-code",
                "modelId": "sonnet",
                "maxTokens": 64000,
                "temperature": 0.2,
            }
        },
    )

    result = run_configure_providers(economy="conservative")

    assert result["economy"] == "conservative"
    assert result["models"]["main"] == {
        "provider": "claude-code",
        "modelId": "haiku",
        "maxTokens": 64000,
        "temperature": 0.2,
    }
    assert "main" in result["changed"]


def test_configure_providers_balanced_with_key_configures_sonar_research(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    _seed_taskmaster_config(tmp_path, {})

    result = run_configure_providers(economy="balanced")

    assert result["economy"] == "balanced"
    assert result["models"]["research"] == {
        "provider": "perplexity",
        "modelId": "sonar",
        "maxTokens": 8700,
        "temperature": 0.1,
    }


def test_configure_providers_performance_with_key_configures_sonar_pro_research(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    _seed_taskmaster_config(tmp_path, {})

    result = run_configure_providers(economy="performance")

    assert result["economy"] == "performance"
    assert result["models"]["research"] == {
        "provider": "perplexity",
        "modelId": "sonar-pro",
        "maxTokens": 8700,
        "temperature": 0.1,
    }


def test_configure_providers_user_configured_main_is_not_touched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch, claude=True)
    user_main = {
        "provider": "openai",
        "modelId": "gpt-4.1",
        "maxTokens": 32000,
        "temperature": 0.3,
    }
    _seed_taskmaster_config(tmp_path, {"main": dict(user_main)})

    result = run_configure_providers(economy="conservative")

    assert result["models"]["main"] == user_main
    assert result["skipped_main"] == "user-configured"
    assert "main" not in result["changed"]


def test_configure_providers_none_economy_reads_fleet_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch)
    (tmp_path / ".atlas-ai").mkdir()
    (tmp_path / ".atlas-ai" / "fleet.json").write_text(json.dumps({"token_economy": "conservative"}))
    _seed_taskmaster_config(
        tmp_path,
        {
            "main": {
                "provider": "claude-code",
                "modelId": "sonnet",
                "maxTokens": 64000,
                "temperature": 0.2,
            }
        },
    )

    result = run_configure_providers()

    assert result["economy"] == "conservative"
    assert result["models"]["main"]["modelId"] == "haiku"


def test_configure_providers_free_proxy_first_preserves_local_proxy_golden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_provider_detection(monkeypatch)
    _seed_taskmaster_config(tmp_path, {})

    result = run_configure_providers(economy="conservative")

    assert result["models"]["research"] == {
        "provider": "openai-compatible",
        "modelId": "sonar",
        "maxTokens": 8700,
        "temperature": 0.1,
        "baseURL": "http://127.0.0.1:8765",
    }
    assert result["changed"] == [
        "research",
        ".env:OPENAI_COMPATIBLE_API_KEY",
        ".env:PERPLEXITY_API_BASE_URL",
    ]
    assert (tmp_path / ".env").read_text() == (
        'OPENAI_COMPATIBLE_API_KEY="local-perplexity-api-free"\n'
        'PERPLEXITY_API_BASE_URL="http://127.0.0.1:8765"\n'
    )


# ── Finding 3 (P2): calc-tasks respects the discovery scale band ───────────

def test_calc_tasks_solo_band_clamps_down():
    r = run_calc_tasks(14, scale="solo")
    assert r["recommended"] == 12  # raw 21 clamped to solo [8, 12]
    assert r["scale"] == "solo"


def test_calc_tasks_enterprise_band_clamps_up():
    r = run_calc_tasks(3, scale="enterprise")
    assert r["recommended"] == 20  # raw 5 clamped to enterprise [20, 30]


def test_calc_tasks_no_scale_keeps_legacy_formula():
    r = run_calc_tasks(14)
    assert r["recommended"] == 21
    assert "scale" not in r


def test_calc_tasks_rejects_unknown_scale():
    with pytest.raises(CommandError):
        run_calc_tasks(10, scale="galactic")


# ── Finding 4 (P2): detection emits tier + a reason aligned with handoff ───

def test_detect_capabilities_has_tier_and_reason():
    r = run_detect_capabilities()
    assert r["tier"] in ("free", "premium")
    assert r["recommended_mode"] in ("A", "B", "C", "D")
    assert len(r["recommended_reason"]) > 10


def test_detect_capabilities_loop_runner_flips_to_verified_loop(monkeypatch, tmp_path):
    # Fake a HOME with superpowers + ralph-loop installed -> Verified Loop (C)
    home = tmp_path / "home"
    (home / ".claude" / "plugins" / "superpowers").mkdir(parents=True)
    (home / ".claude" / "skills" / "ralph-loop").mkdir(parents=True)
    (home / ".claude" / "skills" / "ralph-loop" / "SKILL.md").write_text("x")
    monkeypatch.setenv("HOME", str(home))
    r = run_detect_capabilities()
    assert r["recommended_mode"] == "C"
    assert "Verified Loop" in r["recommended_reason"]
