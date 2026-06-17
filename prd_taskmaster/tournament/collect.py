"""Tournament commit-reveal collector with a quality-gated window.

This is the security core of the tournament: it defeats the *diff-copy attack*.

Background
----------
Racers spawned by :mod:`prd_taskmaster.tournament.spawn` work in isolated
worktrees. The protocol is **commit-reveal**:

  1. **COMMIT phase** — each racer commits its work, computes
     ``commit_hash = sha256(git diff base_ref..HEAD)`` and reports
     ``{job_id, claimant_id, commit_sha, commit_hash}`` to the orchestrator
     inbox. At this point only the *hash* is public, not the diff.
  2. **REVEAL phase** — the collector asks each committed session to reveal
     ``{claimant_id, worktree_path, commit_sha, self_reported_exit}``.
  3. **ANTI DIFF-COPY VERIFY** — the collector independently recomputes
     ``sha256(git diff base_ref..commit_sha)`` at the racer's worktree. A racer
     that copied a peer's diff *after* the reveal cannot match the hash it
     committed *earlier* (it would have to predict the peer's diff in advance).
     Any racer whose recomputed hash != its committed hash is **rejected**.

Design constraints
------------------
- **All external I/O is injected** (inbox read, reveal dispatch, hash compute,
  clock). The defaults raise-with-guidance and never import the launcher at
  module load, mirroring :mod:`prd_taskmaster.tournament.spawn` and
  :mod:`prd_taskmaster.tournament.adjudicate`.
- **Deterministic / pure where possible** — time comes from an injected
  :class:`Clock`; logic uses no ``random`` or wall-clock reads.
- **Fail-closed everywhere** — a git error yields an empty hash, which can
  never match a committed hash, so the racer is rejected rather than admitted.

The returned racer dicts match exactly the shape consumed by
:func:`prd_taskmaster.tournament.adjudicate.adjudicate_submission`:
``claimant_id, commit_sha, worktree_path, self_reported_exit, commit_hash,
revealed_at, entry_fee_paid, fakery_stake``.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Reasons a racer may be rejected (kept narrow + documented for the caller).
REJECT_NO_COMMIT = "no_commit"
REJECT_NO_REVEAL = "no_reveal"
REJECT_HASH_MISMATCH = "hash_mismatch"
REJECT_TIMEOUT = "timeout"

# Default per-git-call timeout (seconds) for the diff-hash recompute.
_GIT_TIMEOUT_S = 30

# Smallest per-iteration clock advance for the commit window. The
# window-cannot-hang guarantee requires the loop to make strictly-monotonic
# progress toward the deadline on every sleep. A degenerate poll_interval_s<=0
# would otherwise advance time by 0 (FakeClock) or never (RealClock.monotonic),
# spinning forever. Flooring the advance to this positive minimum keeps "never
# sleep past the deadline" while guaranteeing termination.
_MIN_POLL_S = 0.001


# ─── Clock abstraction ────────────────────────────────────────────────────────


class Clock:
    """Monotonic clock + sleep abstraction.

    The collector reads time and sleeps ONLY through a Clock so unit tests can
    inject a :class:`FakeClock` that fast-forwards without any real waiting.
    """

    def now(self) -> float:  # pragma: no cover - interface
        raise NotImplementedError

    def sleep(self, seconds: float) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class RealClock(Clock):
    """Production clock backed by ``time.monotonic`` + ``time.sleep``."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock(Clock):
    """Deterministic clock for tests — sleep() advances a virtual monotonic
    clock WITHOUT any real wall-clock wait. Records every sleep duration so a
    test can prove the loop slept (rather than spun) and never blocked.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        # Virtual time only — no real waiting ever happens.
        self.sleeps.append(seconds)
        self._t += float(seconds)


# ─── Diff-hash recompute (fail-closed) ────────────────────────────────────────


def _compute_diff_hash(
    worktree: str,
    base_ref: str,
    commit_sha: str,
    *,
    _run: "Callable[..., Any]" = subprocess.run,
    timeout_s: int = _GIT_TIMEOUT_S,
) -> str:
    """Recompute ``sha256(git diff base_ref..commit_sha)`` at ``worktree``.

    Equivalent to ``git -C <worktree> diff <base_ref>..<commit_sha> | sha256sum``
    but the hashing is done in-process for determinism.

    Fail-closed contract
    --------------------
    On ANY failure (git missing, non-zero exit, timeout, decode error) this
    returns ``""``. An empty string can never equal a committed 64-hex hash, so
    a failed recompute deterministically REJECTS the racer rather than letting
    an unverifiable submission through.

    Parameters
    ----------
    worktree:
        Path to the racer's worktree (``git -C`` target).
    base_ref:
        Fork-point commit the diff is measured from.
    commit_sha:
        The racer's committed SHA (the end of the diff range).
    _run:
        Injectable subprocess runner (default ``subprocess.run``). Tests inject
        a stub so no real git is invoked.
    timeout_s:
        Per-call timeout passed to the runner.
    """
    cmd = ["git", "-C", str(worktree), "diff", f"{base_ref}..{commit_sha}"]
    try:
        proc = _run(
            cmd,
            capture_output=True,
            timeout=timeout_s,
        )
    except Exception:  # noqa: BLE001 - fail-closed on ANY launch/timeout error
        return ""

    # Fail-closed on non-zero git exit.
    if getattr(proc, "returncode", 1) != 0:
        return ""

    out = getattr(proc, "stdout", b"")
    if out is None:
        return ""
    if isinstance(out, str):
        out = out.encode("utf-8", errors="surrogateescape")

    try:
        return hashlib.sha256(out).hexdigest()
    except Exception:  # noqa: BLE001 - fail-closed
        return ""


# ─── Result type ─────────────────────────────────────────────────────────────


@dataclass
class CollectResult:
    """Outcome of a collection round.

    Attributes
    ----------
    racers:
        Verified racer dicts in the EXACT shape ``adjudicate_submission``
        consumes. Safe to hand straight to ``adjudicate_job``.
    rejected:
        One ``{"claimant_id": str, "reason": str}`` per rejected racer, where
        ``reason`` is one of ``no_commit``, ``no_reveal``, ``hash_mismatch``,
        ``timeout``.
    """

    racers: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


# ─── Default reveal adapter (no launcher import at module load) ───────────────


def default_reveal_adapter(
    *,
    claimant_id: str,
    session_name: str,
    worktree_path: str,
) -> "Optional[dict]":
    """Thin documented wrapper showing the intended reveal dispatch.

    Documents the live wiring from a committed handle → a reveal request without
    importing or calling the launcher MCP at module load. Call it only when the
    atlas-launcher MCP is available (inside an orchestrator skill, not in tests).

    Intended mapping::

        # ask the racer's session to reveal its end-state, then read the reply
        session_prompt_dispatch(
            session_name=session_name,
            prompt="REVEAL: report {claimant_id, worktree_path, commit_sha, exit}",
        )
        reply = session_read_messages(session_name=session_name)
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": <reply.commit_sha>,
            "self_reported_exit": <reply.exit>,
        }

    Returns
    -------
    A reveal dict, or ``None`` if the session did not reveal.

    Raises
    ------
    RuntimeError
        Always — this adapter requires the atlas-launcher MCP to be wired.
        Pass your real adapter as ``_dispatch_reveal`` to ``collect_tournament``.
    """
    raise RuntimeError(
        "default_reveal_adapter requires the atlas-launcher MCP to be available. "
        "Wire a real adapter that prompts the racer session for its reveal and "
        "returns {claimant_id, worktree_path, commit_sha, self_reported_exit} "
        "(or None if no reveal). "
        f"claimant_id={claimant_id!r} session_name={session_name!r} "
        f"worktree_path={worktree_path!r}. "
        "Pass your adapter as _dispatch_reveal to collect_tournament()."
    )


def default_inbox_adapter(*, job_id: str) -> "list[dict]":
    """Documented default for the inbox reader — raises with guidance.

    Intended mapping::

        msgs = inbox_read(box=orchestrator_session)
        return [m for m in msgs if m.get("job_id") == job_id]

    Raises
    ------
    RuntimeError
        Always — requires the atlas-launcher MCP. Pass a real ``_inbox_read``.
    """
    raise RuntimeError(
        "default_inbox_adapter requires the atlas-launcher MCP. Wire a real "
        "_inbox_read that returns the orchestrator inbox messages whose "
        f"job_id == {job_id!r}. Pass it as _inbox_read to collect_tournament()."
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _first_commits_by_claimant(
    messages: "list[dict]",
    *,
    job_id: str,
    roster_ids: "set[str]",
    acc: "dict[str, dict]",
) -> None:
    """Merge new commit messages into ``acc`` — FIRST commit per claimant wins.

    Mutates ``acc`` in place (claimant_id -> commit message dict). Messages for
    the wrong job, for claimants not on the roster, or duplicates for a claimant
    already recorded are ignored. Malformed (non-dict / missing keys) messages
    are skipped, never raised.
    """
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("job_id", "")) != job_id:
            continue
        cid = msg.get("claimant_id")
        if cid is None:
            continue
        cid = str(cid)
        if cid not in roster_ids:
            continue
        if cid in acc:
            # First commit wins — ignore duplicate / late messages.
            continue
        commit_sha = msg.get("commit_sha")
        commit_hash = msg.get("commit_hash")
        if not commit_sha or commit_hash is None:
            # Incomplete commit report — wait for a complete one.
            continue
        acc[cid] = {
            "claimant_id": cid,
            "commit_sha": str(commit_sha),
            "commit_hash": str(commit_hash),
        }


# ─── Public API ───────────────────────────────────────────────────────────────


def collect_tournament(
    *,
    job_id: str,
    roster: "list[Any]",
    handles: "list[dict]",
    base_ref: str,
    orchestrator_session: str,
    window_s: float = 120.0,
    poll_interval_s: float = 2.0,
    _inbox_read: "Callable[..., list[dict]]" = default_inbox_adapter,
    _dispatch_reveal: "Callable[..., Optional[dict]]" = default_reveal_adapter,
    _compute_hash: "Callable[..., str]" = _compute_diff_hash,
    clock: "Optional[Clock]" = None,
) -> CollectResult:
    """Run the commit-reveal collection for one tournament job.

    Phases
    ------
    1. **COMMIT** — poll ``_inbox_read(job_id=...)`` until every roster claimant
       has reported a commit OR the quality-gated window ``window_s`` elapses.
       The loop sleeps ``poll_interval_s`` between polls via the injected
       ``clock`` (a FakeClock fast-forwards with no real wait, proving the loop
       always terminates).
    2. **REVEAL** — for each committed claimant, call ``_dispatch_reveal`` to get
       ``{claimant_id, worktree_path, commit_sha, self_reported_exit}``. A racer
       that never reveals is rejected ``no_reveal``.
    3. **ANTI DIFF-COPY VERIFY** — recompute the diff hash at the revealed
       worktree via ``_compute_hash`` and REJECT (``hash_mismatch``) any racer
       whose recomputed hash != its committed hash. ``_compute_hash`` is
       fail-closed: a git error yields ``""`` which never matches.

    Parameters
    ----------
    job_id:
        Tournament job identifier; inbox messages are matched on this.
    roster:
        List of ``RacerSpec`` (from ``spawn.build_roster``). Each carries
        ``claimant_id``, ``entry_fee_paid`` and ``fakery_stake``, which are
        passed through to the racer dict for settlement.
    handles:
        Spawn handles, one per spawned racer. Each MUST be a dict carrying at
        minimum::

            {"claimant_id": str, "session_name": str, "worktree_path": str}

        - ``claimant_id`` keys the handle to its roster spec.
        - ``session_name`` addresses the reveal dispatch (the racer's session).
        - ``worktree_path`` is the orchestrator-controlled checkout the racer
          worked in; it is the source of truth for the anti-diff-copy recompute
          (see the reveal phase below).

        **Handle-shape reconciliation with spawn:**
        :func:`prd_taskmaster.tournament.spawn.spawn_roster` documents the raw
        spawn handle as ``{claimant_id, session_id, ...}`` (the launcher returns
        a ``session_id``) and sets ``session_name=spec.claimant_id`` when it
        calls ``session_spawn``. The integrating orchestrator MUST normalise the
        spawn handle into the shape above before passing it here — i.e. map the
        spawned session to ``session_name`` and attach the racer's
        ``worktree_path`` — so the keys collect reads match the keys spawn
        produced. Handles missing ``session_name``/``worktree_path`` degrade
        fail-closed (empty session/worktree → reveal/recompute reject), never
        crash.
    base_ref:
        Fork-point commit; the diff range is ``base_ref..commit_sha``.
    orchestrator_session:
        The orchestrator inbox/session the racers reported to (passed through to
        a real ``_inbox_read`` adapter; unused by the injected test stubs).
    window_s:
        Quality-gated commit window in seconds (default 120). Once elapsed,
        un-committed roster claimants are rejected.
    poll_interval_s:
        Seconds to sleep between inbox polls (default 2).
    _inbox_read, _dispatch_reveal, _compute_hash:
        Injectable I/O. Defaults raise-with-guidance / are fail-closed and never
        import the launcher at module load.
    clock:
        Injectable :class:`Clock`. Defaults to :class:`RealClock`. Tests inject
        a :class:`FakeClock`.

    Returns
    -------
    CollectResult — verified ``racers`` (adjudicate shape) + ``rejected`` list.
    """
    if clock is None:
        clock = RealClock()

    # Index roster + handles by claimant_id. Only claimants present in BOTH the
    # roster and the handles can be collected (we need fees AND a worktree).
    roster_by_id: dict[str, Any] = {}
    for spec in roster:
        cid = getattr(spec, "claimant_id", None)
        if cid is None and isinstance(spec, dict):
            cid = spec.get("claimant_id")
        if cid is not None:
            roster_by_id[str(cid)] = spec

    handle_by_id: dict[str, dict] = {}
    for h in handles or []:
        if isinstance(h, dict) and h.get("claimant_id") is not None:
            handle_by_id[str(h["claimant_id"])] = h

    roster_ids = set(roster_by_id)

    result = CollectResult()

    # ── Phase 1: COMMIT — poll until all committed or the window elapses ──────
    committed: dict[str, dict] = {}
    deadline = clock.now() + float(window_s)

    while True:
        try:
            messages = _inbox_read(job_id=job_id)
        except Exception:  # noqa: BLE001 - a flaky read must not abort the job
            messages = []
        _first_commits_by_claimant(
            messages,
            job_id=job_id,
            roster_ids=roster_ids,
            acc=committed,
        )

        # All roster claimants reported → stop early.
        if roster_ids and roster_ids.issubset(committed.keys()):
            break

        # Window elapsed → stop. (We re-poll once before sleeping above, so the
        # final pre-deadline messages are captured.)
        if clock.now() >= deadline:
            break

        # Sleep one interval — but never sleep past the deadline. The FakeClock
        # advances virtual time here without any real wait, guaranteeing the
        # loop terminates. The advance is floored to a positive minimum so a
        # degenerate poll_interval_s<=0 cannot stall progress to the deadline
        # (the clock must strictly approach `deadline` every iteration). We
        # still never overshoot: when the remaining window is below that floor
        # we sleep exactly the remaining amount, which lands us on the deadline.
        remaining = deadline - clock.now()
        if remaining <= 0:
            break
        step = float(poll_interval_s)
        if step < _MIN_POLL_S:
            step = _MIN_POLL_S
        if step > remaining:
            step = remaining
        clock.sleep(step)

    # Roster claimants that never committed within the window → rejected.
    for cid in roster_ids:
        if cid not in committed:
            result.rejected.append({"claimant_id": cid, "reason": REJECT_NO_COMMIT})

    # ── Phases 2+3: REVEAL then ANTI DIFF-COPY VERIFY ────────────────────────
    # Deterministic order: roster order, then any committed extras.
    ordered_ids = [cid for cid in roster_by_id if cid in committed]
    for cid in committed:
        if cid not in ordered_ids:
            ordered_ids.append(cid)

    for cid in ordered_ids:
        commit = committed[cid]
        handle = handle_by_id.get(cid, {})
        session_name = handle.get("session_name", "")
        handle_worktree = handle.get("worktree_path", "")

        # Phase 2: REVEAL.
        try:
            reveal = _dispatch_reveal(
                claimant_id=cid,
                session_name=session_name,
                worktree_path=handle_worktree,
            )
        except Exception:  # noqa: BLE001 - a dead session is a no_reveal, not a crash
            reveal = None

        if not reveal or not isinstance(reveal, dict):
            result.rejected.append({"claimant_id": cid, "reason": REJECT_NO_REVEAL})
            continue

        # Trust the racer's COMMITTED sha (bound to its committed hash), not a
        # reveal-time sha it could swap.
        commit_sha = commit["commit_sha"]
        committed_hash = commit["commit_hash"]

        # SECURITY: the recompute path is the ORCHESTRATOR-controlled spawn-handle
        # worktree, NOT the racer-supplied reveal path. Defense-in-depth: a racer
        # must not be able to steer the verifier at a path it controls. We only
        # fall back to the reveal's worktree_path when the handle omits one (e.g.
        # a handle that wasn't fully normalised), and even then the recompute is
        # fail-closed (a wrong/empty path → git error → empty hash → reject).
        recompute_worktree = handle_worktree or reveal.get("worktree_path", "")
        # The reveal path is retained only for provenance/result reporting.
        reported_worktree = recompute_worktree

        # Phase 3: ANTI DIFF-COPY VERIFY (the security core).
        recomputed = _compute_hash(recompute_worktree, base_ref, commit_sha)
        if not recomputed or recomputed != committed_hash:
            # Fail-closed: empty hash (git error) or a copied diff → reject.
            result.rejected.append({"claimant_id": cid, "reason": REJECT_HASH_MISMATCH})
            continue

        # Pass fees through from the roster spec (fail-closed to 0 if absent).
        spec = roster_by_id[cid]
        entry_fee_paid = getattr(spec, "entry_fee_paid", None)
        fakery_stake = getattr(spec, "fakery_stake", None)
        if entry_fee_paid is None and isinstance(spec, dict):
            entry_fee_paid = spec.get("entry_fee_paid")
        if fakery_stake is None and isinstance(spec, dict):
            fakery_stake = spec.get("fakery_stake")

        result.racers.append(
            {
                "claimant_id": cid,
                "commit_sha": commit_sha,
                "worktree_path": reported_worktree,
                "self_reported_exit": reveal.get("self_reported_exit"),
                "commit_hash": committed_hash,
                # revealedAt marker — deterministic, no wall-clock read; the
                # adjudicator only needs a non-empty provenance string.
                "revealed_at": f"job:{job_id}:claimant:{cid}",
                "entry_fee_paid": entry_fee_paid if entry_fee_paid is not None else 0,
                "fakery_stake": fakery_stake if fakery_stake is not None else 0,
            }
        )

    return result
