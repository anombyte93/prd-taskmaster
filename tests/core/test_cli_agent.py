"""Chunk 2: cli_agent — keyless CLI-agent structured-JSON provider.

Hermetic: every subprocess.run is monkeypatched (no real claude/codex/gemini),
no network. Telemetry asserted by chdir-ing into tmp_path and reading the
.atlas-ai/telemetry.jsonl the module appends to.
"""

import json
import subprocess

import pytest

from prd_taskmaster import cli_agent as C


# ── A reusable fake for subprocess.run ───────────────────────────────────────
class FakeCompleted:
    """Mimics subprocess.CompletedProcess just enough for cli_agent."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_runner(scripted):
    """Return a fake subprocess.run that records calls and replays `scripted`
    (a list of FakeCompleted or Exception instances), one per invocation."""
    calls = []
    seq = list(scripted)

    def fake_run(argv, *args, **kwargs):
        calls.append({"argv": argv, "kwargs": kwargs})
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    fake_run.calls = calls
    return fake_run


# ── Task 1: error shape + argv builders ──────────────────────────────────────

def test_cli_agent_error_has_kind():
    err = C.CliAgentError("timeout", "boom")
    assert err.kind == "timeout"
    assert "boom" in str(err)
    assert isinstance(err, Exception)


def test_build_argv_claude_schema_path():
    argv, stdin = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint='{"type":"object"}',
        structured_json="auto",
    )
    assert argv == ["/bin/claude", "-p", "PROMPT", "--output-format", "json",
                    "--json-schema", '{"type":"object"}']
    assert stdin is None


def test_build_argv_claude_prompt_path_when_no_schema():
    argv, stdin = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint="",
        structured_json="auto",
    )
    assert argv == ["/bin/claude", "-p", "PROMPT", "--output-format", "json"]
    assert stdin is None


def test_build_argv_claude_prompt_mode_forces_no_schema():
    argv, _ = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint='{"x":1}',
        structured_json="prompt",
    )
    assert "--json-schema" not in argv


def test_build_argv_codex_uses_stdin():
    argv, stdin = C._build_argv(
        "codex-cli", "/bin/codex", "PROMPT", schema_hint="", structured_json="auto",
    )
    assert argv == ["/bin/codex", "exec", "--skip-git-repo-check", "-"]
    assert stdin == "PROMPT"


def test_build_argv_gemini():
    argv, stdin = C._build_argv(
        "gemini-cli", "/bin/gemini", "PROMPT", schema_hint="", structured_json="auto",
    )
    assert argv == ["/bin/gemini", "-p", "PROMPT"]
    assert stdin is None


def test_build_argv_unknown_provider_raises_no_cli():
    with pytest.raises(C.CliAgentError) as ei:
        C._build_argv("openrouter", "/bin/x", "P", schema_hint="", structured_json="auto")
    assert ei.value.kind == "no_cli"


# ── Task 2: _run_once spawn + parse + failure classification ──────────────────

def test_run_once_claude_envelope_result_is_json_string(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"type": "result", "result": '{"tasks": [1, 2]}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "claude-code", "/bin/claude", "PROMPT", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=3, timeout=180,
    )
    assert out == {"tasks": [1, 2]}
    # captured argv is the claude prompt path
    assert fake.calls[0]["argv"][:2] == ["/bin/claude", "-p"]


def test_run_once_claude_envelope_result_is_object(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"result": {"tasks": []}})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out == {"tasks": []}


def test_run_once_codex_extract_from_fenced_stdout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    stdout = "Here you go:\n```json\n{\"ok\": true}\n```\n"
    fake = make_runner([FakeCompleted(returncode=0, stdout=stdout)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "codex-cli", "/bin/codex", "P", schema_hint="", structured_json="auto",
        model="gpt-5.2-codex", op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out == {"ok": True}
    # codex carries the prompt on stdin, not argv
    assert fake.calls[0]["kwargs"].get("input") == "P"


def test_run_once_invalid_json_returns_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=0, stdout="totally not json")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "gemini-cli", "/bin/gemini", "P", schema_hint="", structured_json="auto",
        model=None, op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out is None  # signals the caller to do its one parse-retry


def test_run_once_nonzero_exit_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=2, stdout="", stderr="bad flag")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "nonzero_exit"
    assert "bad flag" in str(ei.value)


def test_run_once_timeout_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([subprocess.TimeoutExpired(cmd="claude", timeout=180)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "timeout"


def test_run_once_oserror_raises_spawn_refused(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([OSError("nested spawn refused")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "spawn_refused"


def test_run_once_emits_one_native_cli_telemetry_row(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"result": '{"ok": true}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C._run_once(
        "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=9, timeout=180,
    )
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["backend"] == "native-cli"
    assert rows[0]["exit"] == 0
    assert rows[0]["task_id"] == 9
    assert rows[0]["http_status"] is None
    assert "tokens_in" not in rows[0]


def test_run_once_invalid_json_telemetry_exit_1(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=0, stdout="nope")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C._run_once(
        "gemini-cli", "/bin/gemini", "P", schema_hint="", structured_json="auto",
        model=None, op_class="structured_gen", task_id=None, timeout=180,
    )
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["exit"] == 1
    assert rows[0]["parse_retry"] is False


# ── Task 3: generate_json_via_cli public entry ───────────────────────────────

def test_generate_json_via_cli_happy_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    envelope = json.dumps({"result": '{"tasks": [{"id": 1}]}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C.generate_json_via_cli("claude-code", "Make tasks", task_id=1)
    assert out == {"tasks": [{"id": 1}]}
    assert len(fake.calls) == 1  # one spawn, no retry needed


def test_generate_json_via_cli_no_cli_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: None)
    with pytest.raises(C.CliAgentError) as ei:
        C.generate_json_via_cli("claude-code", "P")
    assert ei.value.kind == "no_cli"


def test_generate_json_via_cli_parse_retry_succeeds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    # First spawn: garbage; second spawn (the one retry): valid.
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="garbage no json"),
        FakeCompleted(returncode=0, stdout='{"ok": true}'),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C.generate_json_via_cli("gemini-cli", "P")
    assert out == {"ok": True}
    assert len(fake.calls) == 2
    # The retry prompt must carry the corrective instruction.
    retry_prompt = fake.calls[1]["argv"][2]  # gemini -p <prompt>
    assert "ONLY the JSON" in retry_prompt


def test_generate_json_via_cli_invalid_json_after_retry_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="nope"),
        FakeCompleted(returncode=0, stdout="still nope"),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C.generate_json_via_cli("gemini-cli", "P")
    assert ei.value.kind == "invalid_json"
    assert len(fake.calls) == 2  # exactly one retry, no third spawn


def test_generate_json_via_cli_schema_hint_appended_to_prompt_when_no_schema_flag(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout='{"ok": 1}')])
    monkeypatch.setattr(C.subprocess, "run", fake)
    # gemini has no schema flag -> schema_hint must be folded into the prompt text.
    C.generate_json_via_cli("gemini-cli", "Base", schema_hint='{"type":"object"}')
    sent_prompt = fake.calls[0]["argv"][2]
    assert "Base" in sent_prompt
    assert '{"type":"object"}' in sent_prompt


def test_generate_json_via_cli_claude_schema_uses_flag_not_prompt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout=json.dumps({"result": "{}"}))])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("claude-code", "Base", schema_hint='{"type":"object"}',
                            structured_json="schema")
    argv = fake.calls[0]["argv"]
    assert "--json-schema" in argv
    # schema goes via the flag, so the prompt slot stays the bare prompt
    assert argv[2] == "Base"


def test_generate_json_via_cli_two_telemetry_rows_on_retry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="bad"),
        FakeCompleted(returncode=0, stdout='{"ok": true}'),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("gemini-cli", "P", task_id=5)
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["exit"] == 1 and rows[0]["parse_retry"] is False
    assert rows[1]["exit"] == 0 and rows[1]["parse_retry"] is True
    assert all(r["backend"] == "native-cli" for r in rows)


# ── Task 4: guardrails ───────────────────────────────────────────────────────

def test_generate_json_via_cli_api_provider_is_no_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # an API/plan provider name must never reach a spawn — it is no_cli.
    monkeypatch.setattr(C.subprocess, "run",
                        lambda *a, **k: pytest.fail("must not spawn for api provider"))
    for provider in ("anthropic", "openai", "perplexity", ""):
        with pytest.raises(C.CliAgentError) as ei:
            C.generate_json_via_cli(provider, "P")
        assert ei.value.kind == "no_cli"


def test_codex_prompt_carried_on_stdin_not_argv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout='{"ok": true}')])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("codex-cli", "SECRET PROMPT", schema_hint='{"x":1}')
    argv = fake.calls[0]["argv"]
    assert "SECRET PROMPT" not in " ".join(argv)        # never on the command line
    assert "SECRET PROMPT" in fake.calls[0]["kwargs"]["input"]  # on stdin
    assert '{"x":1}' in fake.calls[0]["kwargs"]["input"]        # schema folded into stdin
