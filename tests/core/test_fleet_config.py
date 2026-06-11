"""B-Task 8 (REQ-010): .atlas-ai/fleet.json routing config for Atlas Fleet."""

import json

import pytest

from prd_taskmaster.fleet import load_fleet_config, resolve_backend


def test_defaults_without_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_fleet_config()
    assert cfg["max_concurrency"] == 3
    assert cfg["experimental_backends"] is False
    assert cfg["token_economy"] == "balanced"
    assert "escalation" not in cfg
    assert set(cfg["routing"]) == {"fast", "standard", "capable", "frontier"}
    assert all(v.startswith("claude:") for v in cfg["routing"].values())


def test_config_file_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "max_concurrency": 5,
        "routing": {"fast": "codex:gpt-5.2-codex"},
        "experimental_backends": True,
        "token_economy": "conservative",
        "escalation": {"max_steps": 1, "ceiling": "capable"},
    }))
    cfg = load_fleet_config()
    assert cfg["max_concurrency"] == 5
    assert cfg["experimental_backends"] is True
    assert cfg["token_economy"] == "conservative"
    assert cfg["escalation"] == {
        "enabled": True,
        "max_steps": 1,
        "ceiling": "capable",
    }
    assert cfg["routing"]["fast"] == "codex:gpt-5.2-codex"
    # unspecified tiers keep defaults
    assert cfg["routing"]["capable"].startswith("claude:")


def test_flag_off_forces_claude_regardless_of_routing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "routing": {"fast": "codex:gpt-5.2-codex", "capable": "gemini:pro"},
        "experimental_backends": False,
    }))
    cfg = load_fleet_config()
    assert resolve_backend("fast", cfg).startswith("claude:")
    assert resolve_backend("capable", cfg).startswith("claude:")


def test_flag_on_honours_routing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "routing": {"fast": "codex:gpt-5.2-codex"},
        "experimental_backends": True,
    }))
    cfg = load_fleet_config()
    assert resolve_backend("fast", cfg) == "codex:gpt-5.2-codex"
    assert resolve_backend("standard", cfg).startswith("claude:")  # default kept


def test_malformed_config_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text("{not json")
    cfg = load_fleet_config()
    assert cfg["max_concurrency"] == 3
    assert cfg["experimental_backends"] is False


def test_invalid_values_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "max_concurrency": 0,          # invalid (<1) -> default
        "routing": "not-a-dict",        # invalid -> default
        "token_economy": 123,            # invalid -> default
        "escalation": {
            "enabled": "yes",            # invalid -> dropped
            "max_steps": -1,             # invalid -> dropped
            "ceiling": "slow",           # invalid -> dropped
        },
        "unknown_key": "ignored",
    }))
    cfg = load_fleet_config()
    assert cfg["max_concurrency"] == 3
    assert cfg["token_economy"] == "balanced"
    assert "escalation" not in cfg
    assert isinstance(cfg["routing"], dict)


def test_unknown_token_economy_string_is_preserved_for_profile_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({"token_economy": "turbo"}))

    cfg = load_fleet_config()

    assert cfg["token_economy"] == "turbo"


def test_unknown_tier_resolves_to_standard():
    cfg = {"routing": {"standard": "claude:sonnet"}, "experimental_backends": True}
    assert resolve_backend("mystery", cfg) == "claude:sonnet"
