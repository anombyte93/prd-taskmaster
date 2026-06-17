"""Backend abstraction tests. The task-master backend was removed (spec §9.4);
NativeBackend is the sole generator. These tests cover the factory + the
fleet.json backend-key validation that survive the deletion."""

import json
import warnings


def test_backend_factory_precedence_and_auto_detection(tmp_path, monkeypatch):
    """get_backend always returns NativeBackend. 'native' and 'auto' resolve to
    it directly; a legacy 'taskmaster' config falls back to native with a
    DeprecationWarning (the class itself is gone)."""
    from prd_taskmaster.backend import NativeBackend, get_backend

    monkeypatch.chdir(tmp_path)

    # legacy backend="taskmaster" no longer constructs a removed class — it
    # resolves to native with a deprecation warning.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy = get_backend({"backend": "taskmaster"})
    assert isinstance(legacy, NativeBackend)
    assert legacy.name == "native"
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    native = get_backend({"backend": "native"})
    assert isinstance(native, NativeBackend)
    assert native.name == "native"

    auto = get_backend({"backend": "auto"})
    assert isinstance(auto, NativeBackend)


def test_load_fleet_config_backend_key_validates_silently(tmp_path, monkeypatch):
    from prd_taskmaster.fleet import load_fleet_config

    monkeypatch.chdir(tmp_path)
    # the native engine is the sole generator: the default backend is "native".
    assert load_fleet_config()["backend"] == "native"

    cfg_dir = tmp_path / ".atlas-ai"
    cfg_dir.mkdir()
    (cfg_dir / "fleet.json").write_text(json.dumps({"backend": "native"}))
    assert load_fleet_config()["backend"] == "native"

    # an invalid/removed value (e.g. the removed "taskmaster", or garbage) is
    # silently repaired back to the "native" default.
    (cfg_dir / "fleet.json").write_text(json.dumps({"backend": "broken"}))
    assert load_fleet_config()["backend"] == "native"
