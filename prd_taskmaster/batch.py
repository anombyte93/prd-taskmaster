"""Batched Phase-1 entry point.

Dogfood finding (2026-06-11): the skill UX shelled out to script.py four
times for Phase 1 (preflight, detect-taskmaster, configure-providers,
detect-providers) spraying raw JSON each time. One call should cover the
whole phase and return a human-presentable summary.
"""

import json

from prd_taskmaster import fleet
from prd_taskmaster.backend import NativeBackend, get_backend
from prd_taskmaster.capabilities import run_detect_capabilities
from prd_taskmaster.lib import CommandError, _detect_taskmaster_method, emit, fail
from prd_taskmaster.preflight import run_detect_taskmaster, run_preflight
from prd_taskmaster.providers import run_configure_providers, run_detect_providers


def _backend_source() -> str:
    path = fleet.FLEET_CONFIG_PATH
    if not path.is_file():
        return "auto"
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return "auto"
    if isinstance(raw, dict) and raw.get("backend") in ("taskmaster", "native"):
        return "config"
    return "auto"


def _backend_ai_ops(native_detect: dict) -> str:
    if native_detect.get("ai_ops") == "api":
        return "native-api"
    return "agent"


def _backend_block() -> dict:
    selected = get_backend(fleet.load_fleet_config()).name
    # The task-master backend was removed (spec §9.4): native is the sole
    # generator. The `taskmaster` entry is now an informational file-format/binary
    # presence probe (via the surviving _detect_taskmaster_method), never a
    # selectable backend — so engine-preflight stays honest about the optional
    # binary without depending on the deleted TaskMasterBackend class.
    tm_detected = _detect_taskmaster_method()
    tm_available = tm_detected.get("method") in ("cli", "mcp")
    native_detect = NativeBackend().detect()
    return {
        "selected": selected,
        "source": _backend_source(),
        "taskmaster": {
            "available": tm_available,
            "version": tm_detected.get("version"),
            "min_ok": tm_available,
        },
        "native": {
            "api_provider": native_detect.get("api_provider"),
            "agent_fallback": True,
        },
        "ai_ops": _backend_ai_ops(native_detect),
    }


def _backend_summary(block: dict) -> str:
    provider = block.get("native", {}).get("api_provider")
    if provider:
        return f"Backend: native (api: {provider})"
    return "Backend: native (agent-driven)"


def run_engine_preflight(configure: bool = True) -> dict:
    """Run every Phase-1 probe in one call.

    Read-only on a bare directory: provider configuration is attempted only
    when a TaskMaster project already exists (configure_providers refuses
    otherwise, and we swallow that refusal into the summary rather than
    failing the batch).
    """
    preflight = run_preflight()
    taskmaster = run_detect_taskmaster()
    backend = _backend_block()

    providers_configured = None
    if configure and preflight.get("has_taskmaster"):
        try:
            providers_configured = run_configure_providers()
        except CommandError as e:
            providers_configured = {"ok": False, "error": e.message, **e.extra}

    providers = run_detect_providers()
    capabilities = run_detect_capabilities()

    summary = []
    tm_state = taskmaster.get("method", "none")
    summary.append(
        f"TaskMaster: {tm_state}"
        + (f" v{taskmaster['version']}" if taskmaster.get("version") else "")
    )
    summary.append(_backend_summary(backend))
    prov = providers.get("providers", {})
    main = prov.get("main", {})
    research = prov.get("research", {})
    summary.append(f"Provider: {main.get('provider', 'none')} ({main.get('source', '-')})")
    summary.append(f"Research: {research.get('provider', 'none')}")
    summary.append(
        f"Tier: {capabilities.get('tier', 'free')} — {capabilities.get('recommended_reason', '')}"
    )
    if preflight.get("has_taskmaster"):
        summary.append(
            f"Project: {preflight.get('task_count', 0)} tasks"
            f" ({preflight.get('tasks_pending', 0)} pending)"
        )
    else:
        summary.append("Project: fresh (no .taskmaster yet)")

    return {
        "ok": True,
        "preflight": preflight,
        "taskmaster": taskmaster,
        "backend": backend,
        "providers": providers,
        "providers_configured": providers_configured,
        "capabilities": capabilities,
        "summary": summary,
    }


def cmd_engine_preflight(args) -> None:
    try:
        emit(run_engine_preflight(configure=not getattr(args, "no_configure", False)))
    except CommandError as e:
        fail(e.message, **e.extra)
