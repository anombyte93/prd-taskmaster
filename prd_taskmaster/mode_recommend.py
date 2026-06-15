"""
Capability detection for the PRD-TaskMaster plugin.

Ported from prd-taskmaster-v4 script.py (cmd_detect_taskmaster,
cmd_detect_capabilities, cmd_validate_setup).

All functions return dicts — never terminate the process (per spec §13.3).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from prd_taskmaster.fleet import engine_config
from prd_taskmaster.lib import emit_json_error
from prd_taskmaster.providers import (
    _has_perplexity_api_key,
    _is_nested_claude,
    _is_spawning_provider,
    _probe_spawn,
    _provider_usable,
)

# ---------------------------------------------------------------------------
# Constants (mirrored from v4 script.py)
# ---------------------------------------------------------------------------

TASKMASTER_DIR = Path(".taskmaster")
TASKMASTER_MIN_VERSION = "0.43.0"
ATLAS_FLEET_REASON = "Atlas Fleet — atlas-launcher detected (parallel multi-session execution)"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver-ish string into a comparable tuple.

    Strips leading 'v' and ignores any pre-release suffix after '-'.
    Returns (0, 0, 0) on parse failure so comparison is always safe.
    """
    try:
        v = v.strip().lstrip("v").split("-")[0]
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


def _check_taskmaster_version(cli_path: str | None) -> dict:
    """Probe the task-master binary for version and compare against minimum.

    Returns:
      detected_version: str | None
      supported: bool — True if >= TASKMASTER_MIN_VERSION
      warning: str | None
    """
    if not cli_path:
        return {
            "detected_version": None,
            "supported": False,
            "warning": "task-master binary not found",
        }
    try:
        result = subprocess.run(
            [cli_path, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        detected = result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        detected = None

    if not detected:
        return {
            "detected_version": None,
            "supported": False,
            "warning": "could not read task-master --version output",
        }

    dv = _parse_version(detected)
    mv = _parse_version(TASKMASTER_MIN_VERSION)
    supported = dv >= mv

    return {
        "detected_version": detected,
        "minimum_version": TASKMASTER_MIN_VERSION,
        "supported": supported,
        "warning": (
            None if supported
            else f"task-master {detected} is older than minimum supported {TASKMASTER_MIN_VERSION}. Upgrade: npm install -g task-master-ai@latest"
        ),
    }


def _safe_call(fn) -> bool:
    """Run a detection lambda, swallowing exceptions as False."""
    try:
        return bool(fn())
    except Exception:
        return False


def _mcp_config_has_server(
    config_path: Path,
    server_name: str,
    *,
    allow_top_level: bool = False,
) -> bool:
    """Return True when an MCP config declares the exact server key."""
    if not config_path.is_file():
        return False

    try:
        with open(config_path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False

    if not isinstance(config, dict):
        return False

    servers = config.get("mcpServers")
    if isinstance(servers, dict) and server_name in servers:
        return True

    return allow_top_level and server_name in config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_atlas_launcher() -> dict:
    """Detect the Atlas Fleet launcher binary and MCP registration."""
    installed = bool(
        shutil.which("atlas-launcher")
        or shutil.which("atlas")
    )

    config_paths: list[tuple[Path, bool]] = []
    try:
        config_paths.append((Path.home() / ".claude.json", False))
    except RuntimeError:
        pass
    config_paths.append((Path(".mcp.json"), True))

    mcp_registered = any(
        _mcp_config_has_server(
            config_path,
            "atlas-launcher",
            allow_top_level=allow_top_level,
        )
        for config_path, allow_top_level in config_paths
    )

    return {
        "installed": installed,
        "mcp_registered": mcp_registered,
    }


def detect_taskmaster() -> dict:
    """Detect taskmaster availability: MCP > CLI > none.

    Returns:
      ok: True
      method: "cli" | "mcp" | "none"
      version: str | None   (CLI version string, if found)
      path: str | None      (resolved CLI path, if found)
    """
    # Check CLI — all three known entry-point names.
    cli_path = (
        shutil.which("task-master")
        or shutil.which("task-master-ai")
        or shutil.which("taskmaster")
    )
    cli_version: str | None = None
    if cli_path:
        try:
            result = subprocess.run(
                [cli_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            cli_version = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # MCP detection: look for task-master-ai entry in known config files.
    mcp_available = False
    for config_path in [
        Path.home() / ".claude" / "settings" / "mcp.json",
        Path.home() / ".config" / "claude-code" / "mcp.json",
        Path(".mcp.json"),
    ]:
        if config_path.is_file():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", config.get("servers", {}))
                if any("task-master" in k.lower() for k in servers):
                    mcp_available = True
                    break
            except (json.JSONDecodeError, KeyError, OSError):
                pass

    if mcp_available:
        return {"ok": True, "method": "mcp", "version": None, "path": None}
    elif cli_path:
        return {"ok": True, "method": "cli", "version": cli_version, "path": cli_path}
    else:
        return {"ok": True, "method": "none", "version": None, "path": None}


def detect_capabilities() -> dict:
    """Scan for available skills, tools, plugins, and external AI tools.

    v4 is designed to be tool-agnostic. Detection covers:
      - Claude Code plugins (superpowers, atlas-*)
      - Claude Code skills (cdd, ralph-loop, phase-executor, etc.)
      - External AI tools (Cursor, RooCode, Codex CLI, Gemini CLI, etc.)
      - TaskMaster (CLI or MCP)

    Returns:
      ok: True
      tier: "free" | "premium"
      has_superpowers: bool
      has_taskmaster: bool
      has_atlas_premium: bool
      capabilities: dict     (per-tool flags)
      recommended_mode: str
      recommended_reason: str
      alternative_modes: list
      has_external_ai_tools: bool
    """
    capabilities: dict[str, Any] = {}

    # ── Claude Code plugin detection ──────────────────────────────────
    superpowers_paths = [
        Path.home() / ".claude" / "plugins" / "cache" / "claude-plugins-official" / "superpowers",
        Path.home() / ".claude" / "plugins" / "superpowers",
    ]
    capabilities["superpowers"] = any(p.is_dir() for p in superpowers_paths)

    # ── Claude Code skill detection ───────────────────────────────────
    skills_dir = Path.home() / ".claude" / "skills"
    skill_names = [
        "cdd", "ralph-loop", "atlas-user-test", "expand-tasks",
        "phase-executor", "org-tree",
        # Atlas premium markers
        "atlas-loop", "atlas-cdd", "atlas-plan", "atlas-gamify",
        # Customisation (v4+)
        "customise-workflow",
    ]
    for skill_name in skill_names:
        skill_path = skills_dir / skill_name / "SKILL.md"
        capabilities[skill_name] = skill_path.is_file()

    # ── External AI tool detection (v4: tool-agnostic) ────────────────
    external_tools: dict[str, list] = {
        "cursor": [
            lambda: bool(shutil.which("cursor")),
            lambda: (Path.home() / ".cursor").is_dir(),
            lambda: (Path.home() / ".config" / "Cursor").is_dir(),
        ],
        "codex-cli": [
            lambda: bool(shutil.which("codex")),
            lambda: bool(shutil.which("openai-codex")),
        ],
        "gemini-cli": [
            lambda: bool(shutil.which("gemini")),
        ],
        "roo-code": [
            lambda: bool(shutil.which("roo")),
            lambda: bool(shutil.which("roocode")),
            lambda: (Path.home() / ".vscode" / "extensions").is_dir()
                    and any(
                        "roo" in p.name.lower()
                        for p in (Path.home() / ".vscode" / "extensions").glob("*")
                    ) if (Path.home() / ".vscode" / "extensions").is_dir() else False,
        ],
        "coderabbit": [
            lambda: bool(shutil.which("coderabbit")),
            lambda: bool(shutil.which("cr")),
        ],
        "aider": [
            lambda: bool(shutil.which("aider")),
        ],
        "continue": [
            lambda: (Path.home() / ".continue").is_dir(),
        ],
    }
    for tool_name, strategies in external_tools.items():
        capabilities[tool_name] = any(_safe_call(s) for s in strategies)

    # ── TaskMaster detection ──────────────────────────────────────────
    tm = detect_taskmaster()
    capabilities["taskmaster-mcp"] = tm["method"] == "mcp"
    capabilities["taskmaster-cli"] = tm["method"] in ("mcp", "cli")

    # ── Derive tier flags ─────────────────────────────────────────────
    has_atlas_skill_premium = (
        capabilities.get("atlas-loop", False)
        and capabilities.get("atlas-cdd", False)
    )
    has_atlas_launcher_premium = detect_atlas_launcher()["mcp_registered"]
    has_atlas_premium = has_atlas_skill_premium or has_atlas_launcher_premium
    has_free_ralph_stack = (
        capabilities.get("superpowers", False)
        and capabilities.get("ralph-loop", False)
    )
    has_external_ai_tools = any(
        capabilities.get(t, False)
        for t in ("cursor", "codex-cli", "gemini-cli", "roo-code", "aider", "continue")
    )

    # ── Mode recommendation ───────────────────────────────────────────
    if has_atlas_launcher_premium:
        recommended = "D"
        reason = ATLAS_FLEET_REASON
    elif has_atlas_skill_premium:
        recommended = "D"
        reason = "Atlas Loop (premium) — atlas-loop + atlas-cdd detected"
    elif has_free_ralph_stack:
        recommended = "C"
        reason = "Plan + Ralph Loop (recommended free) — superpowers + ralph-loop detected"
    elif capabilities.get("superpowers"):
        recommended = "A"
        reason = "Plan Only — superpowers detected, no execution loop"
    elif capabilities.get("taskmaster-cli"):
        recommended = "B"
        reason = "TaskMaster Auto-Execute — native CLI execution loop"
    else:
        recommended = "A"
        reason = "Plan Only — universal fallback"

    alternative_modes = []
    if capabilities.get("cursor"):
        alternative_modes.append({"mode": "E", "tool": "cursor", "description": "Cursor Composer handoff"})
    if capabilities.get("roo-code"):
        alternative_modes.append({"mode": "F", "tool": "roo-code", "description": "RooCode agent handoff"})
    if capabilities.get("codex-cli"):
        alternative_modes.append({"mode": "G", "tool": "codex-cli", "description": "Codex CLI auto-execute"})
    if capabilities.get("gemini-cli"):
        alternative_modes.append({"mode": "H", "tool": "gemini-cli", "description": "Gemini CLI orchestrator"})
    if capabilities.get("coderabbit"):
        alternative_modes.append({"mode": "I", "tool": "coderabbit", "description": "CodeRabbit PR review loop"})
    if capabilities.get("aider"):
        alternative_modes.append({"mode": "J", "tool": "aider", "description": "Aider pair-programming"})

    return {
        "ok": True,
        "tier": "premium" if has_atlas_premium else "free",
        "has_superpowers": capabilities.get("superpowers", False),
        "has_taskmaster": capabilities.get("taskmaster-cli", False),
        "has_atlas_premium": has_atlas_premium,
        "capabilities": capabilities,
        "has_external_ai_tools": has_external_ai_tools,
        "recommended_mode": recommended,
        "recommended_reason": reason,
        "alternative_modes": alternative_modes,
    }


def validate_setup(provider_mode: str | None = None) -> dict:
    """Run all Phase 0 SETUP checks and return per-check pass/fail + fix hints.

    `provider_mode` controls whether the task-master binary is a hard
    requirement ("plan_only") or advisory. When None, it defaults to the engine
    default ("hybrid") via `engine_config()` — which returns compiled-in
    defaults, NOT the persisted value in fleet.json. Callers that need the
    persisted mode must read it from `fleet.load_fleet_config()` and pass it
    explicitly.

    Returns EXACTLY 6 checks (spec §5):
      binary          — task-master CLI installed
      version         — task-master version >= TASKMASTER_MIN_VERSION
      project         — .taskmaster/ directory exists
      config          — .taskmaster/config.json present
      provider_main   — main model configured
      provider_research — research model configured (soft check)

    Returns:
      ok: True
      ready: bool
      critical_failures: int
      checks: list[dict]   — exactly 6 entries, each with id, passed, fix
    """
    if provider_mode is None:
        provider_mode = engine_config().get("provider_mode", "hybrid")
    # When the engine is NOT plan_only it no longer depends on the task-master
    # binary (sub-project #1 removes it), so its presence/version is advisory,
    # not a critical gate. plan_only keeps the binary as a hard requirement.
    taskmaster_advisory = provider_mode != "plan_only"

    checks = []

    # Check 1: task-master binary installed
    cli_path = (
        shutil.which("task-master")
        or shutil.which("task-master-ai")
        or shutil.which("taskmaster")
    )
    cli_version: str | None = None
    if cli_path:
        try:
            result = subprocess.run(
                [cli_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                cli_version = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    checks.append({
        "id": "binary",
        "name": "task-master CLI installed",
        "passed": bool(cli_path),
        "detail": (
            f"Found at {cli_path} (version {cli_version})" if cli_path
            else (
                "Not found in PATH (advisory: engine no longer requires it)"
                if taskmaster_advisory else "Not found in PATH"
            )
        ),
        "fix": (
            None if cli_path or taskmaster_advisory
            else "npm install -g task-master-ai"
        ),
        **({"severity": "advisory"} if taskmaster_advisory else {}),
    })

    # Check 2: version >= minimum
    version_info = _check_taskmaster_version(cli_path)
    checks.append({
        "id": "version",
        "name": f"task-master version >= {TASKMASTER_MIN_VERSION}",
        "passed": version_info["supported"],
        "detail": (
            f"detected {version_info['detected_version']} (min {TASKMASTER_MIN_VERSION})"
            if version_info.get("detected_version")
            else "version not detectable"
        ),
        "fix": (
            None if version_info["supported"] or taskmaster_advisory
            else "npm install -g task-master-ai@latest"
        ),
        "severity": "advisory" if taskmaster_advisory else "warning",
    })

    # Check 3: .taskmaster/ directory exists
    has_tm_dir = TASKMASTER_DIR.is_dir()
    checks.append({
        "id": "project",
        "name": ".taskmaster/ project initialized",
        "passed": has_tm_dir,
        "detail": f".taskmaster/ {'exists' if has_tm_dir else 'missing'}",
        "fix": "task-master init --yes" if not has_tm_dir else None,
    })

    # Check 4: config.json present
    config_file = TASKMASTER_DIR / "config.json"
    has_config = config_file.is_file()
    checks.append({
        "id": "config",
        "name": ".taskmaster/config.json present",
        "passed": has_config,
        "detail": (
            "config.json found" if has_config
            else "config.json missing — project may not be fully initialized"
        ),
        "fix": "task-master init --yes" if not has_config else None,
    })

    # Check 5: main model configured AND its provider is usable here.
    # A model-id string is not enough: a paid 'anthropic' main with no
    # ANTHROPIC_API_KEY (TaskMaster's stock default) is configured but cannot
    # run, and silently produces 0 tasks. The gate must verify reachability.
    usable_kwargs = {
        "has_claude": shutil.which("claude") is not None,
        "has_codex": shutil.which("codex") is not None,
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_perplexity_key": _has_perplexity_api_key(),
    }
    provider_ok = False
    provider_detail = "Cannot read config"
    main_model: str | None = None
    main_provider: str | None = None
    research_model: str | None = None
    research_provider: str | None = None
    main_usable = False
    nested_spawn_block = False
    if has_config:
        try:
            with open(config_file) as f:
                cfg = json.load(f)
            models = cfg.get("models", {})
            main = models.get("main", {}) or {}
            research = models.get("research", {}) or {}
            fallback = models.get("fallback", {}) or {}
            main_provider = main.get("provider")
            main_model = main.get("modelId")
            research_provider = research.get("provider")
            research_model = research.get("modelId")
            fallback_model = fallback.get("modelId")
            main_usable = _provider_usable(main_provider, **usable_kwargs)
            # #11/#12: a CLI-spawning provider may pass the credential check (CLI on
            # PATH) yet still be unable to spawn a child inside a nested Claude
            # session. PROBE it — don't assume either way.
            nested_spawn_block = False
            if main_usable and _is_spawning_provider(main_provider) and _is_nested_claude():
                if not _probe_spawn(main_provider):
                    main_usable = False
                    nested_spawn_block = True
            provider_ok = bool(main_model) and main_usable
            if nested_spawn_block:
                provider_detail = (
                    f"main={main_provider}/{main_model}: the '{main_provider}' CLI cannot spawn a "
                    "child inside this nested Claude Code session — parse/expand would die with "
                    "exit 1 and write no tasks"
                )
            elif bool(main_model) and not main_usable:
                provider_detail = (
                    f"main={main_provider or '?'}/{main_model} configured, but provider "
                    f"'{main_provider}' has no usable credential/CLI here — would produce 0 tasks"
                )
            else:
                provider_detail = (
                    f"main={main_provider or '?'}/{main_model or 'unset'}, "
                    f"research={research_provider or '?'}/{research_model or 'unset'}, "
                    f"fallback={fallback_model or 'unset'}"
                )
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            provider_detail = f"config.json unreadable: {exc}"

    checks.append({
        "id": "provider_main",
        "name": "Main model configured and reachable",
        "passed": provider_ok,
        "detail": provider_detail,
        "fix": (
            (
                (
                    "Run Atlas from a plain shell (outside Claude Code), OR set ANTHROPIC_API_KEY "
                    "to use the Anthropic API instead of the CLI spawn, OR run: "
                    "python3 script.py configure-providers"
                )
                if nested_spawn_block
                else (
                    "python3 script.py configure-providers"
                    "  # migrate the unusable provider to your installed claude/codex CLI (or set its API key)"
                    if (main_model and not main_usable)
                    else "task-master models --set-main sonnet --claude-code"
                )
            )
            if not provider_ok else None
        ),
    })

    # Check 6: research model configured AND reachable (soft — not blocking,
    # because expand degrades to a structural pass when research is unavailable).
    research_usable = bool(research_model) and _provider_usable(research_provider, **usable_kwargs)
    checks.append({
        "id": "provider_research",
        "name": "Research model configured and reachable (optional but recommended)",
        "passed": research_usable,
        "detail": (
            f"research={research_provider or '?'}/{research_model}"
            if research_usable
            else (
                f"research={research_provider or '?'}/{research_model or 'unset'} not reachable — "
                "expand will fall back to structural (no --research)"
            )
        ),
        "fix": (
            "python3 script.py configure-providers"
            "  # points research at the free local proxy or your claude/codex CLI"
            if not research_usable else None
        ),
        "severity": "warning",
    })

    # Aggregate — neither "warning" nor "advisory" failures are "critical"
    _non_critical = {"warning", "advisory"}
    critical_failures = [
        c for c in checks
        if not c["passed"] and c.get("severity") not in _non_critical
    ]
    all_passed = len(critical_failures) == 0

    return {
        "ok": True,
        "ready": all_passed,
        "critical_failures": len(critical_failures),
        "checks": checks,
        "cli_path": cli_path,
        "cli_version": cli_version,
        "next_action": (
            "Setup complete. Proceed to Phase 1 (DISCOVER)."
            if all_passed
            else f"{len(critical_failures)} critical check(s) failing. Run the 'fix' command from each failed check."
        ),
    }
