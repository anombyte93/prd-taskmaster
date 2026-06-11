"""Tests for Atlas Fleet launcher detection."""

import json

import pytest

from prd_taskmaster.mode_recommend import detect_atlas_launcher


def _make_executable(path):
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)


@pytest.mark.parametrize(
    ("binary_name", "expected_installed"),
    [
        (None, False),
        ("atlas-launcher", True),
        ("atlas", True),
    ],
)
@pytest.mark.parametrize(
    ("home_config", "expected_registered"),
    [
        (None, False),
        ({"mcpServers": {"atlas-launcher": {"command": "atlas-launcher"}}}, True),
    ],
)
def test_detect_atlas_launcher_binary_and_config_matrix(
    monkeypatch,
    tmp_path,
    binary_name,
    expected_installed,
    home_config,
    expected_registered,
):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    bin_dir = tmp_path / "bin"
    home_dir.mkdir()
    project_dir.mkdir()
    bin_dir.mkdir()

    if binary_name:
        _make_executable(bin_dir / binary_name)
    if home_config:
        (home_dir / ".claude.json").write_text(json.dumps(home_config))

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.chdir(project_dir)

    assert detect_atlas_launcher() == {
        "installed": expected_installed,
        "mcp_registered": expected_registered,
    }


def test_detect_atlas_launcher_ignores_malformed_home_config(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    bin_dir = tmp_path / "bin"
    home_dir.mkdir()
    project_dir.mkdir()
    bin_dir.mkdir()
    (home_dir / ".claude.json").write_text("{not valid json")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.chdir(project_dir)

    assert detect_atlas_launcher() == {
        "installed": False,
        "mcp_registered": False,
    }


def test_detect_atlas_launcher_ignores_empty_project_mcp_json(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    bin_dir = tmp_path / "bin"
    home_dir.mkdir()
    project_dir.mkdir()
    bin_dir.mkdir()
    (project_dir / ".mcp.json").write_text("")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.chdir(project_dir)

    assert detect_atlas_launcher() == {
        "installed": False,
        "mcp_registered": False,
    }


@pytest.mark.parametrize(
    "project_config",
    [
        {"atlas-launcher": {"command": "atlas-launcher"}},
        {"mcpServers": {"atlas-launcher": {"command": "atlas-launcher"}}},
    ],
)
def test_detect_atlas_launcher_finds_project_mcp_json_only(
    monkeypatch,
    tmp_path,
    project_config,
):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    bin_dir = tmp_path / "bin"
    home_dir.mkdir()
    project_dir.mkdir()
    bin_dir.mkdir()
    (project_dir / ".mcp.json").write_text(json.dumps(project_config))

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.chdir(project_dir)

    assert detect_atlas_launcher() == {
        "installed": False,
        "mcp_registered": True,
    }
