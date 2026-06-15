"""Acceptance gate: Google/Gemini provider in llm_client (hermetic; urlopen monkeypatched).

This file is the UNFAKABLE contract for adding the google provider. It is written
BEFORE the implementation and must not be modified by the worker. The worker's job
is to edit prd_taskmaster/llm_client.py until every test here passes.

Gemini REST contract (generativelanguage v1beta, generateContent):
  URL    : {base}/models/{model}:generateContent   base = https://generativelanguage.googleapis.com/v1beta
  Auth   : header  x-goog-api-key: <key>
  Body   : {"contents":[{"role":"user","parts":[{"text": <prompt>}]}],
            "generationConfig":{"maxOutputTokens": <max_tokens>}}
           + optional "system_instruction":{"parts":[{"text": <system>}]} when system given
  Result : data["candidates"][0]["content"]["parts"][0]["text"]
  Usage  : data["usageMetadata"]["promptTokenCount"] / ["candidatesTokenCount"]
Provider key discovery: GOOGLE_API_KEY or GEMINI_API_KEY, LOWEST precedence
(checked after anthropic, openai, and openai-compatible).
"""

import io
import json

import pytest

from prd_taskmaster import llm_client as L


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _google_ok(payload_text, usage=None):
    payload = {"candidates": [{"content": {"parts": [{"text": payload_text}]}}]}
    if usage is not None:
        payload["usageMetadata"] = usage
    return FakeResponse(json.dumps(payload).encode())


# ── discovery + precedence ───────────────────────────────────────────────────

def test_discover_key_google_from_google_api_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key-1")
    k = L.discover_key()
    assert k["provider"] == "google" and k["key"] == "g-key-1"


def test_discover_key_google_from_gemini_api_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key-2")
    k = L.discover_key()
    assert k["provider"] == "google" and k["key"] == "g-key-2"


def test_google_is_lowest_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    assert L.discover_key()["provider"] == "openai"  # openai still wins over google


# ── request shape + parse ────────────────────────────────────────────────────

def test_google_request_shape_and_parse(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key-1")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        captured["body"] = json.loads(req.data)
        return _google_ok('{"answer": 42}')

    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    out = L.generate_json("give me json", system="be terse", model="gemini-2.5-flash")
    assert out == {"answer": 42}
    assert "generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" in captured["url"]
    assert captured["headers"].get("x-goog-api-key") == "g-key-1"
    # contents carry the prompt
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "give me json"
    # system goes to system_instruction, not contents
    assert captured["body"]["system_instruction"]["parts"][0]["text"] == "be terse"


def test_google_default_model_is_gemini_flash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key-1")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _google_ok('{"ok": true}')

    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    assert L.generate_json("x") == {"ok": True}  # no model/tier given
    assert "models/gemini-2.5-flash:generateContent" in captured["url"]


def test_google_telemetry_includes_usage_tokens(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key-1")
    monkeypatch.setattr(
        L.urllib.request, "urlopen",
        lambda req, timeout=None: _google_ok(
            '{"x": 1}', usage={"promptTokenCount": 50, "candidatesTokenCount": 12}),
    )
    L.generate_json("x", task_id=21, model="gemini-2.5-flash")
    rows = [json.loads(l) for l in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["backend"] == "native-api"
    assert rows[0]["tokens_in"] == 50
    assert rows[0]["tokens_out"] == 12
