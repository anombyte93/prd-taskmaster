"""validate_setup: task-master binary/version checks are advisory in hybrid mode."""
import json

import pytest

from prd_taskmaster import mode_recommend


def _no_taskmaster(monkeypatch):
    """No task-master binary on PATH, no claude/codex either."""
    monkeypatch.setattr(mode_recommend.shutil, "which", lambda name: None)


def _not_nested(monkeypatch):
    """Deterministic non-nested context so the main-provider spawn probe does not
    fire (provider_main usability then turns purely on the credential/CLI check)."""
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)

def _seed_config(tmp_path, main_provider="claude-code"):
    tm = tmp_path / ".taskmaster"
    tm.mkdir(parents=True, exist_ok=True)
    (tm / "config.json").write_text(json.dumps({
        "models": {
            "main": {"provider": main_provider, "modelId": "sonnet"},
            "research": {"provider": "perplexity", "modelId": "sonar"},
            "fallback": {"provider": "codex-cli", "modelId": "gpt-5.2-codex"},
        }
    }))


def test_hybrid_mode_does_not_hard_fail_on_missing_taskmaster(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_config(tmp_path)
    _not_nested(monkeypatch)
    _no_taskmaster(monkeypatch)
    # claude usable so provider_main passes; only the task-master checks would fail.
    monkeypatch.setattr(mode_recommend.shutil, "which",
                        lambda name: "/usr/bin/claude" if name == "claude" else None)

    result = mode_recommend.validate_setup(provider_mode="hybrid")

    binary = next(c for c in result["checks"] if c["id"] == "binary")
    version = next(c for c in result["checks"] if c["id"] == "version")
    assert binary["severity"] == "advisory"
    assert version["severity"] == "advisory"
    # binary/version are NOT in critical_failures even though they "failed"
    assert not binary["passed"]
    assert result["critical_failures"] == 0
    assert result["ready"] is True


def test_plan_only_mode_still_hard_fails_on_missing_taskmaster(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_config(tmp_path)
    _no_taskmaster(monkeypatch)

    result = mode_recommend.validate_setup(provider_mode="plan_only")

    binary = next(c for c in result["checks"] if c["id"] == "binary")
    assert binary.get("severity") != "advisory"
    assert not binary["passed"]
    assert result["critical_failures"] >= 1
    assert result["ready"] is False


def test_default_provider_mode_reads_engine_config_hybrid(tmp_path, monkeypatch):
    """No explicit provider_mode → engine_config() default 'hybrid' → advisory."""
    monkeypatch.chdir(tmp_path)
    _seed_config(tmp_path)
    _not_nested(monkeypatch)
    monkeypatch.setattr(mode_recommend.shutil, "which",
                        lambda name: "/usr/bin/claude" if name == "claude" else None)

    result = mode_recommend.validate_setup()  # no arg → engine_config default

    binary = next(c for c in result["checks"] if c["id"] == "binary")
    assert binary["severity"] == "advisory"
    assert result["ready"] is True
