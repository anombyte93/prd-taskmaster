"""Token economy presets and tier helpers for Atlas Fleet routing."""

TIER_ORDER = ["fast", "standard", "capable", "frontier"]

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
