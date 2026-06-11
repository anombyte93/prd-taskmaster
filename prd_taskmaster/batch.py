"""Batched Phase-1 entry point.

Dogfood finding (2026-06-11): the skill UX shelled out to script.py four
times for Phase 1 (preflight, detect-taskmaster, configure-providers,
detect-providers) spraying raw JSON each time. One call should cover the
whole phase and return a human-presentable summary.
"""

from prd_taskmaster.capabilities import run_detect_capabilities
from prd_taskmaster.lib import CommandError, emit, fail
from prd_taskmaster.preflight import run_detect_taskmaster, run_preflight
from prd_taskmaster.providers import run_configure_providers, run_detect_providers


def run_engine_preflight(configure: bool = True) -> dict:
    """Run every Phase-1 probe in one call.

    Read-only on a bare directory: provider configuration is attempted only
    when a TaskMaster project already exists (configure_providers refuses
    otherwise, and we swallow that refusal into the summary rather than
    failing the batch).
    """
    preflight = run_preflight()
    taskmaster = run_detect_taskmaster()

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
