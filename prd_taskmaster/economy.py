"""Token economy presets, telemetry, and tier helpers for Atlas Fleet routing."""

import json
from pathlib import Path

from prd_taskmaster.lib import locked_update

TIER_ORDER = ["fast", "standard", "capable", "frontier"]

# These vendor IDs rot. Refresh this map when telemetry or MODEL-ECONOMY.md
# shows the model ladder has changed.
TIER_MODEL_IDS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
}

# These price priors rot. Refresh them from docs/product/MODEL-ECONOMY.md
# section 1 before making cost-saving claims.
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
}

NAIVE_BASELINE_MODEL = "claude-fable-5"

TELEMETRY = Path(".atlas-ai") / "telemetry.jsonl"

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
    """Append one telemetry row to JSONL and return its stable row reference."""
    p = Path(path) if path else TELEMETRY
    line = json.dumps(row, default=str) + "\n"
    ref = {}

    def transform(current: str) -> str:
        separator = "" if not current or current.endswith("\n") else "\n"
        row_line = len(current.splitlines()) + 1
        ref.update({
            "path": str(p.resolve()),
            "line": row_line,
            "ts": row.get("ts"),
            "op_class": row.get("op_class"),
            "model": row.get("model"),
            "backend": row.get("backend"),
            "exit": row.get("exit"),
        })
        return current + separator + line

    locked_update(p, transform)
    return ref


def _token_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _price_key_for_model(model):
    if not isinstance(model, str):
        return None
    if model in PRICES_PER_MTOK:
        return model
    for price_key in PRICES_PER_MTOK:
        if model.startswith(price_key + "-"):
            return price_key
    return None


def _estimate_cost_usd(tokens_in, tokens_out, rates):
    input_per_mtok, output_per_mtok = rates
    return ((tokens_in * input_per_mtok) + (tokens_out * output_per_mtok)) / 1_000_000


def _summarize_costs(rows):
    est_cost = 0.0
    naive_cost = 0.0
    priced_calls = 0
    unpriced_calls = 0
    token_calls = 0
    baseline_rates = PRICES_PER_MTOK[NAIVE_BASELINE_MODEL]

    for row in rows:
        tokens_in = _token_int(row.get("tokens_in"))
        tokens_out = _token_int(row.get("tokens_out"))
        if tokens_in is not None and tokens_out is not None:
            token_calls += 1
        price_key = _price_key_for_model(row.get("model"))
        if tokens_in is None or tokens_out is None or price_key is None:
            unpriced_calls += 1
            continue

        priced_calls += 1
        est_cost += _estimate_cost_usd(tokens_in, tokens_out, PRICES_PER_MTOK[price_key])
        naive_cost += _estimate_cost_usd(tokens_in, tokens_out, baseline_rates)

    total = priced_calls + unpriced_calls
    return {
        "naive_baseline_model": NAIVE_BASELINE_MODEL,
        "est_cost_usd": est_cost,
        "naive_cost_usd": naive_cost,
        "est_saved_usd": naive_cost - est_cost,
        "priced_calls": priced_calls,
        "unpriced_calls": unpriced_calls,
        # token_coverage = calls carrying token counts; priced_coverage = calls
        # whose model also matched a known price (the $ figures cover only those).
        "token_coverage": (token_calls / total) if total else 0.0,
        "priced_coverage": (priced_calls / total) if total else 0.0,
    }


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
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    skipped += 1
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
        "costs": _summarize_costs(rows),
        "telemetry_path": str(p),
    }


def cmd_economy_report(args):
    from prd_taskmaster.lib import emit

    emit(summarize_telemetry(getattr(args, "input", None)))
