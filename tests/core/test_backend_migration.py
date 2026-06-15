"""Migration tests: NativeBackend is the sole generator. The task-master backend
was removed (spec §9.4); backend='auto' resolves to NativeBackend unconditionally
and a legacy backend='taskmaster' config falls back to native with a warning.

Spec: docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md §9.2, §9.4
"""

import importlib
import warnings

import pytest

from prd_taskmaster import backend as backend_mod
from prd_taskmaster.backend import (
    NativeBackend,
    get_backend,
)


def test_auto_resolves_native(monkeypatch):
    """The migration's core invariant: 'auto' is NativeBackend. Post-deletion
    there is no task-master binary probe at all — native is unconditional."""
    be = get_backend({"backend": "auto"})
    assert isinstance(be, NativeBackend)
    assert be.name == "native"


def test_missing_backend_key_defaults_to_native():
    """An empty/legacy config (no 'backend' key) defaults to 'auto' -> Native."""
    be = get_backend({})
    assert isinstance(be, NativeBackend)


def test_explicit_native_returns_native():
    be = get_backend({"backend": "native"})
    assert isinstance(be, NativeBackend)


# ─── Post-deletion: the task-master surface is gone (Chunk 6 Task 4) ──────────

def test_taskmaster_backend_is_removed():
    """Post-deletion: TaskMasterBackend no longer exists in the backend module."""
    assert not hasattr(backend_mod, "TaskMasterBackend")


def test_tm_parallel_module_is_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("prd_taskmaster.tm_parallel")


def test_backend_choices_is_native_only():
    from prd_taskmaster import fleet

    assert fleet.BACKEND_CHOICES == {"native"}


def test_taskmaster_backend_request_falls_back_to_native(recwarn):
    """An old fleet.json still pinned to backend='taskmaster' must NOT crash now
    that the class is gone — it resolves to native with a deprecation warning."""
    be = get_backend({"backend": "taskmaster"})
    assert isinstance(be, NativeBackend)
    assert any(issubclass(w.category, DeprecationWarning) for w in recwarn.list)
