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
    assert r["recommended_mode"] in ("A", "B", "C")
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
