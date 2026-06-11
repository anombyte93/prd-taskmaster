"""Batched engine_preflight (dogfood finding 2026-06-11: skill UX shells out
to script.py repeatedly — one MCP call should cover the whole Phase 1)."""

import json

from prd_taskmaster.batch import run_engine_preflight


def test_engine_preflight_batches_all_phase1_signals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = run_engine_preflight()
    assert r["ok"] is True
    # one call returns every Phase-1 signal
    for key in ("preflight", "taskmaster", "providers", "capabilities", "summary"):
        assert key in r, f"missing {key}"
    assert isinstance(r["summary"], list) and r["summary"], "human-readable summary lines"
    assert r["preflight"]["has_taskmaster"] is False  # fresh dir


def test_engine_preflight_never_mutates_without_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_engine_preflight()
    # no .taskmaster, no .env, nothing created in a bare dir (read-only probe)
    assert list(tmp_path.iterdir()) == []
