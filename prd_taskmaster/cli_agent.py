"""Keyless CLI-agent structured-JSON provider (sub-project #1, Chunk 2).

The structured-JSON twin of llm_client.generate_json(): instead of an HTTP call
against a raw API key, it shells out to a host model CLI (claude / codex / gemini)
using that CLI's own session auth — free, no API key, runs N-parallel inside the
existing NativeBackend ThreadPoolExecutor exactly like N concurrent HTTP calls.

Reuses llm_client._extract_json verbatim and mirrors generate_json's ONE
parse-retry. Emits one telemetry row per spawn attempt with backend="native-cli".
"""

import shutil
import subprocess
import time

from prd_taskmaster.economy import append_telemetry
from prd_taskmaster.llm_client import _extract_json

# provider -> CLI binary name (mirrors providers._SPAWN_PROBE_CLI; kept local to
# avoid a hard import cycle and because cli_agent must run even if probe is stubbed).
_CLI_FOR_PROVIDER = {"claude-code": "claude", "codex-cli": "codex", "gemini-cli": "gemini"}

_RETRY_INSTRUCTION = (
    "\nYour previous output failed json.loads. Return ONLY the JSON, no prose, no fences."
)


class CliAgentError(Exception):
    """kind in {"no_cli", "spawn_refused", "timeout", "invalid_json", "nonzero_exit"}."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _build_argv(provider, binary, prompt, *, schema_hint, structured_json):
    """Return (argv, stdin_text). stdin_text is None unless the CLI takes the
    prompt on stdin (codex). Raises CliAgentError('no_cli') for unknown providers."""
    p = str(provider or "").lower()
    if p == "claude-code":
        argv = [binary, "-p", prompt, "--output-format", "json"]
        # Schema path: only when a schema is supplied AND prompt-mode not forced.
        if schema_hint and structured_json != "prompt":
            argv += ["--json-schema", schema_hint]
        return argv, None
    if p == "codex-cli":
        return [binary, "exec", "--skip-git-repo-check", "-"], prompt
    if p == "gemini-cli":
        return [binary, "-p", prompt], None
    raise CliAgentError("no_cli", f"provider {provider!r} is not a spawning CLI agent")


def _telemetry(op_class, task_id, model, exit_code, start, parse_retry):
    """One native-cli telemetry row. Mirrors llm_client._telemetry minus usage
    tokens (the CLIs do not surface token counts) and http_status (None)."""
    from datetime import datetime, timezone

    return append_telemetry({
        "ts": datetime.now(timezone.utc).isoformat(),
        "op_class": op_class,
        "task_id": task_id,
        "model": model,
        "backend": "native-cli",
        "exit": exit_code,
        "wall_ms": int((time.monotonic() - start) * 1000),
        "escalated": False,
        "parse_retry": parse_retry,
        "http_status": None,
    })


def _parse_claude_envelope(stdout):
    """claude --output-format json prints a JSON envelope; the model answer is in
    `.result` (a JSON string when --json-schema was used, else free text). Funnel
    `.result` through _extract_json so a stringified-JSON result is normalized.
    Return parsed JSON, or None to signal a parse failure (one retry upstream)."""
    envelope = _extract_json(stdout)
    if isinstance(envelope, dict) and "result" in envelope:
        result = envelope["result"]
        if isinstance(result, (dict, list)):
            return result
        if isinstance(result, str):
            return _extract_json(result)
        return None
    # No envelope (or non-dict): treat the whole stdout as the payload.
    return envelope


def _claude_error_detail(stdout, stderr):
    """For a claude-code nonzero exit, prefer the error reason from the JSON
    envelope in stdout (which carries the real cause in .result / api_error_status)
    over stderr (which may only hold benign warnings like 'no stdin data received').
    Falls back to stderr, then stdout, then a generic message."""
    import json as _json
    if stdout:
        try:
            envelope = _json.loads(stdout.strip())
            if isinstance(envelope, dict) and envelope.get("is_error"):
                parts = []
                result_text = envelope.get("result", "")
                if result_text:
                    parts.append(str(result_text))
                status = envelope.get("api_error_status")
                if status:
                    parts.append(f"api_error_status={status}")
                if parts:
                    return "; ".join(parts)[:400]
        except (_json.JSONDecodeError, ValueError):
            pass
    return (stderr or stdout or "no detail").strip()[:400]


def _run_once(provider, binary, prompt, *, schema_hint, structured_json,
              model, op_class, task_id, timeout, parse_retry=False):
    """Spawn the CLI once, parse stdout into JSON. Returns the parsed dict/list,
    or None on a parse failure (caller decides whether to retry). Raises
    CliAgentError for timeout / nonzero_exit / spawn_refused. Emits exactly one
    native-cli telemetry row for this attempt."""
    argv, stdin_text = _build_argv(
        provider, binary, prompt, schema_hint=schema_hint, structured_json=structured_json,
    )
    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        raise CliAgentError("timeout", f"{binary} exceeded {timeout}s timeout")
    except OSError as exc:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        raise CliAgentError("spawn_refused", f"{binary} could not spawn: {exc}")

    if completed.returncode != 0:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        if _has_schema_flag(provider):
            detail = _claude_error_detail(completed.stdout, completed.stderr)
        else:
            detail = (completed.stderr or completed.stdout or "").strip()[:400]
        raise CliAgentError("nonzero_exit", f"{binary} exit {completed.returncode}: {detail}")

    if _has_schema_flag(provider):
        result = _parse_claude_envelope(completed.stdout)
    else:
        result = _extract_json(completed.stdout)

    _telemetry(op_class, task_id, model, 0 if result is not None else 1, start, parse_retry)
    return result


def _has_schema_flag(provider):
    """Only claude exposes a native --json-schema flag today; codex/gemini fold
    the schema into the prompt text."""
    return str(provider or "").lower() == "claude-code"


def generate_json_via_cli(provider, prompt, *, system="", schema_hint="", model=None,
                          op_class="structured_gen", task_id=None, timeout=180,
                          structured_json="auto"):
    """Structured-JSON generation by shelling out to a keyless host CLI.

    Mirrors llm_client.generate_json: builds the full prompt (system + schema for
    CLIs without a schema flag), spawns once, and on a parse failure respawns ONCE
    with the corrective instruction. Raises CliAgentError(kind, message) with
    kind in {no_cli, spawn_refused, timeout, invalid_json, nonzero_exit}. One
    telemetry row (backend=native-cli) per spawn attempt.
    """
    cli = _CLI_FOR_PROVIDER.get(str(provider or "").lower())
    if not cli:
        raise CliAgentError("no_cli", f"provider {provider!r} is not a spawning CLI agent")
    binary = shutil.which(cli)
    if not binary:
        raise CliAgentError("no_cli", f"{cli} binary not on PATH")

    # Assemble the prompt the model sees. The CLI takes no separate system slot,
    # so prepend system. Fold the schema into the prompt for codex/gemini (no
    # native schema flag) or when prompt-mode is forced for claude. For claude,
    # ALWAYS include a terse JSON-only directive even when --json-schema is used
    # (belt-and-suspenders: claude v2.1.177+ still requires the prompt directive
    # to reliably return JSON in .result rather than prose).
    base_prompt = prompt
    if system:
        base_prompt = system + "\n\n" + base_prompt
    use_schema_flag = _has_schema_flag(provider) and structured_json != "prompt"
    if schema_hint:
        # For codex/gemini, folding the schema into the prompt is the only path.
        # For claude, ALWAYS include a terse JSON-only directive even when
        # --json-schema is also passed (belt-and-suspenders: claude v2.1.177+
        # still requires the prompt directive to reliably return JSON in .result).
        base_prompt += "\n\nReturn ONLY valid JSON matching:\n" + schema_hint

    flag_schema = schema_hint if use_schema_flag else ""

    attempt_prompt = base_prompt
    parse_retry = False
    while True:
        result = _run_once(
            provider, binary, attempt_prompt,
            schema_hint=flag_schema, structured_json=structured_json,
            model=model, op_class=op_class, task_id=task_id, timeout=timeout,
            parse_retry=parse_retry,
        )
        if result is not None:
            return result
        if parse_retry:
            raise CliAgentError("invalid_json", "CLI output failed JSON parsing after one retry")
        parse_retry = True
        attempt_prompt = base_prompt + _RETRY_INSTRUCTION
