"""Provider configuration and detection commands."""

import argparse
import os
import shutil
from pathlib import Path

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


def run_configure_providers() -> dict:
    """Configure TaskMaster for native Claude/Codex plus local Perplexity API Free when available."""
    config = _read_taskmaster_config()
    if not config:
        raise CommandError(".taskmaster/config.json not found or invalid; run task-master init first")

    models = config.setdefault("models", {})
    changed = []

    has_claude = shutil.which("claude") is not None
    has_codex = shutil.which("codex") is not None
    has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_claude:
        desired_main = {
            "provider": "claude-code",
            "modelId": "sonnet",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    elif has_codex:
        desired_main = {
            "provider": "codex-cli",
            "modelId": "gpt-5.2-codex",
            "maxTokens": 128000,
            "temperature": 0.2,
        }
    elif has_anthropic_key:
        desired_main = {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-20250514",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    else:
        desired_main = None

    if desired_main and models.get("main") != desired_main:
        models["main"] = desired_main
        changed.append("main")

    if has_codex:
        desired_fallback = {
            "provider": "codex-cli",
            "modelId": "gpt-5.2-codex",
            "maxTokens": 128000,
            "temperature": 0.2,
        }
    elif has_claude:
        desired_fallback = {
            "provider": "claude-code",
            "modelId": "sonnet",
            "maxTokens": 64000,
            "temperature": 0.2,
        }
    elif has_anthropic_key:
        desired_fallback = {
            "provider": "anthropic",
            "modelId": "claude-3-7-sonnet-20250219",
            "maxTokens": 120000,
            "temperature": 0.2,
        }
    else:
        desired_fallback = None

    if desired_fallback and models.get("fallback") != desired_fallback:
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
    if local_proxy_available:
        desired_research = {
            "provider": "openai-compatible",
            "modelId": "sonar",
            "maxTokens": 8700,
            "temperature": 0.1,
            "baseURL": local_proxy_url,
        }
        if models.get("research") != desired_research:
            models["research"] = desired_research
            changed.append("research")

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
