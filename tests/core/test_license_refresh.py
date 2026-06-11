"""Tests for silent Atlas license refresh."""

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from prd_taskmaster import capabilities
from prd_taskmaster import license


REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((REPO_ROOT / "tests" / "license" / "test_vectors.json").read_text())
VALID = next(v for v in VECTORS["vectors"] if v["name"] == "valid")
BAD_SIGNATURE = next(v for v in VECTORS["vectors"] if v["name"] == "signature-mismatch")
DAY = 24 * 60 * 60


class _Response:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def _activate_fixture_license(monkeypatch, tmp_path, *, now: int) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
    result = license.save_license(VALID["key"], now=now)
    assert result["ok"] is True


def test_should_refresh_only_for_active_or_grace_license_within_window(monkeypatch):
    monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
    parsed = license.parse_key(VALID["key"])
    exp = VALID["payload"]["exp"]

    assert license.should_refresh(parsed, now=exp - (20 * DAY)) is True
    assert license.should_refresh(parsed, now=exp - (22 * DAY)) is False
    assert license.should_refresh(parsed, now=exp - (7 * DAY)) is True
    assert license.should_refresh(parsed, now=exp + 1) is False
    assert license.should_refresh(license.parse_key(BAD_SIGNATURE["key"]), now=exp - (7 * DAY)) is False


def test_should_refresh_respects_last_attempt_throttle(monkeypatch):
    monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
    exp = VALID["payload"]["exp"]
    now = exp - (7 * DAY)
    parsed = license.parse_key(VALID["key"])

    throttled = dict(parsed, last_refresh_attempt=now - 60)
    stale = dict(parsed, last_refresh_attempt=now - DAY - 1)

    assert license.should_refresh(throttled, now=now) is False
    assert license.should_refresh(stale, now=now) is True


def test_refresh_if_needed_posts_lid_verifies_and_saves(monkeypatch, tmp_path):
    now = VALID["payload"]["exp"] - (7 * DAY)
    _activate_fixture_license(monkeypatch, tmp_path, now=now)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers.get("Content-type")
        captured["timeout"] = timeout
        return _Response({"ok": True, "key": VALID["key"]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = license.refresh_if_needed(now=now)

    assert result == "refreshed"
    assert captured == {
        "url": "https://api.atlas-ai.au/license/refresh",
        "method": "POST",
        "body": {"lid": VALID["payload"]["lid"]},
        "content_type": "application/json",
        "timeout": 5,
    }
    stored = json.loads((tmp_path / ".atlas-ai" / "license.json").read_text())
    assert stored["key"] == VALID["key"]
    assert stored["last_refresh_attempt"] == now


def test_refresh_rejects_badly_signed_wire_key(monkeypatch, tmp_path):
    now = VALID["payload"]["exp"] - (7 * DAY)
    _activate_fixture_license(monkeypatch, tmp_path, now=now)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _Response({"ok": True, "key": BAD_SIGNATURE["key"]}),
    )

    result = license.refresh_if_needed(now=now)

    stored = json.loads((tmp_path / ".atlas-ai" / "license.json").read_text())
    assert result == "failed"
    assert stored["key"] == VALID["key"]


def test_refresh_failure_paths_are_non_fatal(monkeypatch, tmp_path):
    now = VALID["payload"]["exp"] - (7 * DAY)
    failures = [
        urllib.error.HTTPError(
            "https://api.atlas-ai.au/license/refresh",
            403,
            "Forbidden",
            {},
            None,
        ),
        socket.timeout("timed out"),
        urllib.error.URLError("offline"),
        ConnectionError("offline"),
    ]

    for index, failure in enumerate(failures):
        home = tmp_path / str(index)
        _activate_fixture_license(monkeypatch, home, now=now)

        def fake_urlopen(request, timeout, exc=failure):
            raise exc

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        result = license.refresh_if_needed(now=now)

        stored = json.loads((home / ".atlas-ai" / "license.json").read_text())
        assert result == "failed"
        assert stored["key"] == VALID["key"]


def test_refresh_opt_out_skips_before_network_or_attempt_file(monkeypatch, tmp_path):
    now = VALID["payload"]["exp"] - (7 * DAY)
    _activate_fixture_license(monkeypatch, tmp_path, now=now)
    monkeypatch.setenv("ATLAS_TELEMETRY", "0")

    def fail_if_called(request, timeout):
        raise AssertionError("refresh should not call the network when opted out")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)

    result = license.refresh_if_needed(now=now)

    stored = json.loads((tmp_path / ".atlas-ai" / "license.json").read_text())
    assert result == "skipped"
    assert "last_refresh_attempt" not in stored


def test_capabilities_refreshes_once_when_needed(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    calls = []

    monkeypatch.setattr(
        capabilities,
        "detect_atlas_launcher",
        lambda: {"installed": False, "mcp_registered": True},
    )
    monkeypatch.setattr(
        capabilities.license,
        "get_status",
        lambda: {"status": "active", "days_remaining": None, "detail": "license active"},
    )
    monkeypatch.setattr(capabilities.license, "load_license", lambda: {"payload": VALID["payload"], "ok": True})
    monkeypatch.setattr(capabilities.license, "should_refresh", lambda parsed: True)
    monkeypatch.setattr(capabilities.license, "refresh_if_needed", lambda: calls.append("refresh"))

    result = capabilities.run_detect_capabilities()

    assert calls == ["refresh"]
    assert result["tier"] == "premium"


def test_capabilities_skips_refresh_when_not_needed(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    calls = []

    monkeypatch.setattr(
        capabilities,
        "detect_atlas_launcher",
        lambda: {"installed": False, "mcp_registered": True},
    )
    monkeypatch.setattr(
        capabilities.license,
        "get_status",
        lambda: {"status": "active", "days_remaining": None, "detail": "license active"},
    )
    monkeypatch.setattr(capabilities.license, "load_license", lambda: {"payload": VALID["payload"], "ok": True})
    monkeypatch.setattr(capabilities.license, "should_refresh", lambda parsed: False)
    monkeypatch.setattr(capabilities.license, "refresh_if_needed", lambda: calls.append("refresh"))

    capabilities.run_detect_capabilities()

    assert calls == []


def test_capabilities_survives_refresh_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        capabilities,
        "detect_atlas_launcher",
        lambda: {"installed": False, "mcp_registered": True},
    )
    monkeypatch.setattr(
        capabilities.license,
        "get_status",
        lambda: {"status": "active", "days_remaining": None, "detail": "license active"},
    )
    monkeypatch.setattr(capabilities.license, "load_license", lambda: {"payload": VALID["payload"], "ok": True})
    monkeypatch.setattr(capabilities.license, "should_refresh", lambda parsed: True)

    def boom():
        raise RuntimeError("refresh exploded")

    monkeypatch.setattr(capabilities.license, "refresh_if_needed", boom)

    result = capabilities.run_detect_capabilities()

    assert result["ok"] is True
    assert result["tier"] == "premium"
