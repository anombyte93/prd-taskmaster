"""Atlas hybrid provider: engine config block defaults + merge (Chunk 1)."""

import json

import pytest

from prd_taskmaster.fleet import engine_config, load_fleet_config


# ─── engine_config() pure defaults ───────────────────────────────────────────

def test_engine_config_none_returns_full_defaults():
    eng = engine_config(None)
    assert eng["provider_mode"] == "hybrid"
    assert eng["keyless_default"] is None
    assert eng["cli_agent"]["structured_json"] == "auto"
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900
    assert eng["cli_agent"]["per_call_timeout_s"] == 180
    assert eng["cli_agent"]["max_inflight"] is None
    assert eng["concurrency"]["structured_gen"] is None
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_no_arg_returns_full_defaults():
    # Called with no argument at all (cfg defaults to None).
    eng = engine_config()
    assert eng["provider_mode"] == "hybrid"
    assert eng["keyless_default"] is None
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_returns_fresh_copy_not_shared_mutable():
    a = engine_config(None)
    a["provider_mode"] = "MUTATED"
    a["cli_agent"]["probe_cache_ttl_s"] = -999
    b = engine_config(None)
    assert b["provider_mode"] == "hybrid"
    assert b["cli_agent"]["probe_cache_ttl_s"] == 900


# ─── engine_config() merges valid overrides ──────────────────────────────────

def test_engine_config_merges_valid_top_level_values():
    raw = {"engine": {"provider_mode": "cli_only", "keyless_default": True}}
    eng = engine_config(raw)
    assert eng["provider_mode"] == "cli_only"
    assert eng["keyless_default"] is True
    # untouched keys keep defaults
    assert eng["cli_agent"]["structured_json"] == "auto"
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_keyless_default_false_is_honored():
    eng = engine_config({"engine": {"keyless_default": False}})
    assert eng["keyless_default"] is False


def test_engine_config_merges_valid_cli_agent_values():
    raw = {"engine": {"cli_agent": {
        "structured_json": "schema",
        "probe_cache_ttl_s": 60,
        "per_call_timeout_s": 30,
        "max_inflight": 4,
    }}}
    eng = engine_config(raw)
    assert eng["cli_agent"]["structured_json"] == "schema"
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 60
    assert eng["cli_agent"]["per_call_timeout_s"] == 30
    assert eng["cli_agent"]["max_inflight"] == 4


def test_engine_config_merges_valid_concurrency_values():
    raw = {"engine": {"concurrency": {"structured_gen": 8, "ram_aware": True}}}
    eng = engine_config(raw)
    assert eng["concurrency"]["structured_gen"] == 8
    assert eng["concurrency"]["ram_aware"] is True


# ─── engine_config() ignores malformed values (silent fallback) ──────────────

def test_engine_config_malformed_provider_mode_falls_back():
    eng = engine_config({"engine": {"provider_mode": "warp_drive"}})
    assert eng["provider_mode"] == "hybrid"


def test_engine_config_malformed_keyless_default_falls_back():
    # Only true/false/None are valid; a string is malformed -> default None.
    eng = engine_config({"engine": {"keyless_default": "yes"}})
    assert eng["keyless_default"] is None


def test_engine_config_malformed_structured_json_falls_back():
    eng = engine_config({"engine": {"cli_agent": {"structured_json": "telepathy"}}})
    assert eng["cli_agent"]["structured_json"] == "auto"


def test_engine_config_malformed_ints_fall_back():
    raw = {"engine": {"cli_agent": {
        "probe_cache_ttl_s": "soon",     # not an int
        "per_call_timeout_s": 0,          # < 1, invalid
        "max_inflight": -3,               # < 1, invalid (None stays valid via default)
    }}}
    eng = engine_config(raw)
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900
    assert eng["cli_agent"]["per_call_timeout_s"] == 180
    assert eng["cli_agent"]["max_inflight"] is None


def test_engine_config_bool_is_not_accepted_as_int():
    # bool is a subclass of int in Python; ttl must reject True/False.
    eng = engine_config({"engine": {"cli_agent": {"probe_cache_ttl_s": True}}})
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900


def test_engine_config_malformed_ram_aware_falls_back():
    eng = engine_config({"engine": {"concurrency": {"ram_aware": "true"}}})
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_malformed_structured_gen_falls_back():
    eng = engine_config({"engine": {"concurrency": {"structured_gen": "lots"}}})
    assert eng["concurrency"]["structured_gen"] is None


def test_engine_config_non_dict_engine_block_falls_back():
    assert engine_config({"engine": "broken"})["provider_mode"] == "hybrid"
    assert engine_config({"engine": ["not", "a", "dict"]})["provider_mode"] == "hybrid"
    assert engine_config({"engine": 42})["provider_mode"] == "hybrid"


def test_engine_config_non_dict_cli_agent_falls_back():
    eng = engine_config({"engine": {"cli_agent": "nope"}})
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900


def test_engine_config_non_dict_concurrency_falls_back():
    eng = engine_config({"engine": {"concurrency": 5}})
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_missing_engine_key_returns_defaults():
    eng = engine_config({"max_concurrency": 7})
    assert eng["provider_mode"] == "hybrid"


def test_engine_config_non_dict_cfg_returns_defaults():
    assert engine_config("garbage")["provider_mode"] == "hybrid"
    assert engine_config(42)["provider_mode"] == "hybrid"
    assert engine_config([])["provider_mode"] == "hybrid"
