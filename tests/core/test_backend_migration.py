"""Migration tests: backend='auto' resolves to NativeBackend unconditionally,
backend='taskmaster' still works for one deprecation release with a warning.

Spec: docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md §9.2
"""

import warnings

import pytest

from prd_taskmaster import backend as backend_mod
from prd_taskmaster.backend import (
    NativeBackend,
    TaskMasterBackend,
    get_backend,
)


def test_auto_resolves_native_even_when_taskmaster_binary_present(monkeypatch):
    """The migration's core invariant: 'auto' is NativeBackend even when the
    task-master binary is on PATH and detect() reports it available.

    We monkeypatch TaskMasterBackend.detect to claim availability; the old
    code would have returned the TaskMasterBackend in that case. Post-flip it
    must NOT — 'auto' returns NativeBackend unconditionally.
    """
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": True, "ai_ops": True},
    )
    be = get_backend({"backend": "auto"})
    assert isinstance(be, NativeBackend)
    assert be.name == "native"


def test_auto_resolves_native_when_taskmaster_binary_absent(monkeypatch):
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": False, "ai_ops": False},
    )
    be = get_backend({"backend": "auto"})
    assert isinstance(be, NativeBackend)


def test_missing_backend_key_defaults_to_native(monkeypatch):
    """An empty/legacy config (no 'backend' key) defaults to 'auto' -> Native."""
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": True},
    )
    be = get_backend({})
    assert isinstance(be, NativeBackend)


def test_explicit_native_returns_native():
    be = get_backend({"backend": "native"})
    assert isinstance(be, NativeBackend)


def test_explicit_taskmaster_still_works_but_warns():
    """backend='taskmaster' is honored for ONE deprecation release, with a
    DeprecationWarning so dispatch logs surface the impending removal."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        be = get_backend({"backend": "taskmaster"})
    assert isinstance(be, TaskMasterBackend)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert any("taskmaster" in str(w.message).lower() for w in caught)


def test_get_backend_does_not_call_taskmaster_detect_on_auto(monkeypatch):
    """Regression guard: the old auto path constructed a TaskMasterBackend and
    called .detect(). The flip must NOT touch TaskMasterBackend at all on auto —
    no binary probe cost, no import-time spawn."""
    called = {"detect": False}

    def boom(self):
        called["detect"] = True
        return {"available": True}

    monkeypatch.setattr(TaskMasterBackend, "detect", boom)
    get_backend({"backend": "auto"})
    assert called["detect"] is False
