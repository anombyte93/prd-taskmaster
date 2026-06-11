"""Tests for privacy-first client telemetry."""

import json
import platform
import socket
from types import SimpleNamespace
import uuid

from prd_taskmaster import __version__
from prd_taskmaster import pipeline
from prd_taskmaster import shipcheck
from prd_taskmaster import telemetry


def test_get_install_id_creates_uuid4_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    install_id = telemetry.get_install_id()

    assert uuid.UUID(install_id).version == 4
    assert (tmp_path / ".atlas-ai" / "install_id").read_text().strip() == install_id


def test_get_install_id_is_stable_and_does_not_rewrite(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    install_dir = tmp_path / ".atlas-ai"
    install_dir.mkdir()
    existing = str(uuid.uuid4())
    install_file = install_dir / "install_id"
    install_file.write_text(existing + "\n")
    before = install_file.stat().st_mtime_ns

    assert telemetry.get_install_id() == existing
    assert install_file.stat().st_mtime_ns == before


def test_get_install_id_regenerates_corrupt_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    install_dir = tmp_path / ".atlas-ai"
    install_dir.mkdir()
    install_file = install_dir / "install_id"
    install_file.write_text("not-a-uuid\n")

    install_id = telemetry.get_install_id()

    assert uuid.UUID(install_id).version == 4
    assert install_id != "not-a-uuid"
    assert install_file.read_text().strip() == install_id


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"ok":true}'


def _run_threads_inline(monkeypatch):
    threads = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon
            threads.append(self)

        def start(self):
            self.target()

    threading_mod = getattr(telemetry, "threading", SimpleNamespace())
    monkeypatch.setattr(threading_mod, "Thread", ImmediateThread, raising=False)
    monkeypatch.setattr(telemetry, "threading", threading_mod, raising=False)
    return threads


def _patch_urlopen(monkeypatch, fake_urlopen):
    request_mod = getattr(telemetry, "urllib_request", SimpleNamespace())
    monkeypatch.setattr(request_mod, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(telemetry, "urllib_request", request_mod, raising=False)


def test_send_event_posts_exact_payload_in_daemon_thread(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    threads = _run_threads_inline(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    _patch_urlopen(monkeypatch, fake_urlopen)

    telemetry.send_event("atlas_invoked")

    assert len(threads) == 1
    assert threads[0].daemon is True
    assert captured["url"] == "https://api.atlas-ai.au/telemetry"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 1
    assert set(captured["payload"]) == {"install_id", "event", "version", "os"}
    assert uuid.UUID(captured["payload"]["install_id"]).version == 4
    assert captured["payload"]["event"] == "atlas_invoked"
    assert captured["payload"]["version"] == __version__
    assert captured["payload"]["os"] == platform.system()


def test_send_event_env_opt_out_skips_before_install_id_or_network(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ATLAS_TELEMETRY", "0")
    calls = []
    _run_threads_inline(monkeypatch)
    _patch_urlopen(monkeypatch, lambda request, timeout: calls.append(request))

    telemetry.send_event("atlas_invoked")

    assert calls == []
    assert not (tmp_path / ".atlas-ai" / "install_id").exists()


def test_send_event_config_opt_out_skips_before_install_id_or_network(monkeypatch, tmp_path):
    cases = [
        (tmp_path / "home-config", tmp_path / "home-config", tmp_path / "home-config" / ".atlas-ai" / "config.json"),
        (
            tmp_path / "project-config",
            tmp_path / "project-config" / "project",
            tmp_path / "project-config" / "project" / ".taskmaster" / "config.json",
        ),
    ]
    for home, cwd, target in cases:
        cwd.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(cwd)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"telemetry": false}\n')
        calls = []
        _run_threads_inline(monkeypatch)
        _patch_urlopen(monkeypatch, lambda request, timeout: calls.append(request))

        telemetry.send_event("reach_execute")

        assert calls == []
        assert not (home / ".atlas-ai" / "install_id").exists()


def test_send_event_swallow_errors_and_does_not_join(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    started = []

    class RecordingThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append(self)

        def join(self, *args, **kwargs):
            raise AssertionError("send_event must not join telemetry threads")

    threading_mod = getattr(telemetry, "threading", SimpleNamespace())
    monkeypatch.setattr(threading_mod, "Thread", RecordingThread, raising=False)
    monkeypatch.setattr(telemetry, "threading", threading_mod, raising=False)
    _patch_urlopen(monkeypatch, lambda request, timeout: (_ for _ in ()).throw(socket.timeout("down")))

    telemetry.send_event("ship_check_ok")

    assert len(started) == 1
    assert started[0].daemon is True
    started[0].target()


def test_send_event_invalid_event_is_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = []
    _run_threads_inline(monkeypatch)
    _patch_urlopen(monkeypatch, lambda request, timeout: calls.append(request))

    telemetry.send_event("goal_text_or_path")

    assert calls == []
    assert not (tmp_path / ".atlas-ai" / "install_id").exists()


def test_preflight_fires_atlas_invoked_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events = []
    monkeypatch.setattr(telemetry, "send_event", lambda event: events.append(event))

    result = pipeline.preflight()

    assert result["ok"] is True
    assert events == ["atlas_invoked"]


def test_advance_phase_fires_reach_execute_only_for_execute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events = []
    monkeypatch.setattr(telemetry, "send_event", lambda event: events.append(event))

    assert pipeline.advance_phase(None, "SETUP", {})["ok"] is True
    assert pipeline.advance_phase("SETUP", "DISCOVER", {})["ok"] is True
    assert pipeline.advance_phase("DISCOVER", "GENERATE", {})["ok"] is True
    assert pipeline.advance_phase("GENERATE", "HANDOFF", {})["ok"] is True
    assert events == []

    result = pipeline.advance_phase("HANDOFF", "EXECUTE", {})

    assert result["ok"] is True
    assert events == ["reach_execute"]


def _green_ship_project(root):
    atlas = root / ".atlas-ai"
    (atlas / "state").mkdir(parents=True)
    (atlas / "state" / "pipeline.json").write_text(json.dumps({"current_phase": "EXECUTE"}))
    tasks = root / ".taskmaster" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "tasks.json").write_text(
        json.dumps({"master": {"tasks": [{"id": 1, "status": "done"}]}})
    )
    cdd = atlas / "cdd"
    cdd.mkdir(parents=True)
    (cdd / "task-1.json").write_text("{}")
    docs = root / ".taskmaster" / "docs"
    docs.mkdir(parents=True)
    (docs / "plan.md").write_text("# Plan\n")


def test_ship_check_fires_ship_check_ok_only_on_real_pass(monkeypatch, tmp_path):
    _green_ship_project(tmp_path)
    events = []
    monkeypatch.setattr(telemetry, "send_event", lambda event: events.append(event))

    result = shipcheck.run_ship_check(cwd=str(tmp_path))
    dry_run = shipcheck.run_ship_check(cwd=str(tmp_path), dry_run=True)

    assert result["passed"] is True
    assert dry_run["passed"] is True
    assert events == ["ship_check_ok"]


def test_telemetry_hook_failures_do_not_change_return_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def boom(event):
        raise RuntimeError(f"{event} failed")

    monkeypatch.setattr(telemetry, "send_event", boom)

    assert pipeline.preflight()["ok"] is True
    assert pipeline.advance_phase(None, "SETUP", {})["ok"] is True
    assert pipeline.advance_phase("SETUP", "DISCOVER", {})["ok"] is True
    assert pipeline.advance_phase("DISCOVER", "GENERATE", {})["ok"] is True
    assert pipeline.advance_phase("GENERATE", "HANDOFF", {})["ok"] is True
    assert pipeline.advance_phase("HANDOFF", "EXECUTE", {})["ok"] is True

    ship_root = tmp_path / "ship"
    ship_root.mkdir()
    _green_ship_project(ship_root)
    result = shipcheck.run_ship_check(cwd=str(ship_root))

    assert result["passed"] is True
    assert result["exit_code"] == 0
