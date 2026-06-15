"""Setup wizard: detect+recommend panel, accept, add-key, validate.

Hermetic: every detector is monkeypatched and every subprocess.run is faked —
no real claude/codex/gemini is ever spawned, no network is touched.
"""
import json

import pytest

from prd_taskmaster import setup_wizard


def _stub_detectors(monkeypatch, *, claude=True, codex=True, gemini=False,
                    anthropic_key=False, perplexity_proxy=True):
    """Stub run_detect_providers + detect_capabilities so the panel is deterministic."""
    providers = {
        "main": {"provider": "claude-code" if claude else "anthropic",
                 "status": "detected", "source": "claude CLI"},
        "fallback": {"provider": "codex-cli" if codex else "claude-code",
                     "status": "detected", "source": "codex CLI"},
        "research": {"provider": "perplexity-api-free" if perplexity_proxy else "claude-code",
                     "status": "detected", "source": "proxy"},
    }
    monkeypatch.setattr(setup_wizard, "run_detect_providers",
                        lambda: {"ok": True, "providers": providers})
    caps = {
        "ok": True, "tier": "free",
        "recommended_mode": "C", "recommended_reason": "Plan + Ralph Loop",
        "capabilities": {"codex-cli": codex, "gemini-cli": gemini},
        "has_external_ai_tools": codex or gemini,
    }
    monkeypatch.setattr(setup_wizard, "detect_capabilities", lambda: caps)
    # PATH-based presence flags used by the env-detection line.
    def fake_which(name):
        return {
            "claude": "/usr/bin/claude" if claude else None,
            "codex": "/usr/bin/codex" if codex else None,
            "gemini": "/usr/bin/gemini" if gemini else None,
        }.get(name)
    monkeypatch.setattr(setup_wizard.shutil, "which", fake_which)
    if anthropic_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_recommend_panel_lists_each_role_with_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_detectors(monkeypatch)
    monkeypatch.setattr(setup_wizard, "_validate", lambda mode: {"ok": True, "ready": True, "checks": []})

    result = setup_wizard.run_setup(accept_default=True)

    panel = "\n".join(result["panel"])
    assert "Atlas detected" in panel
    assert "claude ✓" in panel
    assert "codex ✓" in panel
    assert "gemini ✗" in panel
    assert "main" in panel and "claude-code" in panel
    assert "fallback" in panel and "codex-cli" in panel
    assert "research" in panel
    assert result["recommendation"]["main"]["provider"] == "claude-code"
    assert result["ok"] is True
