"""Token economy presets, telemetry, and tier helpers for Atlas Fleet routing."""

import json
import threading
from pathlib import Path

TIER_ORDER = ["fast", "standard", "capable", "frontier"]

# These vendor IDs rot. Refresh this map when telemetry or MODEL-ECONOMY.md
# shows the model ladder has changed.
TIER_MODEL_IDS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
}

TELEMETRY = Path(".atlas-ai") / "telemetry.jsonl"
_TELEMETRY_LOCK = threading.Lock()

ECONOMY_PRESETS = {
    "conservative": {
        "structured_gen_start": "fast",
        "research_choice": "free_proxy_first",
        "code_impl_shift": -1,
        "verification_start": "fast",
        "escalation": {"max_steps": 1, "ceiling": "capable"},
        "tm_concurrency": "min2",
    },
    "balanced": {
        "structured_gen_start": "standard",
        "research_choice": "real_api_if_key",
        "code_impl_shift": 0,
        "verification_start": "standard",
        "escalation": {"max_steps": 2, "ceiling": "frontier"},
        "tm_concurrency": "max",
    },
    "performance": {
        "structured_gen_start": "standard",
        "research_choice": "best_available",
        "code_impl_shift": 1,
        "verification_start": "standard",
        "escalation": {"max_steps": 2, "ceiling": "frontier", "eager": True},
        "tm_concurrency": "max",
    },
}


def shift_tier(tier, steps, floor=None, ceiling=None):
    """Shift a tier along TIER_ORDER, clamped to optional floor and ceiling."""
    base = tier if tier in TIER_ORDER else "standard"
    index = TIER_ORDER.index(base) + steps
    low = TIER_ORDER.index(floor) if floor in TIER_ORDER else 0
    high = TIER_ORDER.index(ceiling) if ceiling in TIER_ORDER else len(TIER_ORDER) - 1
    index = max(0, min(len(TIER_ORDER) - 1, index))
    index = max(low, min(high, index))
    return TIER_ORDER[index]


def economy_profile(cfg):
    """Resolve token economy config into one concrete profile dict."""
    requested = cfg.get("token_economy", "balanced") if isinstance(cfg, dict) else "balanced"
    mode = requested if requested in ECONOMY_PRESETS else "balanced"
    preset = ECONOMY_PRESETS[mode]
    profile = {
        key: (dict(value) if isinstance(value, dict) else value)
        for key, value in preset.items()
    }
    profile["mode"] = mode

    escalation = dict(profile["escalation"])
    escalation.setdefault("enabled", True)
    user_escalation = cfg.get("escalation") if isinstance(cfg, dict) else None
    if isinstance(user_escalation, dict):
        escalation.update(user_escalation)
    profile["escalation"] = escalation
    return profile


# ─── Telemetry append helper ─────────────────────────────────────────────────

def append_telemetry(row, path=None):
    """Append one telemetry row to JSONL using the shared in-process lock."""
    p = Path(path) if path else TELEMETRY
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, default=str) + "\n"
    with _TELEMETRY_LOCK:
        with p.open("a") as f:
            f.write(line)


# ─── T7: telemetry summary (economy-report) ──────────────────────────────────

def summarize_telemetry(path=None):
    """Summarize .atlas-ai/telemetry.jsonl per (op_class, model).

    The local-measurement loop from MODEL-ECONOMY.md: success rate and p50
    wall-time per model per op class, plus escalation count. Malformed lines
    are skipped and counted, never fatal.
    """
    import json
    from pathlib import Path as _P

    p = _P(path) if path else _P(".atlas-ai") / "telemetry.jsonl"
    rows, skipped = [], 0
    if p.is_file():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1

    groups = {}
    escalations = 0
    for r in rows:
        key = (str(r.get("op_class", "unknown")), str(r.get("model", "unknown")))
        g = groups.setdefault(key, {"calls": 0, "successes": 0, "walls": []})
        g["calls"] += 1
        if r.get("exit") == 0:
            g["successes"] += 1
        if isinstance(r.get("wall_ms"), (int, float)):
            g["walls"].append(r["wall_ms"])
        if r.get("escalated"):
            escalations += 1

    out = []
    for (op_class, model), g in sorted(groups.items()):
        walls = sorted(g["walls"])
        p50 = walls[len(walls) // 2] if walls else None
        out.append({
            "op_class": op_class,
            "model": model,
            "calls": g["calls"],
            "success_rate": (g["successes"] / g["calls"]) if g["calls"] else None,
            "p50_wall_ms": p50,
        })

    return {
        "ok": True,
        "total_calls": len(rows),
        "skipped_lines": skipped,
        "escalations": escalations,
        "groups": out,
        "telemetry_path": str(p),
    }


def cmd_economy_report(args):
    from prd_taskmaster.lib import emit

    emit(summarize_telemetry(getattr(args, "input", None)))
