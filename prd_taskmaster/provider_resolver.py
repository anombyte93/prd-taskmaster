"""Single decision point: pick the provider TIER for one role at gen time.

Three kinds, in contract precedence (keyless_default truthy/null):
  1. cli  -- provider_mode in {hybrid, cli_only} AND role provider is a spawning
            CLI AND usable (_provider_usable) AND _probe_spawn_cached() true.
  2. api  -- provider_mode in {hybrid, api_only} AND discover_key() returns creds.
  3. plan -- always the floor; returned when nothing above is usable.
keyless_default=False swaps tiers 1 and 2. provider_mode=plan_only short-circuits
to plan; cli_only never falls through to api; api_only never tries the CLI.

Nothing here spawns a process or hits the network: it consults
  - _read_taskmaster_model(role)      -> the role's configured provider
  - _provider_usable(...)             -> credential/CLI presence
  - _probe_spawn_cached(provider,ttl) -> empirical nested-spawn check (cached)
  - discover_key()                    -> raw-key API creds
The cli_agent / llm_client actually run the chosen tier downstream.
"""

import os
import shutil
from dataclasses import dataclass

from prd_taskmaster.fleet import engine_config
from prd_taskmaster.lib import _read_taskmaster_model
from prd_taskmaster.llm_client import discover_key
from prd_taskmaster.providers import (
    _SPAWNING_PROVIDERS,
    _provider_usable,
    _probe_spawn_cached,
)


@dataclass(frozen=True)
class ProviderHandle:
    kind: str          # "cli" | "api" | "plan"
    provider: str      # e.g. "claude-code", "anthropic", ""
    role: str          # "main" | "fallback" | "research"
    model: str | None
    reason: str        # human-readable why this tier (telemetry/logs)


def _usability_facts() -> dict:
    """The keyword args _provider_usable expects. discover_key is consulted
    separately for the api tier; here we only need CLI/key presence flags."""
    return {
        "has_claude": shutil.which("claude") is not None,
        "has_codex": shutil.which("codex") is not None,
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_perplexity_key": bool(os.environ.get("PERPLEXITY_API_KEY")),
    }


def _try_cli(role: str, provider: str, model, ttl_s: int) -> ProviderHandle | None:
    """CLI tier: spawning provider, usable, and spawn probe passes (cached)."""
    if provider not in _SPAWNING_PROVIDERS:
        return None
    if not _provider_usable(provider, **_usability_facts()):
        return None
    if not _probe_spawn_cached(provider, ttl_s):
        return None
    return ProviderHandle(
        kind="cli", provider=provider, role=role, model=model,
        reason=f"keyless CLI-agent ({provider}) usable + spawn-probe ok",
    )


def _try_api(role: str, model) -> ProviderHandle | None:
    """Raw-key API tier: discover_key found credentials."""
    creds = discover_key()
    if not creds:
        return None
    return ProviderHandle(
        kind="api", provider=creds.get("provider", ""), role=role, model=model,
        reason=f"raw-key API ({creds.get('provider', '')}) via discover_key",
    )


def _plan_floor(role: str, model, reason: str) -> ProviderHandle:
    return ProviderHandle(kind="plan", provider="", role=role, model=model, reason=reason)


def resolve_provider(role, op_class="structured_gen", *, fleet_config=None) -> ProviderHandle:
    # op_class is reserved for Chunk 4 op-class routing; accepted here but not yet used.
    """Resolve the provider tier for one role. See module docstring for precedence."""
    engine = engine_config(fleet_config)
    mode = engine.get("provider_mode", "hybrid")
    keyless = engine.get("keyless_default")  # True | False | None
    ttl_s = (engine.get("cli_agent") or {}).get("probe_cache_ttl_s", 900)

    role_cfg = _read_taskmaster_model(role) or {}
    provider = str(role_cfg.get("provider", "")).lower()
    model = role_cfg.get("modelId")

    if mode == "plan_only":
        return _plan_floor(role, model, "provider_mode=plan_only")

    cli_allowed = mode in {"hybrid", "cli_only"}
    api_allowed = mode in {"hybrid", "api_only"}

    # keyless_default False -> key-first; True/None -> CLI-first.
    cli_first = keyless is not False

    if cli_first:
        order = [
            ("cli", lambda: _try_cli(role, provider, model, ttl_s) if cli_allowed else None),
            ("api", lambda: _try_api(role, model) if api_allowed else None),
        ]
    else:
        order = [
            ("api", lambda: _try_api(role, model) if api_allowed else None),
            ("cli", lambda: _try_cli(role, provider, model, ttl_s) if cli_allowed else None),
        ]

    for _name, attempt in order:
        handle = attempt()
        if handle is not None:
            return handle

    return _plan_floor(role, model, f"no usable CLI/API tier (mode={mode})")
