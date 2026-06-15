"""Pre-relaunch P0 regression tests (docs/audit/AUDIT.md, 2026-06-14).

These encode the three first-run blockers found by the pre-relaunch audit, each
reproduced firsthand against the 5.2.0 first-run path:

  P0-1  configure-providers no-op on TaskMaster's stock paid defaults
  P0-2  SETUP gate reports ready=True for a keyless (0-task) config
  P0-3  expand hard-fails when research provider is down (no structural degrade)

The unifying bias they correct: the prior suite only asserted "leave the user's
config alone" against EMPTY/customized baselines — never "CORRECT a keyless stock
default", which is the exact state `task-master init` creates.
"""

import json
from pathlib import Path

from prd_taskmaster.mode_recommend import validate_setup
from prd_taskmaster.providers import run_configure_providers


# ── shared fixtures (self-contained; mirror test_dogfood_fixes helpers) ──────

# The exact roles `task-master init` writes by default (the real dogfood config).
STOCK_PAID_DEFAULTS = {
    "main": {
        "provider": "anthropic",
        "modelId": "claude-sonnet-4-20250514",
        "maxTokens": 64000,
        "temperature": 0.2,
    },
    "research": {
        "provider": "perplexity",
        "modelId": "sonar",
        "maxTokens": 8700,
        "temperature": 0.1,
    },
    "fallback": {
        "provider": "anthropic",
        "modelId": "claude-3-7-sonnet-20250219",
        "maxTokens": 120000,
        "temperature": 0.2,
    },
}


def _seed_taskmaster_config(root: Path, models: dict) -> None:
    taskmaster = root / ".taskmaster"
    taskmaster.mkdir(exist_ok=True)
    (taskmaster / "config.json").write_text(json.dumps({"models": models}, indent=2))


def _patch_env(monkeypatch, *, claude: bool = False, codex: bool = False) -> None:
    def fake_which(name: str) -> str | None:
        if name == "claude" and claude:
            return "/fake/bin/claude"
        if name == "codex" and codex:
            return "/fake/bin/codex"
        return None

    monkeypatch.setattr("prd_taskmaster.providers.shutil.which", fake_which)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_BASE_URL", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_FREE_BASE_URL", raising=False)


# ── P0-1: configure must REPAIR keyless stock paid defaults ──────────────────

def test_configure_repairs_keyless_stock_paid_trio_to_free_clis(tmp_path, monkeypatch):
    """The dogfood failure: init writes the paid anthropic+perplexity trio, the user
    has no ANTHROPIC_API_KEY/PERPLEXITY_API_KEY but DOES have the claude+codex CLIs.
    configure-providers must migrate all three unusable roles to the free paths, not
    no-op on them (which left the first run producing 0 tasks)."""
    monkeypatch.chdir(tmp_path)
    _patch_env(monkeypatch, claude=True, codex=True)
    _seed_taskmaster_config(tmp_path, {k: dict(v) for k, v in STOCK_PAID_DEFAULTS.items()})

    result = run_configure_providers(economy="balanced")

    assert result["models"]["main"]["provider"] == "claude-code"
    assert result["models"]["fallback"]["provider"] == "codex-cli"
    # dead paid Perplexity (no key) must yield to the free local proxy
    assert result["models"]["research"]["provider"] == "openai-compatible"
    assert "main" in result["changed"]
    assert "fallback" in result["changed"]
    assert "research" in result["changed"]


def test_configure_preserves_usable_stock_anthropic_when_key_present(tmp_path, monkeypatch):
    """Repair is scoped to UNUSABLE roles: a stock anthropic main WITH a real key is a
    working config — leave its provider alone (don't yank a paying user onto the CLI)."""
    monkeypatch.chdir(tmp_path)
    _patch_env(monkeypatch, claude=True, codex=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    _seed_taskmaster_config(tmp_path, {"main": dict(STOCK_PAID_DEFAULTS["main"])})

    result = run_configure_providers(economy="balanced")

    assert result["models"]["main"]["provider"] == "anthropic"
    assert "main" not in result["changed"]


# ── P0-2: SETUP gate must be credential-aware, not string-presence ───────────

def _patch_setup_env(monkeypatch, *, claude=False, codex=False):
    """Make the task-master binary check pass while controlling CLI/key availability
    for the provider-usability checks."""
    def fake_which(name: str) -> str | None:
        if "task-master" in name or name == "taskmaster":
            return "/fake/bin/task-master"
        if name == "claude" and claude:
            return "/fake/bin/claude"
        if name == "codex" and codex:
            return "/fake/bin/codex"
        return None

    monkeypatch.setattr("prd_taskmaster.mode_recommend.shutil.which", fake_which)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    # base setup tests are non-nested + deterministic; nested tests opt in explicitly
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)


def test_validate_setup_fails_on_keyless_paid_main_provider(tmp_path, monkeypatch):
    """The gate green-lit the exact 0-task config: a paid 'anthropic' main with no
    ANTHROPIC_API_KEY and no claude/codex CLI. A model-id string is present but the
    provider cannot run — ready must be False with a critical failure."""
    monkeypatch.chdir(tmp_path)
    _patch_setup_env(monkeypatch, claude=False, codex=False)
    _seed_taskmaster_config(tmp_path, {k: dict(v) for k, v in STOCK_PAID_DEFAULTS.items()})

    result = validate_setup()

    main_check = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert main_check["passed"] is False
    assert result["ready"] is False
    assert result["critical_failures"] >= 1
    assert main_check["fix"]  # actionable remediation present


def test_validate_setup_passes_when_main_provider_is_usable(tmp_path, monkeypatch):
    """The corrected free config (main on the claude CLI) must pass the gate."""
    monkeypatch.chdir(tmp_path)
    _patch_setup_env(monkeypatch, claude=True, codex=True)
    _seed_taskmaster_config(tmp_path, {
        "main": {"provider": "claude-code", "modelId": "sonnet"},
        "research": {"provider": "claude-code", "modelId": "sonnet"},
        "fallback": {"provider": "codex-cli", "modelId": "gpt-5.2-codex"},
    })

    result = validate_setup()

    main_check = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert main_check["passed"] is True
    assert result["ready"] is True


# NOTE: P0-3 (expand must degrade to structural when research provider is down)
# previously tested tm_parallel._run_packet against a fake `task-master` binary.
# The task-master backend was removed (spec §9.4) — native is the sole generator —
# so the binary-path degrade tests were deleted with the module. The native
# engine's structural-decomposition fallback lives in NativeBackend.expand.


# ── #11/#12: nested-session spawn PROBE (verify, don't assume) ───────────────

def test_is_nested_claude_detects_env(monkeypatch):
    from prd_taskmaster.providers import _is_nested_claude

    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)
    assert _is_nested_claude() is False

    monkeypatch.setenv("CLAUDECODE", "1")
    assert _is_nested_claude() is True


def test_validate_setup_fails_when_nested_claude_code_spawn_probe_fails(tmp_path, monkeypatch):
    """#11/#12: if the claude-code main provider genuinely cannot spawn in this nested
    session (probe fails), the gate must fail with an actionable error — NOT silently
    pass and let parse_prd die with exit 1 / no tasks. (Probe, not assume.)"""
    monkeypatch.chdir(tmp_path)
    _patch_setup_env(monkeypatch, claude=True, codex=True)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setattr("prd_taskmaster.mode_recommend._probe_spawn", lambda provider: False)
    _seed_taskmaster_config(tmp_path, {
        "main": {"provider": "claude-code", "modelId": "sonnet"},
        "research": {"provider": "perplexity", "modelId": "sonar"},
        "fallback": {"provider": "codex-cli", "modelId": "gpt-5.2-codex"},
    })

    result = validate_setup()

    main_check = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert main_check["passed"] is False
    assert result["ready"] is False
    assert "--claude-code" not in (main_check["fix"] or "")
    assert "nest" in (main_check["detail"] or "").lower()


def test_validate_setup_passes_when_nested_claude_code_spawn_probe_succeeds(tmp_path, monkeypatch):
    """The contradicting case: nested but claude-code spawns fine (current versions).
    The gate must NOT regress the free working path to a forced reroute."""
    monkeypatch.chdir(tmp_path)
    _patch_setup_env(monkeypatch, claude=True, codex=True)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setattr("prd_taskmaster.mode_recommend._probe_spawn", lambda provider: True)
    _seed_taskmaster_config(tmp_path, {
        "main": {"provider": "claude-code", "modelId": "sonnet"},
        "research": {"provider": "perplexity", "modelId": "sonar"},
        "fallback": {"provider": "claude-code", "modelId": "sonnet"},
    })

    result = validate_setup()

    main_check = next(c for c in result["checks"] if c["id"] == "provider_main")
    assert main_check["passed"] is True
    assert result["ready"] is True


# ── #13: preflight flags a stale (all-done) tag + suggests a fresh one ───────

def test_preflight_flags_stale_tag_and_suggests_fresh(tmp_path, monkeypatch):
    """A non-empty but fully-done current tag is 'stale': parsing a new PRD into it
    would pollute the old graph. preflight must flag it and suggest a fresh tag."""
    from prd_taskmaster.pipeline import preflight

    monkeypatch.chdir(tmp_path)
    tm = tmp_path / ".taskmaster"
    (tm / "docs").mkdir(parents=True)
    (tm / "tasks").mkdir(parents=True)
    (tm / "docs" / "prd.md").write_text("# New PRD\n")
    (tm / "state.json").write_text('{"currentTag":"master"}')
    (tm / "tasks" / "tasks.json").write_text(
        '{"master":{"tasks":[{"id":1,"title":"old","status":"done"}]}}'
    )

    result = preflight()

    assert result["current_tag_stale"] is True
    assert result["suggested_fresh_tag"]
    assert result["suggested_fresh_tag"] != "master"


def test_preflight_not_stale_when_pending_work_remains(tmp_path, monkeypatch):
    from prd_taskmaster.pipeline import preflight

    monkeypatch.chdir(tmp_path)
    tm = tmp_path / ".taskmaster"
    (tm / "docs").mkdir(parents=True)
    (tm / "tasks").mkdir(parents=True)
    (tm / "docs" / "prd.md").write_text("# PRD\n")
    (tm / "state.json").write_text('{"currentTag":"master"}')
    (tm / "tasks" / "tasks.json").write_text(
        '{"master":{"tasks":[{"id":1,"title":"todo","status":"pending"}]}}'
    )

    result = preflight()

    assert result["current_tag_stale"] is False
    assert result["suggested_fresh_tag"] is None
