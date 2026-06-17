"""Minimal stdlib structured-generation client (v4.1-T3).

The native backend's headless AI path: one-shot JSON generation against
anthropic or openai-compatible APIs via urllib. Deliberately small —
two providers, one retry per failure class, telemetry per HTTP attempt.
The local free Perplexity proxy is EXCLUDED (returns prose where strict
JSON is needed); that traffic stays on the agent path.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from prd_taskmaster.economy import TIER_MODEL_IDS, append_telemetry
from prd_taskmaster.lib import _read_env_file_value

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"

_LOCAL_PROXY_MARKERS = ("127.0.0.1:8765", "localhost:8765")


def _sleep(seconds):
    time.sleep(seconds)


class LLMError(Exception):
    """kind in {"no_key", "auth", "http", "timeout", "invalid_json"}."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _env_or_dotenv(name):
    return os.environ.get(name) or _read_env_file_value(Path(".env"), name)


def discover_key():
    """Find a usable structured-gen API. Precedence: anthropic > openai >
    openai-compatible. The local free proxy is never returned."""
    key = _env_or_dotenv("ANTHROPIC_API_KEY")
    if key:
        return {"provider": "anthropic", "key": key, "base_url": ANTHROPIC_URL}

    key = _env_or_dotenv("OPENAI_API_KEY")
    if key:
        base = _env_or_dotenv("OPENAI_BASE_URL") or OPENAI_DEFAULT_BASE
        return {"provider": "openai", "key": key, "base_url": base}

    key = _env_or_dotenv("OPENAI_COMPATIBLE_API_KEY")
    if key:
        base = (
            _env_or_dotenv("OPENAI_COMPATIBLE_BASE_URL")
            or _env_or_dotenv("OPENAI_BASE_URL")
            or ""
        )
        if not base or any(m in base for m in _LOCAL_PROXY_MARKERS) or key == "local-perplexity-api-free":
            return None  # free proxy: agent path only
        return {"provider": "openai-compatible", "key": key, "base_url": base}

    key = _env_or_dotenv("GOOGLE_API_KEY") or _env_or_dotenv("GEMINI_API_KEY")
    if key:
        return {"provider": "google", "key": key, "base_url": "https://generativelanguage.googleapis.com/v1beta"}

    return None


def _resolve_model(model, tier, provider):
    if model:
        return model
    if provider == "anthropic":
        short = {"fast": "haiku", "standard": "sonnet", "capable": "opus", "frontier": "fable"}.get(tier or "standard", "sonnet")
        return TIER_MODEL_IDS.get(short, TIER_MODEL_IDS["sonnet"])
    if provider == "google":
        return "gemini-2.5-flash"
    return DEFAULT_OPENAI_MODEL


def _extract_json(text):
    """loads -> fence-strip -> balanced first {..}/[..] scan."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        try:
            return json.loads("\n".join(lines))
        except json.JSONDecodeError:
            stripped = "\n".join(lines)

    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
            elif ch == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(stripped[start:i + 1])
                        except json.JSONDecodeError:
                            break
    return None


def _usage_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _usage_fields(provider, data):
    if provider == "google":
        usage = data
    else:
        usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return {}
    if provider == "anthropic":
        tokens_in = _usage_int(usage.get("input_tokens"))
        tokens_out = _usage_int(usage.get("output_tokens"))
    elif provider == "google":
        tokens_in = _usage_int(usage.get("promptTokenCount"))
        tokens_out = _usage_int(usage.get("candidatesTokenCount"))
    else:
        tokens_in = _usage_int(usage.get("prompt_tokens"))
        tokens_out = _usage_int(usage.get("completion_tokens"))
    if tokens_in is None or tokens_out is None:
        return {}
    return {"tokens_in": tokens_in, "tokens_out": tokens_out}


def _http_call(creds, model, system, prompt, max_tokens, timeout):
    if creds["provider"] == "anthropic":
        url = ANTHROPIC_URL
        headers = {
            "x-api-key": creds["key"],
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
    elif creds["provider"] == "google":
        base = creds["base_url"].rstrip("/")
        url = f"{base}/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": creds["key"],
            "Content-Type": "application/json",
        }
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
    else:
        base = creds["base_url"].rstrip("/")
        url = base + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + creds["key"],
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if "api.openai.com" in url:
            body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    usage_for_telemetry = _usage_fields(creds["provider"], data.get("usageMetadata", {})) if creds["provider"] == "google" else _usage_fields(creds["provider"], data)

    if creds["provider"] == "anthropic":
        return data["content"][0]["text"], usage_for_telemetry
    elif creds["provider"] == "google":
        return data["candidates"][0]["content"]["parts"][0]["text"], usage_for_telemetry
    return data["choices"][0]["message"]["content"], usage_for_telemetry


def generate_json(prompt, *, system="", schema_hint="", model=None, tier=None,
                  max_tokens=8192, timeout=120, op_class="structured_gen", task_id=None,
                  return_telemetry_ref=False):
    """One structured-generation call returning parsed JSON.

    Retry policy: ONE retry on invalid JSON (with the parse error fed back);
    ONE retry on 429/5xx/URLError; 401/403 fail immediately. One telemetry
    row per HTTP attempt (backend=native-api)."""
    creds = discover_key()
    if not creds:
        raise LLMError("no_key", "no structured-gen API key available (agent path required)")

    resolved_model = _resolve_model(model, tier, creds["provider"])
    full_prompt = prompt
    if schema_hint:
        full_prompt += "\n\nReturn ONLY valid JSON matching:\n" + schema_hint

    parse_retry = False
    http_retry_used = False
    attempt_prompt = full_prompt

    for attempt in range(4):  # bounded: <=2 parse attempts x <=2 http attempts
        start = time.monotonic()
        status = None
        try:
            text, usage = _http_call(creds, resolved_model, system, attempt_prompt, max_tokens, timeout)
            status = 200
        except urllib.error.HTTPError as e:
            status = e.code
            _telemetry(op_class, task_id, resolved_model, 1, start, parse_retry, status)
            if e.code in (401, 403):
                raise LLMError("auth", f"HTTP {e.code} from {creds['provider']}")
            if e.code == 429 or e.code >= 500:
                if http_retry_used:
                    raise LLMError("http", f"HTTP {e.code} after retry")
                http_retry_used = True
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    delay = min(float(retry_after), 5.0) if retry_after else 2.0
                except (TypeError, ValueError):
                    delay = 2.0
                _sleep(delay)
                continue
            raise LLMError("http", f"HTTP {e.code}")
        except urllib.error.URLError as e:
            _telemetry(op_class, task_id, resolved_model, 1, start, parse_retry, None)
            if http_retry_used:
                raise LLMError("timeout", f"network error after retry: {e.reason}")
            http_retry_used = True
            _sleep(2.0)
            continue

        result = _extract_json(text)
        telemetry_ref = _telemetry(op_class, task_id, resolved_model, 0 if result is not None else 1,
                                   start, parse_retry, status, usage)
        if result is not None:
            if return_telemetry_ref:
                return result, telemetry_ref
            return result
        if parse_retry:
            raise LLMError("invalid_json", "output failed JSON parsing after one retry")
        parse_retry = True
        attempt_prompt = (
            full_prompt
            + "\nYour previous output failed json.loads. Return ONLY the JSON, no prose, no fences."
        )

    raise LLMError("http", "attempt budget exhausted")


def _telemetry(op_class, task_id, model, exit_code, start, parse_retry, http_status, usage=None):
    from datetime import datetime, timezone

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "op_class": op_class,
        "task_id": task_id,
        "model": model,
        "backend": "native-api",
        "exit": exit_code,
        "wall_ms": int((time.monotonic() - start) * 1000),
        "escalated": False,
        "parse_retry": parse_retry,
        "http_status": http_status,
    }
    if isinstance(usage, dict):
        tokens_in = _usage_int(usage.get("tokens_in"))
        tokens_out = _usage_int(usage.get("tokens_out"))
        if tokens_in is not None and tokens_out is not None:
            row["tokens_in"] = tokens_in
            row["tokens_out"] = tokens_out
    return append_telemetry(row)
