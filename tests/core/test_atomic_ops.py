import os
import threading
from pathlib import Path

from prd_taskmaster.lib import atomic_write, locked_update, emit_json_error


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "out.txt"
    atomic_write(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_replaces_existing(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("old")
    atomic_write(target, "new")
    assert target.read_text() == "new"


def test_atomic_write_survives_mid_write_crash_simulation(tmp_path):
    """Atomic write: tmp file exists but not moved should not corrupt target."""
    target = tmp_path / "out.txt"
    target.write_text("original")
    # simulate a tmp file left behind from aborted atomic_write
    (tmp_path / f"out.txt.tmp.{os.getpid()}").write_text("partial")
    # a fresh atomic_write should still produce clean result
    atomic_write(target, "final")
    assert target.read_text() == "final"


def test_locked_update_serializes_concurrent_writes(tmp_path):
    target = tmp_path / "counter.txt"
    target.write_text("0")

    def incr():
        locked_update(target, lambda s: str(int(s.strip() or "0") + 1))

    threads = [threading.Thread(target=incr) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert int(target.read_text().strip()) == 10, "All 10 increments must land (no lost updates)"


def test_emit_json_error_returns_dict_not_exit():
    """Functions must return dicts, NOT call sys.exit (per spec §13.3)."""
    result = emit_json_error("test error", code=42)
    assert result["ok"] is False
    assert result["error"] == "test error"
    assert result["code"] == 42
