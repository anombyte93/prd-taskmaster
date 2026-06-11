"""Token economy preset and tier-shift contracts."""

from prd_taskmaster.economy import economy_profile, shift_tier


def test_economy_profile_defaults_to_balanced():
    profile = economy_profile({})

    assert profile["mode"] == "balanced"
    assert profile["structured_gen_start"] == "standard"
    assert profile["research_choice"] == "real_api_if_key"
    assert profile["code_impl_shift"] == 0
    assert profile["verification_start"] == "standard"
    assert profile["escalation"] == {
        "enabled": True,
        "max_steps": 2,
        "ceiling": "frontier",
    }
    assert profile["tm_concurrency"] == "max"


def test_unknown_economy_profile_resolves_to_balanced():
    profile = economy_profile({"token_economy": "turbo"})

    assert profile["mode"] == "balanced"
    assert profile["research_choice"] == "real_api_if_key"
    assert profile["escalation"]["ceiling"] == "frontier"


def test_explicit_escalation_overrides_preset_keys():
    profile = economy_profile({
        "token_economy": "conservative",
        "escalation": {"max_steps": 3, "ceiling": "frontier", "enabled": False},
    })

    assert profile["mode"] == "conservative"
    assert profile["code_impl_shift"] == -1
    assert profile["escalation"] == {
        "enabled": False,
        "max_steps": 3,
        "ceiling": "frontier",
    }


def test_shift_tier_clamps_to_order_floor_and_ceiling():
    assert shift_tier("fast", -2) == "fast"
    assert shift_tier("standard", 2) == "frontier"
    assert shift_tier("frontier", 1) == "frontier"
    assert shift_tier("fast", -1, floor="standard") == "standard"
    assert shift_tier("frontier", 1, ceiling="capable") == "capable"
