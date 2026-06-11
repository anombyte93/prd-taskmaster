"""Privacy-first Atlas client telemetry."""

from __future__ import annotations

import uuid
import json
import os
import platform
import threading
import urllib.request as urllib_request
from pathlib import Path

from prd_taskmaster import __version__


_ATLAS_DIRNAME = ".atlas-ai"
_INSTALL_ID_FILENAME = "install_id"
_TELEMETRY_URL = "https://api.atlas-ai.au/telemetry"
_EVENTS = frozenset({"atlas_invoked", "reach_execute", "ship_check_ok", "install"})


def _install_id_path() -> Path:
    return Path.home() / _ATLAS_DIRNAME / _INSTALL_ID_FILENAME


def _valid_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def get_install_id() -> str:
    """Return the stable anonymous install UUID for this machine user."""
    path = _install_id_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if _valid_uuid4(existing):
        return existing

    install_id = str(uuid.uuid4())
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(install_id + "\n", encoding="utf-8")
    return install_id


def _config_opted_out() -> bool:
    for path in (
        Path.home() / _ATLAS_DIRNAME / "config.json",
        Path.cwd() / ".taskmaster" / "config.json",
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("telemetry") is False:
            return True
    return False


def _opted_out() -> bool:
    return os.environ.get("ATLAS_TELEMETRY") == "0" or _config_opted_out()


def _post_payload(payload: dict[str, str]) -> None:
    try:
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            _TELEMETRY_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib_request.urlopen(request, timeout=1) as response:
            response.read()
    except Exception:
        pass


def send_event(event_name: str) -> None:
    """Send a best-effort anonymous telemetry event without blocking exit."""
    if event_name not in _EVENTS or _opted_out():
        return

    try:
        payload = {
            "install_id": get_install_id(),
            "event": event_name,
            "version": __version__,
            "os": platform.system(),
        }
        thread = threading.Thread(target=lambda: _post_payload(payload), daemon=True)
        thread.start()
    except Exception:
        pass
