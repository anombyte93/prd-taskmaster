"""Smart per-task model routing (Hayden directive 2026-06-11): dispatch must
know which backends exist and pick a model per task from its complexity."""

import json

from prd_taskmaster.fleet import available_backends, route_task


def test_available_backends_detects_installed_clis(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: "/bin/x" if c == "claude" else None)
    b = available_backends()
    assert b["claude"] is True
    assert b["codex"] is False
    assert b["gemini"] is False


def test_route_task_uses_complexity_score():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False}
    avail = {"claude": True, "codex": True, "gemini": False}
    assert route_task({"id": 1, "complexityScore": 2}, cfg, avail) == "claude:haiku"
    assert route_task({"id": 2, "complexityScore": 6}, cfg, avail) == "claude:sonnet"
    assert route_task({"id": 3, "complexityScore": 8}, cfg, avail) == "claude:opus"
    assert route_task({"id": 4, "complexityScore": 9}, cfg, avail) == "claude:fable"


def test_route_task_uses_phase_config_class_when_no_score():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False}
    avail = {"claude": True, "codex": False, "gemini": False}
    t = lambda c: {"id": 1, "phaseConfig": {"complexity": c}}
    assert route_task(t("SIMPLE"), cfg, avail) == "claude:haiku"
    assert route_task(t("MEDIUM"), cfg, avail) == "claude:sonnet"
    assert route_task(t("COMPLEX"), cfg, avail) == "claude:opus"
    assert route_task(t("RESEARCH"), cfg, avail) == "claude:fable"   # hardest/longest -> Fable #1


def test_route_task_falls_back_when_backend_not_installed():
    cfg = {"routing": {"fast": "codex:gpt-5.2-codex"}, "experimental_backends": True}
    avail = {"claude": True, "codex": False, "gemini": False}
    # codex routed but not installed -> claude default for the tier
    assert route_task({"id": 1, "complexityScore": 2}, cfg, avail).startswith("claude:")


def test_route_task_unknown_complexity_defaults_standard():
    cfg = {"routing": {"standard": "claude:sonnet"}, "experimental_backends": False}
    avail = {"claude": True, "codex": False, "gemini": False}
    assert route_task({"id": 1}, cfg, avail) == "claude:sonnet"


def test_route_task_escalates_attempts_with_balanced_ceiling():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False, "token_economy": "balanced"}
    avail = {"claude": True, "codex": False, "gemini": False}
    task = {"id": 1, "complexityScore": 2}

    assert route_task(task, cfg, avail, attempt=1) == "claude:sonnet"
    assert route_task(task, cfg, avail, attempt=2) == "claude:opus"
    assert route_task(task, cfg, avail, attempt=5) == "claude:opus"


def test_route_task_escalation_clamps_to_explicit_ceiling():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False, "token_economy": "balanced",
           "escalation": {"max_steps": 5, "ceiling": "capable"}}
    avail = {"claude": True, "codex": False, "gemini": False}

    assert route_task({"id": 1, "complexityScore": 2}, cfg, avail, attempt=5) == "claude:opus"


def test_conservative_code_impl_shift_lowers_medium_task_to_fast():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False, "token_economy": "conservative"}
    avail = {"claude": True, "codex": False, "gemini": False}
    task = {"id": 1, "phaseConfig": {"complexity": "MEDIUM"}}

    assert route_task(task, cfg, avail) == "claude:haiku"


def test_performance_code_impl_shift_floors_simple_task_at_standard():
    cfg = {"routing": {"fast": "claude:haiku", "standard": "claude:sonnet",
                       "capable": "claude:opus", "frontier": "claude:fable"},
           "experimental_backends": False, "token_economy": "performance"}
    avail = {"claude": True, "codex": False, "gemini": False}
    task = {"id": 1, "phaseConfig": {"complexity": "SIMPLE"}}

    assert route_task(task, cfg, avail) == "claude:sonnet"
