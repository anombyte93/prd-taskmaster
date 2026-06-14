"""Pre-relaunch UX-flow regression tests (docs/audit/UX-FLOW-AUDIT.md, 2026-06-14).

UX-P0-3: token_economy is read only from .atlas-ai/fleet.json, but /customise-workflow
writes .atlas-ai/config/atlas.json — so the economy a user sets via the discoverable
customization tool is silently ignored. The engine must honor atlas.json's economy.
"""

import json

from prd_taskmaster.fleet import load_fleet_config


def test_load_fleet_config_reads_token_economy_from_atlas_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfgdir = tmp_path / ".atlas-ai" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "atlas.json").write_text(json.dumps({"token_economy": "conservative"}))

    assert load_fleet_config()["token_economy"] == "conservative"


def test_fleet_json_token_economy_wins_over_atlas_json(tmp_path, monkeypatch):
    """fleet.json is the lower-level routing file — an explicit value there wins."""
    monkeypatch.chdir(tmp_path)
    aa = tmp_path / ".atlas-ai"
    (aa / "config").mkdir(parents=True)
    (aa / "config" / "atlas.json").write_text(json.dumps({"token_economy": "conservative"}))
    (aa / "fleet.json").write_text(json.dumps({"token_economy": "performance"}))

    assert load_fleet_config()["token_economy"] == "performance"


def test_load_fleet_config_default_economy_when_neither_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_fleet_config()["token_economy"] == "balanced"
