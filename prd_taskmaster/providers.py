"""Provider configuration and detection commands."""

import argparse
import os
import shutil
from pathlib import Path

from prd_taskmaster.economy import TIER_MODEL_IDS, economy_profile
from prd_taskmaster.fleet import load_fleet_config
from prd_taskmaster.lib import (
    CommandError,
    emit,
    fail,
    _detect_perplexity_mcp,
    _ensure_env_entry,
    _is_local_perplexity_free,
    _local_port_open,
    _read_env_file_value,
    _read_taskmaster_config,
    _read_taskmaster_model,
    _write_taskmaster_config,
)


KNOWN_ENGINE_DEFAULTS = [
    {
        "provider": "claude-code",
        "modelId": "sonnet",
        "maxTokens": 64000,
        "temperature": 0.2,
    },
    {
        "provider": "codex-cli",
        "modelId": "gpt-5.2-codex",
        "maxTokens": 128000,
        "temperature": 0.2,
    },
    {
        "provider": "anthropic",
        "modelId": "claude-sonnet-4-20250514",
        "maxTokens": 64000,
        "temperature": 0.2,
    },
]

_CLI_DELEGATION_PROVIDERS = {"claude-code", "codex-cli"}
_STRUCTURED_GEN_TIER_MODELS = {
    "fast": "haiku",
    "standard": "sonnet",
    "capable": "opus",
    "frontier": "fable",
}


def _role_empty(value: object) -> bool:
    return not isinstance(value, dict) or not value


def _resolve_configure_profile(economy: str | None) -> dict:
    cfg = load_fleet_config() if economy is None else {"token_economy": economy}
    return economy_profile(cfg)


def _desired_main_model(has_claude: bool, has_codex: bool, has_anthropic_key: bool) -> dict | None:
    if has_claude:
        return {
            "provider": "claude-code",
            "modelId": "sonnet",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    if has_codex:
        return {
            "provider": "codex-cli",
            "modelId": "gpt-5.2-codex",
            "maxTokens": 128000,
            "temperature": 0.2,
        }
    if has_anthropic_key:
        return {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-20250514",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    return None


def _desired_fallback_model(has_claude: bool, has_codex: bool, has_anthropic_key: bool) -> dict | None:
    if has_codex:
        return {
            "provider": "codex-cli",
            "modelId": "gpt-5.2-codex",
            "maxTokens": 128000,
            "temperature": 0.2,
        }
    if has_claude:
        return {
            "provider": "claude-code",
            "modelId": "sonnet",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    if has_anthropic_key:
        return {
            "provider": "anthropic",
            "modelId": "claude-3-7-sonnet-20250219",
            "maxTokens": 120000,
            "temperature": 0.2,
        }
    return None


def _main_model_for_start_tier(model: dict, tier: str) -> dict:
    model_name = _STRUCTURED_GEN_TIER_MODELS.get(tier, tier)
    provider = str(model.get("provider", "")).lower()
    adjusted = dict(model)
    if provider in _CLI_DELEGATION_PROVIDERS:
        adjusted["modelId"] = model_name
    elif provider == "anthropic":
        adjusted["modelId"] = TIER_MODEL_IDS.get(model_name, model_name)
    return adjusted


def _has_perplexity_api_key() -> bool:
    return bool(
        os.environ.get("PERPLEXITY_API_KEY")
        or _read_env_file_value(Path(".env"), "PERPLEXITY_API_KEY")
    )


def _perplexity_research_model(model_id: str) -> dict:
    return {
        "provider": "perplexity",
        "modelId": model_id,
        "maxTokens": 8700,
        "temperature": 0.1,
    }


def _local_proxy_research_model(local_proxy_url: str) -> dict:
    return {
        "provider": "openai-compatible",
        "modelId": "sonar",
        "maxTokens": 8700,
        "temperature": 0.1,
        "baseURL": local_proxy_url,
    }


def run_configure_providers(economy: str | None = None) -> dict:
    """Configure TaskMaster for native Claude/Codex plus local Perplexity API Free when available."""
    config = _read_taskmaster_config()
    if not config:
        raise CommandError(
            ".taskmaster/config.json not found or invalid; initialise TaskMaster first",
            {
                "recommended_action": "init_taskmaster",
                "fix": "python3 script.py init-taskmaster",
                "note": "init-taskmaster preserves an existing .mcp.json (raw 'task-master init' overwrites it)",
            },
        )

    models = config.setdefault("models", {})
    changed = []
    profile = _resolve_configure_profile(economy)
    result_extra = {}

    has_claude = shutil.which("claude") is not None
    has_codex = shutil.which("codex") is not None
    has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    desired_main = _desired_main_model(has_claude, has_codex, has_anthropic_key)
    start_tier = profile.get("structured_gen_start", "standard")
    current_main = models.get("main")
    if _role_empty(current_main):
        if desired_main:
            models["main"] = _main_model_for_start_tier(desired_main, start_tier)
            changed.append("main")
    elif start_tier != "standard":
        if current_main in KNOWN_ENGINE_DEFAULTS:
            desired_tier_main = _main_model_for_start_tier(current_main, start_tier)
            if current_main != desired_tier_main:
                models["main"] = desired_tier_main
                changed.append("main")
        else:
            result_extra["skipped_main"] = "user-configured"

    desired_fallback = _desired_fallback_model(has_claude, has_codex, has_anthropic_key)
    if desired_fallback and _role_empty(models.get("fallback")):
        models["fallback"] = desired_fallback
        changed.append("fallback")

    existing_research = models.get("research") if isinstance(models.get("research"), dict) else {}
    local_proxy_url = (
        _read_env_file_value(Path(".env"), "PERPLEXITY_API_BASE_URL")
        or existing_research.get("baseURL")
        or os.environ.get("PERPLEXITY_API_BASE_URL")
        or os.environ.get("PERPLEXITY_API_FREE_BASE_URL")
        or "http://127.0.0.1:8765"
    )
    local_proxy_available = (
        "127.0.0.1:8765" in local_proxy_url
        or "localhost:8765" in local_proxy_url
        or _local_port_open()
    )
    if _role_empty(models.get("research")):
        desired_research = None
        research_choice = profile.get("research_choice", "real_api_if_key")
        has_perplexity_key = _has_perplexity_api_key()
        if research_choice == "real_api_if_key" and has_perplexity_key:
            desired_research = _perplexity_research_model("sonar")
        elif research_choice == "best_available" and has_perplexity_key:
            desired_research = _perplexity_research_model("sonar-pro")
        elif local_proxy_available:
            desired_research = _local_proxy_research_model(local_proxy_url)

        if desired_research:
            models["research"] = desired_research
            changed.append("research")

    if _is_local_perplexity_free(models.get("research", {})):
        if _ensure_env_entry(Path(".env"), "OPENAI_COMPATIBLE_API_KEY", "local-perplexity-api-free"):
            changed.append(".env:OPENAI_COMPATIBLE_API_KEY")
        if _ensure_env_entry(Path(".env"), "PERPLEXITY_API_BASE_URL", local_proxy_url):
            changed.append(".env:PERPLEXITY_API_BASE_URL")
        if Path(".env.example").is_file():
            if _ensure_env_entry(
                Path(".env.example"),
                "OPENAI_COMPATIBLE_API_KEY",
                "local-perplexity-api-free",
                "Local only: dummy key for local Perplexity API Free proxy.",
            ):
                changed.append(".env.example:OPENAI_COMPATIBLE_API_KEY")
            if _ensure_env_entry(
                Path(".env.example"),
                "PERPLEXITY_API_BASE_URL",
                local_proxy_url,
                "Local only: Perplexity API Free proxy endpoint.",
            ):
                changed.append(".env.example:PERPLEXITY_API_BASE_URL")

    config.setdefault("global", {}).setdefault("defaultTag", "master")
    _write_taskmaster_config(config)

    return {
        "ok": True,
        "changed": changed,
        "models": models,
        "local_perplexity_api_free": local_proxy_available,
        "local_perplexity_api_free_url": local_proxy_url if local_proxy_available else None,
        "economy": profile["mode"],
        **result_extra,
    }


def cmd_configure_providers(args: argparse.Namespace) -> None:
    try:
        emit(run_configure_providers())
    except CommandError as e:
        fail(e.message, **e.extra)


def run_detect_providers() -> dict:
    """Auto-detect and report available AI providers. Zero questions asked."""
    providers = {}

    main_model = _read_taskmaster_model("main")
    fallback_model = _read_taskmaster_model("fallback")
    research_model = _read_taskmaster_model("research")

    # Prefer the concrete TaskMaster project config when native CLI providers are wired.
    main_provider = str(main_model.get("provider", "")).lower()
    fallback_provider = str(fallback_model.get("provider", "")).lower()
    if main_provider in {"claude-code", "codex-cli"}:
        providers["main"] = {
            "provider": main_provider,
            "status": "detected",
            "source": ".taskmaster/config.json",
            "modelId": main_model.get("modelId"),
        }
    if fallback_provider in {"claude-code", "codex-cli"}:
        providers["fallback"] = {
            "provider": fallback_provider,
            "status": "detected",
            "source": ".taskmaster/config.json",
            "modelId": fallback_model.get("modelId"),
        }

    # Check Anthropic API key / native CLI fallbacks.
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and "main" not in providers:
        providers["main"] = {"provider": "anthropic", "status": "detected", "source": "ANTHROPIC_API_KEY env"}
    elif "main" not in providers and shutil.which("claude"):
        providers["main"] = {"provider": "claude-code", "status": "detected", "source": "claude CLI"}
    elif "main" not in providers and shutil.which("codex"):
        providers["main"] = {"provider": "codex-cli", "status": "detected", "source": "codex CLI"}
    elif "main" not in providers:
        providers["main"] = {"provider": "claude-code", "status": "fallback", "source": "Claude Max/Pro subscription"}

    if api_key and "fallback" not in providers:
        providers["fallback"] = {"provider": "anthropic", "status": "detected", "source": "ANTHROPIC_API_KEY env"}
    elif "fallback" not in providers and shutil.which("codex"):
        providers["fallback"] = {"provider": "codex-cli", "status": "detected", "source": "codex CLI"}
    elif "fallback" not in providers and shutil.which("claude"):
        providers["fallback"] = {"provider": "claude-code", "status": "fallback", "source": "Claude Max/Pro subscription"}
    elif "fallback" not in providers:
        providers["fallback"] = {"provider": "claude-code", "status": "fallback", "source": "No native CLI found"}

    # Check Perplexity - local free proxy / MCP first, then paid API key.
    perplexity_mcp = _detect_perplexity_mcp()

    perplexity_key = os.environ.get("PERPLEXITY_API_KEY", "")

    if _is_local_perplexity_free(research_model):
        providers["research"] = {
            "provider": "perplexity-api-free",
            "status": "detected",
            "source": ".taskmaster/config.json research.baseURL",
            "modelId": research_model.get("modelId"),
            "baseURL": research_model.get("baseURL"),
        }
    elif perplexity_mcp:
        providers["research"] = {"provider": perplexity_mcp, "status": "detected", "source": "MCP server"}
    elif perplexity_key:
        providers["research"] = {"provider": "perplexity", "status": "detected", "source": "PERPLEXITY_API_KEY env"}
    else:
        providers["research"] = {"provider": "claude-code", "status": "fallback", "source": "No Perplexity — using Claude Code"}

    return {"ok": True, "providers": providers}


def cmd_detect_providers(args: argparse.Namespace) -> None:
    try:
        emit(run_detect_providers())
    except CommandError as e:
        fail(e.message, **e.extra)
