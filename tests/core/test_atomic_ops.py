from concurrent.futures import ThreadPoolExecutor
import os
import threading
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

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
    # Kill a real helper invocation immediately before replace, leaving its
    # current unique staging path behind, rather than inventing an obsolete name.
    worker = tmp_path / 'crash.py'
    worker.write_text('from pathlib import Path\nimport os\n'
                      'from prd_taskmaster import lib\n'
                      'lib.os.replace = lambda *args: os._exit(23)\n'
                      f'lib.atomic_write(Path({str(target)!r}), "partial")\n')
    result = subprocess.run([sys.executable, str(worker)],
                            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2])})
    assert result.returncode == 23
    abandoned, = tmp_path.glob('out.txt.tmp.*')
    assert abandoned.read_text() == 'partial'
    assert target.read_text() == 'original'
    atomic_write(target, "final")
    assert target.read_text() == "final"
    assert abandoned.read_text() == 'partial'


def test_atomic_write_threads_have_distinct_staging_files(tmp_path, monkeypatch):
    """Owner uniqueness tests bypass flock; reference writes must still be atomic."""
    from prd_taskmaster import lib
    target = tmp_path / "materializations.json"
    before_replace = threading.Barrier(2)
    replace = lib.os.replace
    staging_paths = []

    def overlap(source, destination):
        staging_paths.append(Path(source))
        before_replace.wait(timeout=5)
        replace(source, destination)

    monkeypatch.setattr(lib.os, "replace", overlap)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda content: atomic_write(target, content), ("first", "second")))
    assert len(set(staging_paths)) == 2
    assert target.read_text() in {"first", "second"}
    assert list(tmp_path.iterdir()) == [target]


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


@pytest.mark.parametrize('mask', [0o022, 0o077])
@pytest.mark.parametrize('existing', [None, 0o644, 0o755])
@pytest.mark.parametrize('writer', ['atomic_write', 'locked_update'])
def test_writes_preserve_modes(tmp_path, mask, existing, writer):
    target = tmp_path / 'mode.txt'
    if existing is not None:
        target.write_text('old')
        target.chmod(existing)
    previous = os.umask(mask)
    try:
        if writer == 'atomic_write':
            atomic_write(target, 'new')
        else:
            locked_update(target, lambda _: 'new')
    finally:
        os.umask(previous)
    expected = existing if existing is not None else 0o666 & ~mask
    assert stat.S_IMODE(target.stat().st_mode) == expected
    assert target.read_text() == 'new'


def test_atomic_write_never_changes_process_umask(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'umask', lambda *a: pytest.fail('process-wide umask changed'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: atomic_write(tmp_path / str(n), 'value'), range(8)))
    assert len(list(tmp_path.iterdir())) == 8


def test_atomic_write_replace_failure_removes_staging(tmp_path, monkeypatch):
    from prd_taskmaster import lib
    target = tmp_path / 'out.txt'
    target.write_text('original')
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(lib.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        atomic_write(target, 'new')
    assert target.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_stages_beside_target(tmp_path, monkeypatch):
    from prd_taskmaster import lib
    target = tmp_path / 'nested' / 'out.txt'
    mkstemp = tempfile.mkstemp
    seen = []
    def capture(*args, **kwargs):
        fd, name = mkstemp(*args, **kwargs)
        seen.append(Path(name))
        return fd, name
    monkeypatch.setattr(lib.tempfile, 'mkstemp', capture)
    atomic_write(target, 'value')
    assert len(seen) == 1 and seen[0].parent == target.parent
    assert target.read_text() == 'value'


def test_mcp_append_workflow_keeps_claude_mode(tmp_path, monkeypatch):
    import importlib.util
    import types
    class FakeMCP:
        def __init__(self, *args):
            pass
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    module = types.ModuleType('mcp.server.fastmcp')
    setattr(module, 'FastMCP', FakeMCP)
    monkeypatch.setitem(sys.modules, 'mcp.server.fastmcp', module)
    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('atomic_test_server', repo / 'mcp-server/server.py')
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    target = tmp_path / 'CLAUDE.md'
    target.write_text('User instructions\n')
    target.chmod(0o755)
    content = tmp_path / 'workflow.md'
    content.write_text('Workflow')
    result = server.append_workflow(str(target), str(content))
    assert result['ok'] and result['action'] == 'appended'
    assert 'Workflow' in target.read_text()
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
