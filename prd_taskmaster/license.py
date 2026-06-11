"""Offline Atlas Pro license parsing and verification."""

import base64 as _base64
import json as _json
import math as _math
import os as _os
import re as _re
import time as _time
from pathlib import Path as _Path
from typing import Any as _Any

from prd_taskmaster import _ed25519


_KEY_PREFIX = "ATLAS-"
_PAYLOAD_FIELDS = ("lid", "sub", "plan", "iat", "exp", "v")
_PLANS = ("pro-monthly", "pro-annual")
PUBLIC_KEY = bytes.fromhex("1fc868c32afba550e6db6db038302a6bd83fbbd848a87191f3a03bdcccf7e88d")
_GRACE_SECONDS = 14 * 24 * 60 * 60
_REFRESH_WINDOW_SECONDS = 21 * 24 * 60 * 60
_REFRESH_RETRY_SECONDS = 24 * 60 * 60
_REFRESH_URL = "https://api.atlas-ai.au/license/refresh"
_LAST_REFRESH_FIELD = "last_refresh_attempt"
_LICENSE_DIRNAME = ".atlas-ai"
_LICENSE_FILENAME = "license.json"
_B64URL_RE = _re.compile(r"^[A-Za-z0-9_-]+$")
_HEX64_RE = _re.compile(r"^[0-9a-f]{64}$")


def _invalid(detail: str, payload: dict[str, _Any] | None = None) -> dict[str, _Any]:
    return {
        "ok": False,
        "status": "invalid",
        "detail": detail,
        "payload": payload,
        "payload_bytes": None,
        "signature": None,
    }


def _canonical_payload_bytes(payload: dict[str, _Any]) -> bytes:
    return _json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _b64url_decode(value: str) -> bytes:
    if not value or "=" in value or _B64URL_RE.fullmatch(value) is None:
        raise ValueError("invalid base64url segment")
    padded = value + ("=" * (-len(value) % 4))
    return _base64.urlsafe_b64decode(padded.encode("ascii"))


def _validate_payload(payload: dict[str, _Any]) -> str | None:
    if set(payload) != set(_PAYLOAD_FIELDS):
        return "payload fields must be exactly lid, sub, plan, iat, exp, v"
    if not isinstance(payload["lid"], str) or not payload["lid"]:
        return "lid must be a non-empty string"
    if not isinstance(payload["sub"], str) or _HEX64_RE.fullmatch(payload["sub"]) is None:
        return "sub must be a lowercase SHA-256 hex digest"
    if payload["plan"] not in _PLANS:
        return f"plan must be one of: {', '.join(_PLANS)}"
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        return "iat and exp must be integer Unix timestamps"
    if payload["exp"] < payload["iat"]:
        return "exp must be greater than or equal to iat"
    if payload["v"] != 1:
        return "v must be 1"
    return None


def parse_key(key_str: str) -> dict[str, _Any]:
    """Parse an Atlas license key into payload bytes and signature bytes."""
    if not isinstance(key_str, str) or not key_str.startswith(_KEY_PREFIX):
        return _invalid("license key must start with ATLAS-")

    body = key_str[len(_KEY_PREFIX):]
    if body.count(".") != 1:
        return _invalid("license key must contain one payload/signature separator")

    payload_segment, signature_segment = body.split(".", 1)
    try:
        payload_bytes = _b64url_decode(payload_segment)
        signature = _b64url_decode(signature_segment)
    except (ValueError, _base64.binascii.Error):
        return _invalid("invalid base64url data")

    if len(signature) != 64:
        return _invalid("Ed25519 signature must be 64 bytes")

    try:
        payload = _json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError):
        return _invalid("payload must be UTF-8 JSON")

    if not isinstance(payload, dict):
        return _invalid("payload must be a JSON object")

    detail = _validate_payload(payload)
    if detail:
        return _invalid(detail, payload)

    if payload_bytes != _canonical_payload_bytes(payload):
        return _invalid("payload JSON is not canonical", payload)

    return {
        "ok": True,
        "status": "parsed",
        "detail": "parsed",
        "payload": payload,
        "payload_bytes": payload_bytes,
        "signature": signature,
        "key": key_str,
    }


def verify_signature(payload: bytes, sig: bytes, pubkey: bytes | None = None) -> bool:
    """Return True when sig verifies for payload under pubkey."""
    pubkey = PUBLIC_KEY if pubkey is None else pubkey
    try:
        return _ed25519.verify(pubkey, payload, sig)
    except Exception:
        return False


def _invalid_status(detail: str) -> dict[str, _Any]:
    return {"status": "invalid", "days_remaining": None, "detail": detail}


def get_status(key_str: str | dict[str, _Any] | None = None, *, now: int | None = None) -> dict[str, _Any]:
    """Return active, grace, expired, or invalid status for a license key."""
    if key_str is None:
        parsed = load_license()
        if parsed is None:
            return _invalid_status("no license saved")
    else:
        parsed = key_str if isinstance(key_str, dict) else parse_key(key_str)

    if not parsed.get("ok"):
        return _invalid_status(parsed.get("detail", "invalid license key"))

    if not verify_signature(parsed["payload_bytes"], parsed["signature"], PUBLIC_KEY):
        return _invalid_status("signature mismatch")

    current = int(_time.time() if now is None else now)
    exp = int(parsed["payload"]["exp"])
    period_end = exp - _GRACE_SECONDS

    if current <= period_end:
        return {"status": "active", "days_remaining": None, "detail": "license active"}
    if current <= exp:
        seconds_remaining = max(0, exp - current)
        days_remaining = _math.ceil(seconds_remaining / 86400)
        return {
            "status": "grace",
            "days_remaining": days_remaining,
            "detail": f"license in grace period ({days_remaining} days remaining)",
        }
    return {"status": "expired", "days_remaining": 0, "detail": "license expired"}


def _license_path() -> _Path:
    return _Path.home() / _LICENSE_DIRNAME / _LICENSE_FILENAME


def _read_license_store() -> dict[str, _Any]:
    path = _license_path()
    if not path.is_file():
        return {}
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, _json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_license_store(data: dict[str, _Any]) -> None:
    path = _license_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        _os.chmod(path.parent, 0o700)
    except OSError:
        pass

    payload = _json.dumps(data, indent=2)
    flags = _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC
    fd = _os.open(path, flags, 0o600)
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")
    finally:
        try:
            _os.chmod(path, 0o600)
        except OSError:
            pass


def save_license(key_str: str, *, now: int | None = None) -> dict[str, _Any]:
    """Persist a verified active or grace license under ~/.atlas-ai/license.json."""
    status = get_status(key_str, now=now)
    if status["status"] not in {"active", "grace"}:
        return {"ok": False, **status}

    path = _license_path()
    _write_license_store({"key": key_str})

    return {"ok": True, **status, "path": str(path)}


def load_license() -> dict[str, _Any] | None:
    """Load and parse the saved license key, returning None on missing/corrupt data."""
    data = _read_license_store()
    key_str = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key_str, str):
        return None
    parsed = parse_key(key_str)
    if not parsed.get("ok"):
        return None
    last_attempt = data.get(_LAST_REFRESH_FIELD)
    if isinstance(last_attempt, int):
        parsed[_LAST_REFRESH_FIELD] = last_attempt
    return parsed


def _record_refresh_attempt(now: int) -> None:
    data = _read_license_store()
    if not isinstance(data.get("key"), str):
        return
    data[_LAST_REFRESH_FIELD] = int(now)
    _write_license_store(data)


def _log_refresh_failure(detail: str) -> None:
    try:
        print(f"atlas license refresh skipped: {detail}", file=__import__("sys").stderr)
    except Exception:
        pass


def _should_refresh(license_obj: dict[str, _Any] | None, now: int | None = None) -> bool:
    current = int(_time.time() if now is None else now)
    if not isinstance(license_obj, dict) or not license_obj.get("ok"):
        return False

    status = get_status(license_obj, now=current)
    if status["status"] not in {"active", "grace"}:
        return False

    payload = license_obj.get("payload")
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(exp, int) or exp - current > _REFRESH_WINDOW_SECONDS:
        return False

    last_attempt = license_obj.get(_LAST_REFRESH_FIELD)
    if isinstance(last_attempt, int) and current - last_attempt < _REFRESH_RETRY_SECONDS:
        return False

    return True


def _http_error_reason(exc: _Any) -> str:
    code = getattr(exc, "code", None)
    reason = f"http_{code}" if code is not None else "http_error"
    try:
        body = exc.read()
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        data = _json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("reason"), str):
            return data["reason"]
    except Exception:
        pass
    return reason


def _refresh_if_needed(*, now: int | None = None) -> str:
    current = int(_time.time() if now is None else now)
    if _os.environ.get("ATLAS_TELEMETRY") == "0":
        return "skipped"

    saved = load_license()
    if not _should_refresh(saved, now=current):
        return "skipped"

    lid = saved["payload"]["lid"]
    _record_refresh_attempt(current)

    request_mod = __import__("urllib.request", fromlist=["Request", "urlopen"])
    error_mod = __import__("urllib.error", fromlist=["HTTPError", "URLError"])
    socket_mod = __import__("socket")
    body = _json.dumps({"lid": lid}).encode("utf-8")
    request = request_mod.Request(
        _REFRESH_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )

    try:
        with request_mod.urlopen(request, timeout=5) as response:
            response_body = response.read()
    except error_mod.HTTPError as exc:
        _log_refresh_failure(_http_error_reason(exc))
        return "failed"
    except (error_mod.URLError, socket_mod.timeout, TimeoutError, OSError, ConnectionError) as exc:
        _log_refresh_failure(str(exc))
        return "failed"
    except Exception as exc:
        _log_refresh_failure(str(exc))
        return "failed"

    try:
        data = _json.loads(response_body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, _json.JSONDecodeError):
        _log_refresh_failure("invalid refresh response")
        return "failed"

    new_key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(new_key, str):
        _log_refresh_failure("refresh response missing key")
        return "failed"

    parsed = parse_key(new_key)
    if not parsed.get("ok") or not verify_signature(parsed["payload_bytes"], parsed["signature"], PUBLIC_KEY):
        _log_refresh_failure("refreshed key failed verification")
        return "failed"

    saved_result = save_license(new_key, now=current)
    if not saved_result.get("ok"):
        _log_refresh_failure(saved_result.get("detail", "refreshed key rejected"))
        return "failed"

    _record_refresh_attempt(current)
    return "refreshed"


def __getattr__(name: str) -> _Any:
    if name == "should_refresh":
        return _should_refresh
    if name == "refresh_if_needed":
        return _refresh_if_needed
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
