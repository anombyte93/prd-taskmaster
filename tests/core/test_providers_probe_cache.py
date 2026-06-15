# tests/core/test_providers_probe_cache.py
"""Per-process spawn-probe cache: _probe_spawn at most once per provider per TTL,
invalidated on the first False result. No real subprocess is ever spawned --
_probe_spawn itself is monkeypatched and time.monotonic is driven by the test."""

import prd_taskmaster.providers as providers


def _reset_cache():
    providers._PROBE_CACHE.clear()


def test_cached_hit_calls_probe_once_within_ttl(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_probe(provider):
        calls["n"] += 1
        return True

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is True
    clock["t"] = 1500.0  # 500s later, still inside the 900s TTL
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 1  # second call served from cache


def test_reprobes_after_ttl_expires(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_probe(provider):
        calls["n"] += 1
        return True

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is True
    clock["t"] = 1000.0 + 901.0  # just past TTL
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 2  # TTL expired -> re-probed


def test_false_result_is_not_cached(monkeypatch):
    _reset_cache()
    calls = {"n": 0}
    results = iter([False, True])  # first probe refuses, second succeeds

    def fake_probe(provider):
        calls["n"] += 1
        return next(results)

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is False
    # Same instant, well inside TTL -- a cached False would skip the probe.
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 2  # the False was never cached


def test_distinct_providers_are_cached_independently(monkeypatch):
    _reset_cache()
    seen = []

    def fake_probe(provider):
        seen.append(provider)
        return True

    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: 1000.0)

    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert providers._probe_spawn_cached("codex-cli", 900) is True
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert seen == ["claude-code", "codex-cli"]  # claude-code second call cached
