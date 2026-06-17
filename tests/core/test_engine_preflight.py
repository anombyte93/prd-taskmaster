"""Batched engine_preflight (dogfood finding 2026-06-11: skill UX shells out
to script.py repeatedly — one MCP call should cover the whole Phase 1)."""

import json
import sys
import textwrap
from pathlib import Path

from prd_taskmaster.batch import run_engine_preflight


def _clean_env(monkeypatch, tmp_path: Path, *, with_binary: bool = False) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    bin_dir = tmp_path / "bin"
    if with_binary:
        bin_dir.mkdir()
        script = bin_dir / "task-master"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import sys
                if sys.argv[1:] == ["--version"]:
                    print("0.43.1")
                    raise SystemExit(0)
                print("unexpected command", file=sys.stderr)
                raise SystemExit(2)
                """
            )
        )
        script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_engine_preflight_batches_all_phase1_signals(tmp_path, monkeypatch):
    _clean_env(monkeypatch, tmp_path)
    r = run_engine_preflight()
    assert r["ok"] is True
    # one call returns every Phase-1 signal
    for key in ("preflight", "taskmaster", "providers", "capabilities", "summary"):
        assert key in r, f"missing {key}"
    assert isinstance(r["summary"], list) and r["summary"], "human-readable summary lines"
    assert r["preflight"]["has_taskmaster"] is False  # fresh dir


def test_engine_preflight_never_mutates_without_project(tmp_path, monkeypatch):
    _clean_env(monkeypatch, tmp_path)
    run_engine_preflight()
    # no .taskmaster, no .env, nothing created in a bare dir (read-only probe)
    assert list(tmp_path.iterdir()) == []


def test_engine_preflight_reports_auto_native_even_with_taskmaster_binary(tmp_path, monkeypatch):
    # flipped: spec §9.2 — auto is always native, even with the task-master binary
    # present. The binary is still DETECTED (reported available), but it is no
    # longer SELECTED; native is the sole generator.
    _clean_env(monkeypatch, tmp_path, with_binary=True)

    result = run_engine_preflight()

    assert result["backend"]["selected"] == "native"
    assert result["backend"]["source"] == "auto"
    # the binary is still on PATH and detected, just not selected
    assert result["backend"]["taskmaster"]["available"] is True
    assert result["backend"]["taskmaster"]["version"] == "0.43.1"
    assert result["backend"]["taskmaster"]["min_ok"] is True
    assert result["backend"]["native"]["agent_fallback"] is True
    assert result["backend"]["ai_ops"] == "agent"
    assert "Backend: native (agent-driven)" in result["summary"]


def test_engine_preflight_reports_auto_native_agent_backend(tmp_path, monkeypatch):
    _clean_env(monkeypatch, tmp_path)

    result = run_engine_preflight()

    assert result["backend"]["selected"] == "native"
    assert result["backend"]["source"] == "auto"
    assert result["backend"]["taskmaster"]["available"] is False
    assert result["backend"]["native"] == {
        "api_provider": None,
        "agent_fallback": True,
    }
    assert result["backend"]["ai_ops"] == "agent"
    assert "Backend: native (agent-driven)" in result["summary"]


def test_engine_preflight_reports_config_forced_native(tmp_path, monkeypatch):
    _clean_env(monkeypatch, tmp_path, with_binary=True)
    config_dir = tmp_path / ".atlas-ai"
    config_dir.mkdir()
    (config_dir / "fleet.json").write_text(json.dumps({"backend": "native"}))

    result = run_engine_preflight()

    assert result["backend"]["selected"] == "native"
    assert result["backend"]["source"] == "config"
    assert result["backend"]["taskmaster"]["available"] is True
    assert result["backend"]["ai_ops"] == "agent"


def test_engine_preflight_configure_reports_deferred_on_fresh_project(tmp_path, monkeypatch):
    # Dogfood friction #5: configure=True on a fresh project returned a silent
    # providers_configured=None ("no-op"). It must now report an explicit,
    # structured deferred status WITHOUT mutating the bare directory.
    _clean_env(monkeypatch, tmp_path)

    result = run_engine_preflight(configure=True)

    pc = result["providers_configured"]
    assert isinstance(pc, dict), "configure step must never return a silent null"
    assert pc["ok"] is True
    assert pc["status"] == "deferred"
    assert "init-project" in pc["reason"]
    # the step is now visible in the human summary
    assert any("deferred" in line for line in result["summary"])
    # still read-only on a bare dir
    assert list(tmp_path.iterdir()) == []


def test_engine_preflight_no_configure_keeps_null(tmp_path, monkeypatch):
    # When the caller explicitly opts out, we don't fabricate a result.
    _clean_env(monkeypatch, tmp_path)
    result = run_engine_preflight(configure=False)
    assert result["providers_configured"] is None


def test_engine_preflight_summary_names_structured_gen_provider(tmp_path, monkeypatch):
    # Dogfood friction #4: "Backend: native (api: openai)" next to a
    # "Provider: claude-code" line read as a contradiction. The backend line
    # must name the structured-generation path explicitly.
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")

    result = run_engine_preflight()

    assert result["backend"]["ai_ops"] == "native-api"
    assert result["backend"]["native"]["api_provider"] == "openai"
    assert "Backend: native (structured-gen via openai API)" in result["summary"]
