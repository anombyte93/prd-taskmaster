"""Setup wizard — `atlas setup`.

Beats `task-master models --setup`: zero-config recommendation by default, an
optional guided layer that explains every auto-decision, and a live one-token
probe per chosen provider BEFORE the pipeline runs (the differentiator).

Steps: Detect&Recommend → Accept → Customise → Add-key (writes
engine.keyless_default after asking) → Validate.

Pure-core `run_setup()` returns a dict (never exits); `cmd_setup` is the CLI
wrapper. Interactivity is fully guarded behind `accept_default` / `validate_only`
so the function is non-interactive under --yes and in tests.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from prd_taskmaster import fleet
from prd_taskmaster.lib import _ensure_env_entry
from prd_taskmaster.mode_recommend import detect_capabilities, validate_setup
from prd_taskmaster.providers import run_configure_providers, run_detect_providers

# one-token live-probe commands per provider kind (Task 5)
_PROBE_CMD = {
    "claude-code": ["claude", "-p", "ok"],
    "codex-cli": ["codex", "--version"],
    "gemini-cli": ["gemini", "--version"],
}
_PROBE_TIMEOUT = 60


def _env_flag(name: str) -> bool:
    return bool(os.environ.get(name))


def _detect_line() -> str:
    """`Atlas detected:  claude ✓  codex ✓  gemini ✗  ANTHROPIC_API_KEY ✗ ...`"""
    def mark(ok: bool) -> str:
        return "✓" if ok else "✗"
    claude = shutil.which("claude") is not None
    codex = shutil.which("codex") is not None
    gemini = shutil.which("gemini") is not None
    akey = _env_flag("ANTHROPIC_API_KEY")
    pkey = _env_flag("PERPLEXITY_API_KEY") or _env_flag("PERPLEXITY_API_BASE_URL")
    return (
        f"Atlas detected:  claude {mark(claude)}   codex {mark(codex)}   "
        f"gemini {mark(gemini)}   ANTHROPIC_API_KEY {mark(akey)}   "
        f"PERPLEXITY {mark(pkey)}"
    )


_ROLE_REASON = {
    "claude-code": "free via your Claude session, no API key",
    "codex-cli": "separate quota pool, runs in parallel",
    "gemini-cli": "separate quota pool",
    "anthropic": "paid Anthropic API key",
    "perplexity-api-free": "local proxy on :8765",
    "perplexity": "Perplexity API key",
}


def _recommend() -> dict:
    """Reuse the zero-config detectors and shape a per-role recommendation."""
    detected = run_detect_providers().get("providers", {})
    caps = detect_capabilities()
    recommendation = {}
    for role in ("main", "fallback", "research"):
        entry = detected.get(role, {})
        provider = entry.get("provider", "")
        recommendation[role] = {
            "provider": provider,
            "modelId": entry.get("modelId"),
            "source": entry.get("source", "-"),
            "reason": _ROLE_REASON.get(provider, entry.get("source", "")),
        }
    return {"recommendation": recommendation, "capabilities": caps}


def _panel(recommendation: dict, caps: dict) -> list[str]:
    lines = [_detect_line(), ""]
    lines.append("Recommended (zero-config, keyless):")
    for role in ("main", "fallback", "research"):
        rec = recommendation[role]
        model = rec.get("modelId") or ""
        label = f"{rec['provider']}/{model}".rstrip("/")
        lines.append(f"  {role:<9} {label:<28} ← {rec['reason']}")
    lines.append(
        f"Tier: {caps.get('tier', 'free')} — {caps.get('recommended_reason', '')}"
    )
    lines.append("[Enter] accept   [c] customise   [k] add an API key   [v] validate only")
    return lines


def _validate(mode: str | None) -> dict:
    """Indirection so tests can stub the heavy validate path. Calls the
    refactored validate_setup with the resolved provider_mode."""
    return validate_setup(provider_mode=mode)


def run_setup(accept_default: bool = False, validate_only: bool = False) -> dict:
    """Drive the wizard. Returns a dict; never exits, never raises on the
    happy path. Non-interactive when accept_default or validate_only is set."""
    rec = _recommend()
    recommendation = rec["recommendation"]
    caps = rec["capabilities"]
    panel = _panel(recommendation, caps)

    result = {
        "ok": True,
        "panel": panel,
        "recommendation": recommendation,
        "tier": caps.get("tier", "free"),
    }
    # Accept / customise / add-key / validate are layered in Tasks 3–4.
    return result
