"""Tournament goose backend tests — no real goose / git / network.

ALL external I/O is injected: _run_goose, _git, _inbox_send, _compute_hash.

Coverage:
  G1.  happy: goose exit 0 → correct command (--provider openrouter --model
       <model> -i <task_file> -q), commit_sha from _git, commit_hash from
       _compute_hash, _inbox_send called with payload
       {job_id, claimant_id, commit_sha, commit_hash}, self_reported_exit==0.
  G2.  missing OPENROUTER_API_KEY (env unset) → ConfigError, goose NOT invoked.
  G2b. empty OPENROUTER_API_KEY → ConfigError, goose NOT invoked.
  G3.  goose nonzero exit → self_reported_exit == that code, no crash.
  G4.  goose OSError → self_reported_exit nonzero, no crash.
  G4b. goose timeout (TimeoutExpired) → self_reported_exit nonzero, no crash.
  G5.  nothing-to-commit (_git committed=False) → fail-closed nonzero,
       no fake commit, no inbox reveal.
  G6.  env passthrough: OPENROUTER_API_KEY reaches the env handed to _run_goose.
  G7.  no hardcoded key-looking literal anywhere in the module source.
  G8.  hash failure → commit_hash "" (fail-closed), still reveals.
  G9.  goose nonzero BUT commit succeeded → self_reported_exit == goose code
       (fail-closed), still reveals the commit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import prd_taskmaster.tournament.goose_backend as gb
from prd_taskmaster.tournament.goose_backend import (
    ConfigError,
    OPENROUTER_API_KEY_ENV,
    run_goose_worker,
)

# ─── Constants ────────────────────────────────────────────────────────────────

TASK_FILE = "/tmp/wt/task.md"
WORKTREE = "/tmp/wt"
MODEL = "openai/gpt-4o-mini"
BASE_REF = "abc1234def"
JOB_ID = "job-goose-1"
CLAIMANT_ID = "job-goose-1:0:openrouter:gpt"
ORCH_SESSION = "orch-session-id"
FAKE_KEY = "sk-or-v1-TESTKEYNOTREAL"

# ─── Stub helpers ─────────────────────────────────────────────────────────────


class GooseRecorder:
    """Records the goose invocation and returns a fixed result."""

    def __init__(self, exit_code: int = 0) -> None:
        self.calls: list[dict] = []
        self._exit_code = exit_code

    def __call__(self, cmd, cwd, env, timeout_s) -> dict:
        self.calls.append(
            {"cmd": cmd, "cwd": cwd, "env": env, "timeout_s": timeout_s}
        )
        return {"exit_code": self._exit_code, "stdout": "ok", "stderr": ""}


class GitRecorder:
    """Records the git call and returns a fixed commit result."""

    def __init__(self, committed: bool = True, commit_sha: str = "deadbeef") -> None:
        self.calls: list[Any] = []
        self._committed = committed
        self._commit_sha = commit_sha

    def __call__(self, worktree_path) -> dict:
        self.calls.append(worktree_path)
        return {"committed": self._committed, "commit_sha": self._commit_sha}


class InboxRecorder:
    """Records inbox_send calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, orchestrator_session, message_type, payload, sender) -> None:
        self.calls.append(
            {
                "orchestrator_session": orchestrator_session,
                "message_type": message_type,
                "payload": payload,
                "sender": sender,
            }
        )


class HashRecorder:
    """Records compute_hash calls and returns a fixed hash."""

    def __init__(self, value: str = "feedf00d") -> None:
        self.calls: list[dict] = []
        self._value = value

    def __call__(self, worktree_path, base_ref, commit_sha) -> str:
        self.calls.append(
            {
                "worktree_path": worktree_path,
                "base_ref": base_ref,
                "commit_sha": commit_sha,
            }
        )
        return self._value


def _set_key(monkeypatch) -> None:
    monkeypatch.setenv(OPENROUTER_API_KEY_ENV, FAKE_KEY)


def _run(**overrides):
    """Invoke run_goose_worker with sensible injected defaults; override as needed."""
    kwargs = dict(
        task_file_path=TASK_FILE,
        worktree_path=WORKTREE,
        model=MODEL,
        base_ref=BASE_REF,
        job_id=JOB_ID,
        claimant_id=CLAIMANT_ID,
        orchestrator_session=ORCH_SESSION,
        _run_goose=GooseRecorder(),
        _git=GitRecorder(),
        _inbox_send=InboxRecorder(),
        _compute_hash=HashRecorder(),
    )
    kwargs.update(overrides)
    return kwargs, run_goose_worker(**kwargs)


# ─── G1: happy path ───────────────────────────────────────────────────────────


def test_happy_command_commit_hash_reveal_and_exit(monkeypatch):
    _set_key(monkeypatch)
    goose = GooseRecorder(exit_code=0)
    git = GitRecorder(committed=True, commit_sha="cafe1234")
    inbox = InboxRecorder()
    hasher = HashRecorder(value="abc123hash")

    result = run_goose_worker(
        task_file_path=TASK_FILE,
        worktree_path=WORKTREE,
        model=MODEL,
        base_ref=BASE_REF,
        job_id=JOB_ID,
        claimant_id=CLAIMANT_ID,
        orchestrator_session=ORCH_SESSION,
        _run_goose=goose,
        _git=git,
        _inbox_send=inbox,
        _compute_hash=hasher,
    )

    # Command correctness.
    assert len(goose.calls) == 1
    cmd = goose.calls[0]["cmd"]
    assert cmd[0] == "goose"
    assert cmd[1] == "run"
    assert "--no-session" in cmd
    # --provider openrouter (adjacent)
    pi = cmd.index("--provider")
    assert cmd[pi + 1] == "openrouter"
    # --model <model> (adjacent)
    mi = cmd.index("--model")
    assert cmd[mi + 1] == MODEL
    # -i <task_file> (adjacent)
    ii = cmd.index("-i")
    assert cmd[ii + 1] == TASK_FILE
    # -q present
    assert "-q" in cmd
    # cwd is the worktree
    assert goose.calls[0]["cwd"] == WORKTREE

    # commit_sha from _git; commit_hash from _compute_hash.
    assert result["commit_sha"] == "cafe1234"
    assert result["commit_hash"] == "abc123hash"
    assert result["claimant_id"] == CLAIMANT_ID
    assert result["self_reported_exit"] == 0

    # _inbox_send called with the exact commit-reveal payload.
    assert len(inbox.calls) == 1
    call = inbox.calls[0]
    assert call["payload"] == {
        "job_id": JOB_ID,
        "claimant_id": CLAIMANT_ID,
        "commit_sha": "cafe1234",
        "commit_hash": "abc123hash",
    }
    assert call["orchestrator_session"] == ORCH_SESSION
    # sender is the claimant
    assert call["sender"] == CLAIMANT_ID

    # hash computed over base_ref..commit_sha
    assert hasher.calls[0]["base_ref"] == BASE_REF
    assert hasher.calls[0]["commit_sha"] == "cafe1234"


# ─── G2: missing / empty key → ConfigError, goose NOT invoked ─────────────────


def test_missing_key_raises_configerror_and_skips_goose(monkeypatch):
    monkeypatch.delenv(OPENROUTER_API_KEY_ENV, raising=False)
    goose = GooseRecorder()
    inbox = InboxRecorder()

    with pytest.raises(ConfigError):
        run_goose_worker(
            task_file_path=TASK_FILE,
            worktree_path=WORKTREE,
            model=MODEL,
            base_ref=BASE_REF,
            job_id=JOB_ID,
            claimant_id=CLAIMANT_ID,
            orchestrator_session=ORCH_SESSION,
            _run_goose=goose,
            _git=GitRecorder(),
            _inbox_send=inbox,
            _compute_hash=HashRecorder(),
        )

    # goose was NEVER invoked, nothing revealed.
    assert goose.calls == []
    assert inbox.calls == []


def test_empty_key_raises_configerror(monkeypatch):
    monkeypatch.setenv(OPENROUTER_API_KEY_ENV, "   ")
    goose = GooseRecorder()
    with pytest.raises(ConfigError):
        run_goose_worker(
            task_file_path=TASK_FILE,
            worktree_path=WORKTREE,
            model=MODEL,
            base_ref=BASE_REF,
            job_id=JOB_ID,
            claimant_id=CLAIMANT_ID,
            orchestrator_session=ORCH_SESSION,
            _run_goose=goose,
            _git=GitRecorder(),
            _inbox_send=InboxRecorder(),
            _compute_hash=HashRecorder(),
        )
    assert goose.calls == []


# ─── G3: goose nonzero exit → self_reported_exit == code ──────────────────────


def test_goose_nonzero_exit_reported(monkeypatch):
    _set_key(monkeypatch)
    # goose failed but produced committable work → exit code surfaces.
    kwargs, result = _run(
        _run_goose=GooseRecorder(exit_code=37),
        _git=GitRecorder(committed=True, commit_sha="abc999"),
    )
    assert result["self_reported_exit"] == 37
    # fail-closed but no crash; commit still revealed (G9 behaviour).
    assert result["commit_sha"] == "abc999"


# ─── G4: goose OSError / timeout → nonzero, no crash ──────────────────────────


def test_goose_oserror_failclosed(monkeypatch):
    _set_key(monkeypatch)

    def boom(cmd, cwd, env, timeout_s):
        raise OSError("goose: command not found")

    # No commit produced (git clean) so the worker fails closed entirely.
    kwargs, result = _run(
        _run_goose=boom,
        _git=GitRecorder(committed=False, commit_sha=""),
    )
    assert result["self_reported_exit"] != 0
    assert result["commit_sha"] == ""


def test_goose_timeout_failclosed(monkeypatch):
    _set_key(monkeypatch)
    import subprocess

    def slow(cmd, cwd, env, timeout_s):
        raise subprocess.TimeoutExpired(cmd, timeout_s)

    kwargs, result = _run(
        _run_goose=slow,
        _git=GitRecorder(committed=False, commit_sha=""),
    )
    assert result["self_reported_exit"] != 0
    assert result["commit_sha"] == ""


# ─── G5: nothing to commit → fail-closed, no fake commit, no reveal ───────────


def test_nothing_to_commit_failclosed(monkeypatch):
    _set_key(monkeypatch)
    inbox = InboxRecorder()
    hasher = HashRecorder()
    kwargs, result = _run(
        _run_goose=GooseRecorder(exit_code=0),
        _git=GitRecorder(committed=False, commit_sha=""),
        _inbox_send=inbox,
        _compute_hash=hasher,
    )
    assert result["commit_sha"] == ""
    assert result["commit_hash"] == ""
    assert result["self_reported_exit"] != 0
    # No fake commit → no hash computed, no reveal.
    assert inbox.calls == []
    assert hasher.calls == []


def test_committed_true_but_no_sha_is_failclosed(monkeypatch):
    _set_key(monkeypatch)
    inbox = InboxRecorder()
    # A bogus git adapter that claims committed but gives no SHA must NOT pass.
    kwargs, result = _run(
        _git=GitRecorder(committed=True, commit_sha=""),
        _inbox_send=inbox,
    )
    assert result["commit_sha"] == ""
    assert result["self_reported_exit"] != 0
    assert inbox.calls == []


# ─── G6: env passthrough ──────────────────────────────────────────────────────


def test_env_passthrough_to_run_goose(monkeypatch):
    _set_key(monkeypatch)
    goose = GooseRecorder(exit_code=0)
    _run(_run_goose=goose)
    assert len(goose.calls) == 1
    env = goose.calls[0]["env"]
    assert OPENROUTER_API_KEY_ENV in env
    assert env[OPENROUTER_API_KEY_ENV] == FAKE_KEY


# ─── G7: no hardcoded key-looking literal in the module source ────────────────


def test_no_hardcoded_key_in_module_source():
    src = Path(gb.__file__).read_text(encoding="utf-8")
    # OpenRouter keys look like "sk-or-..." ; OpenAI like "sk-..." ; generic long
    # base64-ish secrets. None of these may appear as literals in the module.
    forbidden = [
        r"sk-or-[A-Za-z0-9]",          # OpenRouter key prefix
        r"sk-[A-Za-z0-9]{20,}",        # OpenAI-style key
        r"Bearer\s+[A-Za-z0-9]{20,}",  # inline bearer token
    ]
    for pat in forbidden:
        assert re.search(pat, src) is None, f"key-looking literal matched {pat!r}"


# ─── G8: hash failure → commit_hash "" but still reveals ──────────────────────


def test_hash_failure_yields_empty_hash_but_reveals(monkeypatch):
    _set_key(monkeypatch)
    inbox = InboxRecorder()

    def bad_hash(worktree_path, base_ref, commit_sha):
        raise RuntimeError("git diff blew up")

    kwargs, result = _run(
        _run_goose=GooseRecorder(exit_code=0),
        _git=GitRecorder(committed=True, commit_sha="sha-ok"),
        _compute_hash=bad_hash,
        _inbox_send=inbox,
    )
    assert result["commit_sha"] == "sha-ok"
    assert result["commit_hash"] == ""
    assert result["self_reported_exit"] == 0
    # still reveals (commit exists) with empty hash
    assert len(inbox.calls) == 1
    assert inbox.calls[0]["payload"]["commit_hash"] == ""


# ─── G9: goose nonzero but commit landed → exit==code, still reveals ──────────


def test_goose_nonzero_but_commit_landed_reveals_with_code(monkeypatch):
    _set_key(monkeypatch)
    inbox = InboxRecorder()
    kwargs, result = _run(
        _run_goose=GooseRecorder(exit_code=5),
        _git=GitRecorder(committed=True, commit_sha="partial-sha"),
        _inbox_send=inbox,
        _compute_hash=HashRecorder(value="h9"),
    )
    assert result["self_reported_exit"] == 5
    assert result["commit_sha"] == "partial-sha"
    assert result["commit_hash"] == "h9"
    assert len(inbox.calls) == 1


# ─── default inbox adapter must not import launcher at module load ────────────


def test_default_inbox_send_raises_guidance_not_at_import():
    # Module imported fine at top of file (no launcher import). The default
    # adapter raises RuntimeError with guidance only when CALLED.
    with pytest.raises(RuntimeError):
        gb._default_inbox_send(ORCH_SESSION, "commit_reveal", {"x": 1}, CLAIMANT_ID)
