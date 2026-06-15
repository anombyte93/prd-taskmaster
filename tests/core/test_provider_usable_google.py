"""Acceptance gate (dogfood bench T3): google/gemini are raw-API providers, so
their usability must be gated on a Google API key — in _provider_usable AND wired
through validate_setup. Cross-file (providers.py + mode_recommend.py).

Context: llm_client now supports a 'google' provider (GOOGLE_API_KEY / GEMINI_API_KEY).
But _provider_usable still treats 'google'/'gemini' as unknown → always usable,
so validate_setup green-lights a google main with no key (the same class of
silent-0-task defect the anthropic/openai checks already prevent).

Contract:
  _provider_usable("google", has_google_key=True,  ...) -> True
  _provider_usable("google", has_google_key=False, ...) -> False
  _provider_usable("gemini", has_google_key=False, ...) -> False
  _provider_usable("openrouter", ...)                   -> True   (unknown still assumed usable)
  has_google_key must default to False so existing callers don't break.
  validate_setup: a google main with NO GOOGLE_API_KEY/GEMINI_API_KEY -> provider_main fails;
  with a key set -> passes.

This file is the fixed contract; the worker may NOT edit it.
"""

import json

import pytest

from prd_taskmaster import mode_recommend
from prd_taskmaster.providers import _provider_usable

_BASE = dict(
    has_claude=False, has_codex=False,
    has_anthropic_key=False, has_openai_key=False, has_perplexity_key=False,
)


def test_google_usable_only_with_key():
    assert _provider_usable("google", has_google_key=True, **_BASE) is True
    assert _provider_usable("google", has_google_key=False, **_BASE) is False


def test_gemini_alias_usable_only_with_key():
    assert _provider_usable("gemini", has_google_key=True, **_BASE) is True
    assert _provider_usable("gemini", has_google_key=False, **_BASE) is False


def test_has_google_key_defaults_false_backcompat():
    # existing callers that don't pass has_google_key must still work,
    # and a google provider without the kwarg is treated as not-usable
    assert _provider_usable("google", **_BASE) is False


def test_unknown_provider_still_assumed_usable():
    assert _provider_usable("openrouter", **_BASE) is True
    assert _provider_usable("ollama", has_google_key=False, **_BASE) is True


def test_existing_providers_unchanged():
    assert _provider_usable("anthropic", **{**_BASE, "has_anthropic_key": True}) is True
    assert _provider_usable("anthropic", **_BASE) is False


def _seed_google_config(tmp_path):
    tm = tmp_path / ".taskmaster"
    tm.mkdir(parents=True, exist_ok=True)
    (tm / "config.json").write_text(json.dumps({
        "models": {
            "main": {"provider": "google", "modelId": "gemini-2.5-flash"},
            "research": {"provider": "perplexity", "modelId": "sonar"},
        }
    }))


def _not_nested(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)


def test_validate_setup_gates_google_main_on_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_google_config(tmp_path)
    _not_nested(monkeypatch)
    monkeypatch.setattr(mode_recommend.shutil, "which", lambda name: None)
    for v in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)

    result = mode_recommend.validate_setup(provider_mode="hybrid")
    provider_main = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert provider_main["passed"] is False  # google main, no key -> not usable


def test_validate_setup_passes_google_main_with_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_google_config(tmp_path)
    _not_nested(monkeypatch)
    monkeypatch.setattr(mode_recommend.shutil, "which", lambda name: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")

    result = mode_recommend.validate_setup(provider_mode="hybrid")
    provider_main = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert provider_main["passed"] is True
