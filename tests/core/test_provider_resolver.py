# tests/core/test_provider_resolver.py
"""resolve_provider precedence. Every external fact is monkeypatched -- no
subprocess, no network, no real config file is read.

Knobs under test (all default-applied by fleet.engine_config):
  provider_mode   : hybrid | api_only | cli_only | plan_only
  keyless_default : True/null -> CLI-first ; False -> key-first ; floor always
"""

import prd_taskmaster.provider_resolver as pr
from prd_taskmaster.provider_resolver import ProviderHandle


def _engine(provider_mode="hybrid", keyless_default=None, ttl_s=900):
    """A fleet_config dict whose engine block is what the resolver reads."""
    return {
        "engine": {
            "provider_mode": provider_mode,
            "keyless_default": keyless_default,
            "cli_agent": {"probe_cache_ttl_s": ttl_s},
        }
    }


def _patch(monkeypatch, *, role_provider="claude-code", role_model="sonnet",
           usable=True, probe=True, key=None):
    """Wire the four facts resolve_provider consults."""
    monkeypatch.setattr(
        pr, "_read_taskmaster_model",
        lambda role: {"provider": role_provider, "modelId": role_model},
    )
    monkeypatch.setattr(pr, "_provider_usable", lambda *a, **k: usable)
    monkeypatch.setattr(pr, "_probe_spawn_cached", lambda provider, ttl_s: probe)
    monkeypatch.setattr(pr, "discover_key", lambda: key)


def test_handle_is_frozen_dataclass():
    h = ProviderHandle(kind="plan", provider="", role="main", model=None, reason="x")
    assert (h.kind, h.provider, h.role, h.model, h.reason) == ("plan", "", "main", None, "x")
    try:
        h.kind = "cli"
        assert False, "ProviderHandle must be frozen"
    except Exception:
        pass


def test_no_cli_no_key_falls_to_plan_floor(monkeypatch):
    # claude-code role, but spawn probe refuses AND no API key -> plan floor.
    _patch(monkeypatch, usable=True, probe=False, key=None)
    h = pr.resolve_provider("main", fleet_config=_engine())
    assert h.kind == "plan"
    assert h.provider == ""
    assert h.role == "main"


def test_plan_only_mode_always_returns_plan(monkeypatch):
    # Even with a perfectly usable CLI and a key, plan_only forces the floor.
    _patch(monkeypatch, usable=True, probe=True, key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="plan_only"))
    assert h.kind == "plan"
