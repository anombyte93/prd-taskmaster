"""v4.1-T3: llm_client — stdlib structured-generation client (hermetic; urlopen monkeypatched)."""

import io
import json
import urllib.error

import pytest

from prd_taskmaster import llm_client as L


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _anthropic_ok(payload_text, usage=None):
    payload = {"content": [{"text": payload_text}]}
    if usage is not None:
        payload["usage"] = usage
    return FakeResponse(json.dumps(payload).encode())


def _openai_ok(payload_text, usage=None):
    payload = {"choices": [{"message": {"content": payload_text}}]}
    if usage is not None:
        payload["usage"] = usage
    return FakeResponse(json.dumps(payload).encode())


# ── discover_key precedence ──────────────────────────────────────────────────

def test_discover_key_prefers_anthropic_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-x")
    k = L.discover_key()
    assert k["provider"] == "anthropic" and k["key"] == "sk-ant-x"


def test_discover_key_openai_fallback_and_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    (tmp_path / ".env").write_text('OPENAI_API_KEY="sk-from-dotenv"\n')
    k = L.discover_key()
    assert k["provider"] == "openai" and k["key"] == "sk-from-dotenv"


def test_discover_key_excludes_local_free_proxy(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "local-perplexity-api-free")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:8765")
    assert L.discover_key() is None  # proxy is agent-path only


def test_discover_key_none_when_nothing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert L.discover_key() is None


# ── generate_json request shapes + extraction ladder ─────────────────────────

def test_anthropic_request_shape_and_parse(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    captured = {}
    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        return _anthropic_ok('{"answer": 42}')
    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    out = L.generate_json("give me json", model="claude-haiku-4-5-20251001")
    assert out == {"answer": 42}
    assert "anthropic.com/v1/messages" in captured["url"]
    assert captured["headers"].get("X-api-key") == "sk-ant-x"
    assert captured["body"]["model"] == "claude-haiku-4-5-20251001"


def test_fence_stripping_extraction(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(L.urllib.request, "urlopen",
                        lambda req, timeout=None: _anthropic_ok('```json\n{"a": 1}\n```'))
    assert L.generate_json("x") == {"a": 1}


def test_invalid_json_retries_once_then_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    calls = []
    def fake(req, timeout=None):
        calls.append(1)
        return _anthropic_ok("definitely not json at all")
    monkeypatch.setattr(L.urllib.request, "urlopen", fake)
    with pytest.raises(L.LLMError) as e:
        L.generate_json("x")
    assert e.value.kind == "invalid_json" and len(calls) == 2  # one retry


def test_auth_error_no_retry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bad")
    calls = []
    def fake(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(L.urllib.request, "urlopen", fake)
    with pytest.raises(L.LLMError) as e:
        L.generate_json("x")
    assert e.value.kind == "auth" and len(calls) == 1


def test_429_retries_once_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    calls = []
    def fake(req, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {"Retry-After": "0"}, io.BytesIO(b"{}"))
        return _anthropic_ok('{"ok": true}')
    monkeypatch.setattr(L, "_sleep", lambda s: None, raising=False)
    monkeypatch.setattr(L.urllib.request, "urlopen", fake)
    assert L.generate_json("x") == {"ok": True}
    assert len(calls) == 2


def test_telemetry_rows_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(L.urllib.request, "urlopen",
                        lambda req, timeout=None: _anthropic_ok('{"x": 1}'))
    L.generate_json("x", task_id=7)
    rows = [json.loads(l) for l in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows and rows[0]["backend"] == "native-api" and rows[0]["task_id"] == 7
    assert "tokens_in" not in rows[0] and "tokens_out" not in rows[0]


def test_anthropic_telemetry_includes_usage_tokens(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(
        L.urllib.request,
        "urlopen",
        lambda req, timeout=None: _anthropic_ok(
            '{"x": 1}',
            usage={"input_tokens": 123, "output_tokens": 45},
        ),
    )

    L.generate_json("x", task_id=8, model="claude-haiku-4-5-20251001")

    rows = [json.loads(l) for l in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["tokens_in"] == 123
    assert rows[0]["tokens_out"] == 45


def test_openai_telemetry_includes_usage_tokens(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(
        L.urllib.request,
        "urlopen",
        lambda req, timeout=None: _openai_ok(
            '{"x": 1}',
            usage={"prompt_tokens": 30, "completion_tokens": 7},
        ),
    )

    L.generate_json("x", task_id=9, model="claude-sonnet-4-6")

    rows = [json.loads(l) for l in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["tokens_in"] == 30
    assert rows[0]["tokens_out"] == 7


def test_generate_json_default_return_unchanged(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(
        L.urllib.request,
        "urlopen",
        lambda req, timeout=None: _anthropic_ok('{"ok": true}'),
    )

    assert L.generate_json("x", task_id=10) == {"ok": True}


def test_generate_json_can_return_success_telemetry_ref(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(
        L.urllib.request,
        "urlopen",
        lambda req, timeout=None: _anthropic_ok(
            '{"ok": true}',
            usage={"input_tokens": 11, "output_tokens": 3},
        ),
    )

    result, telemetry_ref = L.generate_json(
        "x",
        task_id=11,
        model="claude-haiku-4-5-20251001",
        return_telemetry_ref=True,
    )

    assert result == {"ok": True}
    assert telemetry_ref["path"] == str(tmp_path / ".atlas-ai" / "telemetry.jsonl")
    assert telemetry_ref["line"] == 1
    assert telemetry_ref["op_class"] == "structured_gen"
    assert telemetry_ref["model"] == "claude-haiku-4-5-20251001"
    assert telemetry_ref["backend"] == "native-api"
    assert telemetry_ref["exit"] == 0
    assert isinstance(telemetry_ref["ts"], str) and telemetry_ref["ts"]

    rows = [json.loads(l) for l in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["task_id"] == 11
    assert rows[0]["tokens_in"] == 11
    assert rows[0]["tokens_out"] == 3
