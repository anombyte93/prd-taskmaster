"""Tournament CHEAP racer backend — run a worker via `goose` over OpenRouter.

This is the cheap-API arm of the tournament fleet: a single subtask is handed
to a `goose run` invocation pinned to one OpenRouter model. goose does the work
in an isolated worktree; we commit whatever it produced, compute a reproducible
diff hash, and send a commit-reveal message to the orchestrator inbox.

Architecture note (matches spawn.py / adjudicate.py):
  - All external I/O is injected via default-injectable params:
      _run_goose      — shells the goose subprocess.
      _git            — shells git add/commit in the worktree.
      _compute_hash   — sha256 of `git diff base..commit`.
      _inbox_send     — launcher inbox_send wrapper (NEVER imports the launcher
                        at module load — only inside the default adapter body).
  - Unit tests inject stubs for ALL of these — no live goose / git / network.

Security note:
  - The OpenRouter key comes ONLY from os.environ["OPENROUTER_API_KEY"].
    There is NO hardcoded key anywhere in this module. A missing/empty key
    raises ConfigError BEFORE goose is ever invoked (fail-closed).

Fail-closed everywhere:
  - goose nonzero exit  → still attempt to commit whatever exists, but
                          self_reported_exit = that exit code.
  - goose OSError/timeout → self_reported_exit nonzero, no crash.
  - nothing to commit   → self_reported_exit nonzero, NO fake commit.
  - hash computation failure → "" (never invent a hash).
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

#: Environment variable that carries the OpenRouter API key. NEVER hardcoded.
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

#: Sentinel non-zero exit used when goose never ran or never produced a commit.
_FAILCLOSED_EXIT = 1

# ─── Typed errors ─────────────────────────────────────────────────────────────


class ConfigError(Exception):
    """Raised when required configuration (e.g. the OpenRouter key) is missing.

    This is a fail-closed precondition error — it is raised BEFORE the goose
    subprocess is invoked so no work is ever started with an empty/missing key.
    """


# ─── Default adapters (thin; injected by default; tests override) ─────────────


def _default_run_goose(
    cmd: "list[str]",
    cwd: "str | Path",
    env: "dict[str, str]",
    timeout_s: int,
) -> dict:
    """Default goose runner — shells the subprocess with a hard timeout.

    Returns ``{"exit_code", "stdout", "stderr"}``. Never raises for a nonzero
    exit (that is the caller's fail-closed concern); only the subprocess
    machinery itself (OSError / TimeoutExpired) propagates, and the caller
    catches those to fail closed.
    """
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _default_git(worktree_path: "str | Path") -> dict:
    """Default git committer — `git add -A` then `git commit` in the worktree.

    Returns ``{"committed": bool, "commit_sha": str}``.

    Fail-closed contract:
      - If there is nothing to commit (clean tree after add), returns
        ``{"committed": False, "commit_sha": ""}`` — NO empty/fake commit.
      - Only on a real commit does it return committed=True with the SHA.

    Any git invocation error propagates as a CalledProcessError / OSError and
    is caught by the caller, which fails closed.
    """
    cwd = str(worktree_path)

    subprocess.run(
        ["git", "add", "-A"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )

    # Is there anything staged to commit? `git diff --cached --quiet` exits 1
    # when there ARE staged changes, 0 when the index is clean.
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if staged.returncode == 0:
        # Clean index — nothing to commit. Fail-closed: no fake commit.
        return {"committed": False, "commit_sha": ""}

    subprocess.run(
        ["git", "commit", "-m", "tournament: goose worker result"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return {"committed": True, "commit_sha": head.stdout.strip()}


def _default_compute_hash(
    worktree_path: "str | Path",
    base_ref: str,
    commit_sha: str,
) -> str:
    """Default diff-hash computer — delegates to collect._compute_diff_hash.

    Delegates to :func:`prd_taskmaster.tournament.collect._compute_diff_hash`
    so both the goose racer and the collector/adjudicator use EXACTLY the same
    hashing algorithm — raw-bytes git output, no text-decode, sha256 in-process.
    This is the single source of truth: if the collector algorithm changes, goose
    automatically tracks it, and the two can never diverge.

    The import is done at function scope (not module scope) to avoid a circular
    import — collect imports nothing from goose_backend.

    Fail-closed: any error (bad refs, git failure, import failure) returns ""
    rather than raising — the caller must never invent a hash.
    """
    try:
        from prd_taskmaster.tournament.collect import _compute_diff_hash  # noqa: PLC0415
        return _compute_diff_hash(str(worktree_path), base_ref, commit_sha)
    except Exception:  # noqa: BLE001
        return ""


def _default_inbox_send(
    orchestrator_session: str,
    message_type: str,
    payload: dict,
    sender: str,
) -> Any:
    """Default inbox sender — thin wrapper over the launcher inbox_send tool.

    IMPORTANT: the atlas-launcher MCP is NOT imported at module load. This
    adapter raises with guidance so production code MUST inject a real adapter
    that calls ``mcp__atlas-launcher__inbox_send``. Unit tests inject a stub.

    Intended live mapping::

        mcp__atlas-launcher__inbox_send(
            session_id=orchestrator_session,
            message_type=message_type,          # "commit_reveal"
            payload=json.dumps(payload),        # {job_id, claimant_id, commit_sha, commit_hash}
            sender=sender,                      # claimant_id
        )

    WIRING CONTRACT (read/write symmetry — REQUIRED):
        If the live inbox_send adapter JSON-encodes the payload into a single
        ``payload`` string field (as shown above), the MATCHING live inbox_read
        adapter on the consumer side (collect.collect_tournament) MUST
        ``json.loads`` that string and FLATTEN ``{job_id, claimant_id,
        commit_sha, commit_hash}`` back to TOP-LEVEL keys on each message dict
        before returning. collect._first_commits_by_claimant reads each of these
        as a top-level key (``m["job_id"]`` etc.), so an un-flattened payload
        makes every commit look like ``job_id`` missing — collect silently drops
        it as ``no_commit`` and rejects the racer. Send and read MUST be
        symmetric; cover the round-trip with one integration test that passes a
        real ``commit_reveal`` message through both live adapters.
    """
    raise RuntimeError(
        "_default_inbox_send requires the atlas-launcher MCP to be wired. "
        "Inject a real _inbox_send adapter that calls "
        "mcp__atlas-launcher__inbox_send with:\n"
        f"  session_id={orchestrator_session!r}\n"
        f"  message_type={message_type!r}\n"
        f"  payload=<json of {sorted(payload)!r}>\n"
        f"  sender={sender!r}\n"
        "Pass your adapter as _inbox_send to run_goose_worker()."
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _require_openrouter_key() -> str:
    """Return the OpenRouter key from the environment or raise ConfigError.

    Fail-closed: a missing OR empty/whitespace key raises BEFORE goose runs.
    Never returns a default or hardcoded value.
    """
    key = os.environ.get(OPENROUTER_API_KEY_ENV)
    if not key or not key.strip():
        raise ConfigError(
            f"{OPENROUTER_API_KEY_ENV} is not set (or empty); refusing to run "
            "the goose OpenRouter worker without a key. Set "
            f"{OPENROUTER_API_KEY_ENV} in the environment."
        )
    return key


def _build_goose_cmd(*, model: str, task_file_path: "str | Path") -> "list[str]":
    """Construct the goose run command for the OpenRouter racer.

    ["goose","run","--no-session","--provider","openrouter",
     "--model",model,"-i",task_file_path,"-q"]
    """
    return [
        "goose",
        "run",
        "--no-session",
        "--provider",
        "openrouter",
        "--model",
        model,
        "-i",
        str(task_file_path),
        "-q",
    ]


# ─── Public API ───────────────────────────────────────────────────────────────


def run_goose_worker(
    *,
    task_file_path: "str | Path",
    worktree_path: "str | Path",
    model: str,
    base_ref: str,
    job_id: str,
    claimant_id: str,
    orchestrator_session: str,
    timeout_s: int = 1800,
    _run_goose: "Callable[..., dict]" = _default_run_goose,
    _git: "Callable[..., dict]" = _default_git,
    _inbox_send: "Callable[..., Any]" = _default_inbox_send,
    _compute_hash: "Callable[..., str]" = _default_compute_hash,
) -> dict:
    """Run one cheap OpenRouter racer via goose, commit, hash, and reveal.

    Steps
    -----
    1. Require OPENROUTER_API_KEY from os.environ (ConfigError if missing/empty)
       — goose is NEVER invoked without a key.
    2. Build the goose command and a child env carrying OPENROUTER_API_KEY.
    3. Run goose (injected). OSError/timeout → fail-closed nonzero, no crash.
    4. Commit whatever goose produced (injected _git). Nothing to commit →
       fail-closed nonzero exit, NO fake commit.
    5. Compute the diff hash (injected _compute_hash); fail-closed "".
    6. Send the commit-reveal message to the orchestrator inbox (injected
       _inbox_send) — only when a real commit exists.

    Parameters
    ----------
    task_file_path:
        Path to the task instruction file fed to goose via ``-i``.
    worktree_path:
        Isolated worktree directory; cwd for goose and git.
    model:
        OpenRouter model id (e.g. "openai/gpt-4o-mini").
    base_ref:
        Fork-point commit; the diff hash is over ``base_ref..commit_sha``.
    job_id, claimant_id:
        Tournament identifiers echoed in the commit-reveal payload.
    orchestrator_session:
        Inbox session id the commit-reveal message is sent to.
    timeout_s:
        Hard timeout for the goose subprocess (default 1800s).
    _run_goose, _git, _inbox_send, _compute_hash:
        Injectable adapters (defaults documented above). Tests inject stubs.

    Returns
    -------
    dict with keys::

        {
            "claimant_id": str,
            "commit_sha": str,          # "" if nothing committed
            "commit_hash": str,         # "" if no commit / hash failed
            "self_reported_exit": int,  # 0 only on a clean goose+commit success
        }

    Raises
    ------
    ConfigError
        If OPENROUTER_API_KEY is missing/empty (fail-closed precondition).
    """
    # ── 1. Fail-closed key gate (BEFORE goose runs) ───────────────────────────
    openrouter_key = _require_openrouter_key()

    # ── 2. Build command + child env (key passed through; never hardcoded) ───
    cmd = _build_goose_cmd(model=model, task_file_path=task_file_path)
    env = dict(os.environ)
    env[OPENROUTER_API_KEY_ENV] = openrouter_key

    # ── 3. Run goose — fail-closed on OSError / timeout ──────────────────────
    goose_exit = _FAILCLOSED_EXIT
    try:
        result = _run_goose(cmd, str(worktree_path), env, timeout_s)
        goose_exit = int(result.get("exit_code", _FAILCLOSED_EXIT))
    except Exception:  # noqa: BLE001
        # Deliberately broad: a crashed goose (not found / timeout / a bug in an
        # injected adapter raising KeyError/TypeError) must NEVER abort the
        # worker. We fail closed to _FAILCLOSED_EXIT and still proceed to the
        # commit step in case partial work landed on disk. KeyboardInterrupt /
        # SystemExit are BaseException (not Exception) so Ctrl-C / process exit
        # still propagate. We log the exception (NOT goose stdout/stderr — those
        # may echo the OpenRouter key) so a misbehaving adapter is diagnosable.
        log.warning(
            "goose runner raised; failing closed to exit %d",
            _FAILCLOSED_EXIT,
            exc_info=True,
        )
        goose_exit = _FAILCLOSED_EXIT

    # ── 4. Commit whatever exists — fail-closed, NO fake commit ──────────────
    commit_sha = ""
    committed = False
    try:
        git_result = _git(str(worktree_path))
        committed = bool(git_result.get("committed", False))
        commit_sha = str(git_result.get("commit_sha", "") or "")
        # A "committed" claim with no SHA is treated as no commit (fail-closed).
        if committed and not commit_sha:
            committed = False
    except Exception:  # noqa: BLE001
        committed = False
        commit_sha = ""

    if not committed or not commit_sha:
        # Nothing landed: fail-closed. No commit_sha, no hash, no inbox reveal.
        return {
            "claimant_id": claimant_id,
            "commit_sha": "",
            "commit_hash": "",
            "self_reported_exit": goose_exit if goose_exit != 0 else _FAILCLOSED_EXIT,
        }

    # ── 5. Compute diff hash — fail-closed "" ────────────────────────────────
    try:
        commit_hash = str(_compute_hash(str(worktree_path), base_ref, commit_sha) or "")
    except Exception:  # noqa: BLE001
        commit_hash = ""

    # ── 6. Commit-reveal to the orchestrator inbox ───────────────────────────
    payload = {
        "job_id": job_id,
        "claimant_id": claimant_id,
        "commit_sha": commit_sha,
        "commit_hash": commit_hash,
    }
    try:
        _inbox_send(orchestrator_session, "commit_reveal", payload, claimant_id)
    except Exception:  # noqa: BLE001
        # A failed reveal must not corrupt the worker's own self-report, but it
        # IS a degraded outcome — surface it as a non-zero self_reported_exit so
        # the orchestrator never counts an unrevealed commit as a clean success.
        return {
            "claimant_id": claimant_id,
            "commit_sha": commit_sha,
            "commit_hash": commit_hash,
            "self_reported_exit": goose_exit if goose_exit != 0 else _FAILCLOSED_EXIT,
        }

    return {
        "claimant_id": claimant_id,
        "commit_sha": commit_sha,
        "commit_hash": commit_hash,
        "self_reported_exit": goose_exit,
    }
