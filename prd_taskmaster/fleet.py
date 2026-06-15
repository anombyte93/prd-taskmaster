"""Atlas Fleet dependency scheduler and routing config.

The scheduler core operates on a plain list of task dicts. The run_* and
cmd_* wrappers resolve TaskMaster tags for CLI/MCP callers.
"""

import argparse
import json
from pathlib import Path

from prd_taskmaster.economy import TIER_ORDER, economy_profile, shift_tier
from prd_taskmaster import parallel
from prd_taskmaster.lib import CommandError, emit, fail

# ─── REQ-010: optional .atlas-ai/fleet.json routing config ───────────────────

FLEET_CONFIG_PATH = Path(".atlas-ai") / "fleet.json"

# Capability ladder (Hayden 2026-06-11): Fable #1 for the hardest/longest-
# running work, then codex top tier (experimental backends only), then down
# the cost-efficiency curve. Defaults stay all-Claude — codex/gemini need
# experimental_backends=true (handoff-file-only delivery).
DEFAULT_ROUTING = {
    "fast": "claude:haiku",        # trivial: scaffolding, docs, renames
    "standard": "claude:sonnet",   # normal build tasks
    "capable": "claude:opus",      # complex single tasks
    "frontier": "claude:fable",    # hardest + longest-running (1M context)
}

# Experimental ladder for fleet.json when experimental_backends=true:
#   "capable": "codex:gpt-5.5-codex"   (codex top tier — near-opus, slots below Fable)
#   "standard": "gemini:pro"           (solid mid tier, cost-efficient)
#   "fast": "gemini:flash"             (cost floor — effectively free)
#
# QUOTA-POOL DOCTRINE: claude/codex/gemini draw on three SEPARATE quota pools
# (Claude subscription, ChatGPT subscription, Google free tier). For large
# fleets the Claude rate limit is the throughput ceiling — spreading fast-tier
# tasks to gemini and part of standard to codex multiplies concurrent worker
# capacity, independent of per-task cost. Quality ladder picks the model for
# a task; quota spreading picks where bulk tiers run when fleet size > one
# pool's comfort.

DEFAULT_FLEET_CONFIG = {
    "max_concurrency": 3,
    "routing": DEFAULT_ROUTING,
    "experimental_backends": False,
    "token_economy": "balanced",
    "backend": "auto",
}

BACKEND_CHOICES = {"auto", "taskmaster", "native"}

# ─── Atlas hybrid provider: engine config block (Chunk 1) ─────────────────────
PROVIDER_MODE_CHOICES = {"hybrid", "api_only", "cli_only", "plan_only"}
STRUCTURED_JSON_CHOICES = {"auto", "schema", "prompt"}

DEFAULT_ENGINE_CONFIG = {
    "provider_mode": "hybrid",        # hybrid | api_only | cli_only | plan_only
    "keyless_default": None,          # null until wizard asks; True=CLI-first, False=key-first
    "cli_agent": {
        "structured_json": "auto",    # auto | schema | prompt
        "probe_cache_ttl_s": 900,
        "per_call_timeout_s": 180,
        "max_inflight": None,         # null -> inherit max_concurrency
    },
    "concurrency": {
        "structured_gen": None,       # null -> inherit max_concurrency
        "ram_aware": False,           # reserved for sub-project #2
    },
}


ATLAS_CONFIG_PATH = Path(".atlas-ai") / "config" / "atlas.json"


def _atlas_config_economy() -> str | None:
    """token_economy set via /customise-workflow (.atlas-ai/config/atlas.json).

    /customise-workflow is the discoverable customization tool; the economy a user
    sets there must take effect even though the lower-level routing file is fleet.json.
    """
    if not ATLAS_CONFIG_PATH.is_file():
        return None
    try:
        raw = json.loads(ATLAS_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    val = raw.get("token_economy")
    return val if isinstance(val, str) else None


def _is_pos_int(value):
    """True for a real positive int, excluding bool (bool subclasses int)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def engine_config(cfg=None):
    """Merged `engine` block with all defaults applied (Chunk 1).

    Accepts a raw fleet.json dict OR the output of `load_fleet_config` (both
    carry an `engine` key after this change). Returns a fresh dict every call.
    Malformed values fall back silently, exactly like `load_fleet_config`.
    """
    eng = {
        "provider_mode": DEFAULT_ENGINE_CONFIG["provider_mode"],
        "keyless_default": DEFAULT_ENGINE_CONFIG["keyless_default"],
        "cli_agent": dict(DEFAULT_ENGINE_CONFIG["cli_agent"]),
        "concurrency": dict(DEFAULT_ENGINE_CONFIG["concurrency"]),
    }
    if not isinstance(cfg, dict):
        return eng
    raw = cfg.get("engine")
    if not isinstance(raw, dict):
        return eng

    mode = raw.get("provider_mode")
    if mode in PROVIDER_MODE_CHOICES:
        eng["provider_mode"] = mode

    keyless = raw.get("keyless_default")
    # Only an explicit bool is persisted; None means "wizard hasn't asked".
    if isinstance(keyless, bool):
        eng["keyless_default"] = keyless

    cli = raw.get("cli_agent")
    if isinstance(cli, dict):
        sj = cli.get("structured_json")
        if sj in STRUCTURED_JSON_CHOICES:
            eng["cli_agent"]["structured_json"] = sj
        ttl = cli.get("probe_cache_ttl_s")
        if _is_pos_int(ttl):
            eng["cli_agent"]["probe_cache_ttl_s"] = ttl
        timeout = cli.get("per_call_timeout_s")
        if _is_pos_int(timeout):
            eng["cli_agent"]["per_call_timeout_s"] = timeout
        inflight = cli.get("max_inflight")
        if _is_pos_int(inflight):
            eng["cli_agent"]["max_inflight"] = inflight

    conc = raw.get("concurrency")
    if isinstance(conc, dict):
        sg = conc.get("structured_gen")
        if _is_pos_int(sg):
            eng["concurrency"]["structured_gen"] = sg
        if isinstance(conc.get("ram_aware"), bool):
            eng["concurrency"]["ram_aware"] = conc["ram_aware"]

    return eng


def save_engine_config(updates):
    """Deep-merge `updates` into the `engine` block of .atlas-ai/fleet.json,
    write atomically, and return the new merged engine block (Chunk 5 contract).

    Only the `engine` sub-tree is touched; every other top-level key in the file
    is preserved. A missing/unreadable/non-dict file is treated as empty. One
    level of nested-dict merge (matching the engine block's shape) is applied so
    a partial `{"cli_agent": {...}}` update does not clobber sibling cli_agent
    keys.

    The RETURNED block is normalized via `engine_config` (defaults + validation)
    so callers see exactly what a fresh load would return. The value written to
    the file is the raw merged dict as supplied by the caller; it is not
    pre-validated — callers are expected to pass already-valid values, and
    `engine_config` corrects any malformed entries on the next read.
    """
    path = FLEET_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc = json.loads(path.read_text()) if path.is_file() else {}
    except (json.JSONDecodeError, OSError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    engine = doc.get("engine")
    if not isinstance(engine, dict):
        engine = {}
    if isinstance(updates, dict):
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(engine.get(k), dict):
                engine[k].update(v)
            else:
                engine[k] = v
    doc["engine"] = engine
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    tmp.replace(path)
    return engine_config(doc)


def load_fleet_config(path=None):
    """Load .atlas-ai/fleet.json merged over defaults.

    Malformed files and invalid values fall back to defaults silently —
    a broken optional config must never block a fleet run.

    Economy precedence: fleet.json (explicit) > atlas.json (/customise-workflow) > default.
    """
    cfg = {
        "max_concurrency": DEFAULT_FLEET_CONFIG["max_concurrency"],
        "routing": dict(DEFAULT_ROUTING),
        "experimental_backends": DEFAULT_FLEET_CONFIG["experimental_backends"],
        "token_economy": _atlas_config_economy() or DEFAULT_FLEET_CONFIG["token_economy"],
        "backend": DEFAULT_FLEET_CONFIG["backend"],
        "engine": engine_config(None),
    }
    p = Path(path) if path else FLEET_CONFIG_PATH
    if not p.is_file():
        return cfg
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return cfg
    if not isinstance(raw, dict):
        return cfg

    mc = raw.get("max_concurrency")
    if isinstance(mc, int) and mc >= 1:
        cfg["max_concurrency"] = mc

    routing = raw.get("routing")
    if isinstance(routing, dict):
        for tier, target in routing.items():
            if isinstance(tier, str) and isinstance(target, str) and ":" in target:
                cfg["routing"][tier] = target

    if isinstance(raw.get("experimental_backends"), bool):
        cfg["experimental_backends"] = raw["experimental_backends"]

    if isinstance(raw.get("token_economy"), str):
        cfg["token_economy"] = raw["token_economy"]

    backend = raw.get("backend")
    if backend in BACKEND_CHOICES:
        cfg["backend"] = backend

    escalation = raw.get("escalation")
    if isinstance(escalation, dict):
        resolved = {}
        if isinstance(escalation.get("enabled"), bool):
            resolved["enabled"] = escalation["enabled"]
        max_steps = escalation.get("max_steps")
        if isinstance(max_steps, int) and max_steps >= 0:
            resolved["max_steps"] = max_steps
        ceiling = escalation.get("ceiling")
        if ceiling in TIER_ORDER:
            resolved["ceiling"] = ceiling
        if resolved:
            resolved.setdefault("enabled", True)
            cfg["escalation"] = resolved

    cfg["engine"] = engine_config(raw)

    return cfg


# Complexity -> tier mapping (matches execute-task: 1-4 fast / 5-7 standard /
# 8-10 capable; enrich-tasks classes map the same way).
_SCORE_TIERS = ((4, "fast"), (7, "standard"), (8, "capable"), (10, "frontier"))
_CLASS_TIERS = {
    "SIMPLE": "fast",
    "MEDIUM": "standard",
    "COMPLEX": "capable",
    "RESEARCH": "frontier",   # long-running, context-heavy
    "VALIDATION": "standard",
}


def available_backends():
    """Which agent CLIs are actually installed on this machine."""
    import shutil

    return {
        "claude": shutil.which("claude") is not None,
        "codex": shutil.which("codex") is not None,
        "gemini": shutil.which("gemini") is not None,
    }


def task_tier(task):
    """Resolve a task's complexity tier from its score or enrich-tasks class."""
    score = task.get("complexityScore")
    if isinstance(score, (int, float)):
        for ceiling, tier in _SCORE_TIERS:
            if score <= ceiling:
                return tier
        return "frontier"
    cls = str((task.get("phaseConfig") or {}).get("complexity", "")).upper()
    return _CLASS_TIERS.get(cls, "standard")


def _code_impl_shift_bounds(profile):
    mode = profile.get("mode")
    if mode == "conservative":
        return "fast", "capable"
    if mode == "performance":
        return "standard", None
    return None, None


def route_task(task, config, backends=None, attempt=0):
    """Pick the backend:model for ONE task: complexity tier -> routing ->
    availability check. Routed backend not installed -> claude default for
    the tier (claude is the only backend with full spawn support anyway)."""
    if backends is None:
        backends = available_backends()
    profile = economy_profile(config)
    tier = task_tier(task)
    floor, ceiling = _code_impl_shift_bounds(profile)
    tier = shift_tier(tier, profile.get("code_impl_shift", 0), floor=floor, ceiling=ceiling)
    escalation = profile.get("escalation", {})
    if attempt > 0 and escalation.get("enabled", True):
        steps = min(attempt, escalation.get("max_steps", attempt))
        tier = shift_tier(tier, steps, ceiling=escalation.get("ceiling"))
    target = resolve_backend(tier, config)
    backend = target.split(":", 1)[0]
    if not backends.get(backend, False):
        default = DEFAULT_ROUTING.get(tier, DEFAULT_ROUTING["standard"])
        target = default if backends.get("claude", True) else target
    return target


def resolve_backend(tier, config):
    """Resolve a complexity tier to a backend:model string.

    With experimental_backends false, every tier is forced to Claude
    (only Claude has the full session_spawn prompt-injection path).
    Unknown tiers resolve to the standard tier.
    """
    routing = config.get("routing") or {}
    target = routing.get(tier) or routing.get("standard") or DEFAULT_ROUTING["standard"]
    if not config.get("experimental_backends", False):
        if not target.startswith("claude:"):
            default = DEFAULT_ROUTING.get(tier, DEFAULT_ROUTING["standard"])
            target = default if default.startswith("claude:") else DEFAULT_ROUTING["standard"]
    return target


def _task_id(task):
    return task.get("id")


def _status(task):
    return str(task.get("status", "pending"))


def _is_done(task):
    return _status(task) == "done"


def _is_pending(task):
    return _status(task) == "pending"


def _dependencies(task):
    return task.get("dependencies") or []


def _chunk(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def _load_tagged_or_raise(tag):
    if not parallel.TASKS.is_file():
        raise CommandError(f"{parallel.TASKS} not found")
    try:
        raw = json.loads(parallel.TASKS.read_text())
    except json.JSONDecodeError as exc:
        raise CommandError(f"Failed to parse {parallel.TASKS}: {exc}") from exc

    if tag not in raw or not isinstance(raw.get(tag), dict):
        if "tasks" in raw and isinstance(raw["tasks"], list):
            return raw, None
        raise CommandError(f"tag '{tag}' not found in {parallel.TASKS}")
    return raw, tag


def ready_set(tasks):
    """Return pending task IDs whose dependencies are all done."""
    done_ids = {_task_id(task) for task in tasks if _is_done(task)}
    return [
        _task_id(task)
        for task in tasks
        if _is_pending(task)
        and all(dep_id in done_ids for dep_id in _dependencies(task))
    ]


def compute_waves(tasks, max_concurrency=3):
    """Return dependency-ordered execution waves for pending tasks."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")

    completed = {_task_id(task) for task in tasks if _is_done(task)}
    remaining = [task for task in tasks if _is_pending(task)]
    waves = []

    while remaining:
        frontier = [
            task
            for task in remaining
            if all(dep_id in completed for dep_id in _dependencies(task))
        ]
        if not frontier:
            return {
                "waves": waves,
                "blocked": [_task_id(task) for task in remaining],
                "deadlocked": True,
            }

        frontier_ids = [_task_id(task) for task in frontier]
        waves.extend(_chunk(frontier_ids, max_concurrency))
        completed.update(frontier_ids)

        frontier_objects = {id(task) for task in frontier}
        remaining = [
            task for task in remaining
            if id(task) not in frontier_objects
        ]

    return {
        "waves": waves,
        "blocked": [],
        "deadlocked": False,
    }


def run_fleet_waves(concurrency=3, tag=""):
    """Resolve TaskMaster tasks and return fleet wave scheduling JSON."""
    if concurrency < 1:
        raise CommandError("concurrency must be >= 1")

    resolved_tag = parallel.current_tag(argparse.Namespace(tag=tag or None))
    raw, tag_key = _load_tagged_or_raise(resolved_tag)
    try:
        tasks = parallel.get_tasks(raw, tag_key)
    except (KeyError, TypeError) as exc:
        raise CommandError(
            f"tasks missing for tag '{resolved_tag}' in {parallel.TASKS}"
        ) from exc

    waves = compute_waves(tasks, concurrency)
    # Smart per-task model routing: complexity tier -> fleet.json routing ->
    # installed-backend check. Dispatchers pass routing[task_id] as model=.
    cfg = load_fleet_config()
    profile = economy_profile(cfg)
    backends = available_backends()
    routing = {
        str(_task_id(t)): route_task(t, cfg, backends)
        for t in tasks
        if _is_pending(t)
    }
    return {
        "ok": True,
        "tag": resolved_tag,
        "waves": waves["waves"],
        "blocked": waves["blocked"],
        "deadlocked": waves["deadlocked"],
        "ready": ready_set(tasks),
        "concurrency": concurrency,
        "routing": routing,
        "backends": backends,
        "economy": profile["mode"],
        "escalation": profile["escalation"],
    }


def cmd_fleet_waves(args):
    """CLI wrapper for fleet-waves."""
    try:
        emit(run_fleet_waves(args.concurrency, getattr(args, "tag", "")))
    except CommandError as exc:
        fail(exc.message, **exc.extra)
