"""Tournament orchestration commands: tournament-run + tournament-status.

Wires the full Slice-2A flow:
  spawn → collect → adjudicate → settle → reputation
with anti-sybil slots released in a finally (crash-safe).

Fail-closed contract
--------------------
- roster build failure → raised immediately (no slots to release yet).
- spawn errors per racer → handled inside spawn_roster (spawned=False).
- collect / adjudicate errors → surfaced in summary; slots still released.
- settle ok:false → settle_fail_closed; NO winner written to reputation.
- reputation is recorded ONLY from the TRUSTED settle_env["result"].

All live I/O adapters are injected. Unit tests inject stubs; CLI wires the
documented real defaults (raise-with-guidance until the launcher is connected).

Usage (CLI)::

    prd-taskmaster tournament-run \\
        --card .atlas-ai/cdd/task-7.json \\
        --task 7 \\
        --base-ref abc1234 \\
        --models claude:sonnet,claude:haiku \\
        --job-id job-abc \\
        --bounty 100 \\
        --job-poster molle.atlas@gmail.com \\
        --task-class coding

    prd-taskmaster tournament-status
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from prd_taskmaster.tournament import antisybil
from prd_taskmaster.tournament import adjudicate as _adjudicate_module
from prd_taskmaster.tournament.spawn import build_roster, spawn_roster, default_launcher_adapter
from prd_taskmaster.tournament.collect import (
    collect_tournament,
    default_inbox_adapter,
    default_reveal_adapter,
    FakeClock,
)
from prd_taskmaster.tournament.adjudicate import adjudicate_job, settle_job
from prd_taskmaster.reputation import record_tournament, summarize_reputation, _winner_id


# ─── Core orchestration function ─────────────────────────────────────────────


def run_tournament(
    *,
    card_path: "str | Path",
    task_id: str,
    base_ref: str,
    models: "list[str]",
    job_id: str,
    card_id: str,
    bounty_amount: int,
    job_poster: str,
    job_dir: "str | Path",
    held_root: "str | Path",
    operators_path: "str | Path",
    reputation_path: "str | Path",
    orchestrator_session: str,
    task_class: str,
    task_prompt: str,
    card_ref: str,
    now: str,
    window_s: float = 120.0,
    enforce_slash: bool = False,
    _spawn_fn: "Callable[[Any], dict]" = default_launcher_adapter,
    _inbox_read: "Callable[..., list[dict]]" = default_inbox_adapter,
    _dispatch_reveal: "Callable[..., Optional[dict]]" = default_reveal_adapter,
    _seed_bank: "Optional[Callable[..., None]]" = None,
    _settle: "Optional[Callable[..., dict]]" = None,
    _compute_hash: "Optional[Callable[..., str]]" = None,
    clock=None,
) -> dict:
    """Orchestrate a full tournament job, fail-closed at every step.

    Orchestration order
    -------------------
    1. build_roster     — admission-gated racer list.
    2. spawn_roster     — dispatch each racer; normalize handle shape for collect.
    3. collect_tournament — commit-reveal window; returns verified racers.
    4. _seed_bank       — optional escrow hook (called before settle if provided).
    5. adjudicate_job   — oracle + reachability per verified racer; writes
                          submissions.json + job.json.
    6. settle_job       — shell the TS CLI settle; FAIL-CLOSED on ok:false.
    7. record_tournament — reputation update from TRUSTED result (settle ok only).
    8. antisybil.release — ALWAYS in a finally (crash-safe slot cleanup).

    Parameters
    ----------
    card_path:
        Path to the CDD card JSON for the job.
    task_id:
        Task id string (for reachability sweep inside adjudication).
    base_ref:
        Fork-point commit SHA; all worktrees branch from this.
    models:
        Ordered list of distinct model strings to race (e.g. ["claude:sonnet"]).
    job_id:
        Unique tournament job identifier.
    card_id:
        CDD card identifier embedded in job.json.
    bounty_amount:
        Bounty in coin units.
    job_poster:
        Identity of the bounty poster.
    job_dir:
        Directory where adjudicate writes submissions.json + job.json and where
        the settle CLI is invoked.
    held_root:
        Held root path passed to the oracle gate.
    operators_path:
        Path to operators.json (anti-sybil admission persistence).
    reputation_path:
        Path to the ``.jsonl`` reputation event log.
    orchestrator_session:
        The orchestrator inbox/session used by the real _inbox_read adapter.
    task_class:
        Reputation bucket key (e.g. "coding", "research").
    task_prompt:
        Full task description embedded in each racer's prompt.
    card_ref:
        CDD card reference (embedded in each racer's commit-reveal prompt).
    now:
        ISO-8601 UTC timestamp (injected — no datetime.now() calls).
    window_s:
        Commit-reveal window in seconds (default 120).
    enforce_slash:
        If True, passes --enforce-slash to the settle CLI.
    _spawn_fn:
        Callable(RacerSpec) → dict. Default raises-with-guidance until wired.
    _inbox_read:
        Callable(job_id=) → list[dict]. Default raises-with-guidance.
    _dispatch_reveal:
        Callable(claimant_id=, session_name=, worktree_path=) → dict|None.
    _seed_bank:
        Optional callable(job_dir=, job=, racers=) called before settle.
        Wired live in TT10; None → skip.
    _settle:
        Optional callable(job_dir=, enforce_slash=) → dict.
        Defaults to adjudicate.settle_job.
    _compute_hash:
        Optional callable injected into collect_tournament. None → collect
        uses its own default (which raises-with-guidance in tests unless
        overridden; always inject in unit tests).
    clock:
        Injectable Clock for collect_tournament (tests inject FakeClock).

    Returns
    -------
    Summary dict::

        {
            "job_id": str,
            "roster_size": int,       # racers admitted
            "spawned": int,           # racers successfully spawned
            "collected": int,         # racers that passed commit-reveal
            "rejected": list[dict],   # [{claimant_id, reason}, ...]
            "settled_ok": bool,
            "winner": str | None,     # claimant.id of winner, or None
            "settle_envelope_stage": str | None,  # stage on failure
            "reputation_recorded": bool,
        }
    """
    # Normalise paths.
    job_dir = Path(job_dir)
    operators_path = Path(operators_path)
    reputation_path = Path(reputation_path)

    # Determine the settle callable.
    _settle_fn = _settle if _settle is not None else settle_job

    # ── Summary state ────────────────────────────────────────────────────────
    summary: dict = {
        "job_id": job_id,
        "roster_size": 0,
        "spawned": 0,
        "collected": 0,
        "rejected": [],
        "settled_ok": False,
        "winner": None,
        "settle_envelope_stage": None,
        "reputation_recorded": False,
    }

    # ── Step 1: Build roster (admission-gated) ───────────────────────────────
    # Raises SybilLimitError / ValueError on admission failure — before any
    # slots are held, so the finally has nothing to release. Let it propagate.
    roster = build_roster(
        models=models,
        job_id=job_id,
        task_prompt=task_prompt,
        card_ref=card_ref,
        base_ref=base_ref,
        operators_path=operators_path,
        now=now,
    )
    summary["roster_size"] = len(roster)

    # ── Steps 2–7 inside try/finally (always release slots) ──────────────────
    try:
        # ── Orchestration body — NEVER propagates; any crash → summary ───────
        try:
            # ── Step 2: Spawn roster ─────────────────────────────────────────
            raw_handles = spawn_roster(roster, _spawn_fn=_spawn_fn)

            # Normalize spawn handles: collect_tournament requires
            #   {claimant_id, session_name, worktree_path}
            # spawn_roster emits {claimant_id, session_id, spawned, ...}
            # The live launcher sets session_name=spec.claimant_id when calling
            # session_spawn; we replicate that here as the orchestrator-side mapping.
            normalized_handles: list[dict] = []
            spawned_count = 0
            for raw in raw_handles:
                if not raw.get("spawned", False):
                    # Skip failed spawns — racer won't be in collect either.
                    continue
                handle = dict(raw)
                # Map session_name from session_id (or claimant_id as fallback).
                if "session_name" not in handle:
                    handle["session_name"] = handle.get("session_id") or handle.get("claimant_id", "")
                # worktree_path may be carried from the spawn response or from the spec.
                if "worktree_path" not in handle:
                    handle["worktree_path"] = handle.get("worktree", "")
                normalized_handles.append(handle)
                spawned_count += 1
            summary["spawned"] = spawned_count

            # ── Step 3: Collect (commit-reveal window) ───────────────────────
            # Only racers whose claimant_id appears in the normalized handles are
            # collected; the roster drives the claimant_id index on the other side.
            collect_kwargs: dict = dict(
                job_id=job_id,
                roster=roster,
                handles=normalized_handles,
                base_ref=base_ref,
                orchestrator_session=orchestrator_session,
                window_s=window_s,
                _inbox_read=_inbox_read,
                _dispatch_reveal=_dispatch_reveal,
            )
            if _compute_hash is not None:
                collect_kwargs["_compute_hash"] = _compute_hash
            if clock is not None:
                collect_kwargs["clock"] = clock

            collected = collect_tournament(**collect_kwargs)
            summary["collected"] = len(collected.racers)
            summary["rejected"] = list(collected.rejected)

            # ── I2: Zero collected racers → short-circuit (no adjudicate/settle) ─
            if not collected.racers:
                summary["settle_envelope_stage"] = "no_racers_collected"
                summary["settled_ok"] = False
                return summary

            # ── Step 4: Seed bank (optional, pre-settle escrow hook) ─────────
            if _seed_bank is not None:
                job_meta = {
                    "jobId": job_id,
                    "cardId": card_id,
                    "bountyAmount": bounty_amount,
                    "jobPoster": job_poster,
                }
                _seed_bank(job_dir=job_dir, job=job_meta, racers=collected.racers)

            # ── Step 5: Adjudicate (oracle + reachability gates) ─────────────
            # adjudicate_job is fail-closed per racer; writes submissions.json + job.json.
            adjudicate_job(
                job_dir=job_dir,
                racers=collected.racers,
                card_path=card_path,
                held_root=held_root,
                task_id=task_id,
                start_commit=base_ref,
                job_id=job_id,
                card_id=card_id,
                bounty_amount=bounty_amount,
                job_poster=job_poster,
            )

            # ── Step 6: Settle (FAIL-CLOSED on ok:false) ─────────────────────
            settle_env = _settle_fn(job_dir=job_dir, enforce_slash=enforce_slash)

            settled_ok = settle_env.get("ok") is True
            summary["settled_ok"] = settled_ok
            # Fix 9: default stage to 'settle_failed' on ok:false with missing stage field
            # so the caller can distinguish "never reached settle" from "settle returned failure".
            if settled_ok:
                summary["settle_envelope_stage"] = settle_env.get("stage")
            else:
                summary["settle_envelope_stage"] = settle_env.get("stage") or "settle_failed"

            if not settled_ok:
                # Fail-closed: no winner, no reputation update, slots released below.
                return summary

            # ── Step 7: Record reputation (TRUSTED result only) ──────────────
            # result comes from the TRUSTED settle output — never self-reported.
            trusted_result = settle_env.get("result", {})
            # I3: ALWAYS merge applied into the result passed to record_tournament
            # so _slashed_ids can see real-slash info whether applied is empty or not.
            applied = settle_env.get("applied", {})
            merged_result = dict(trusted_result)
            merged_result["applied"] = applied if isinstance(applied, dict) else {}

            record_tournament(
                reputation_path=reputation_path,
                result=merged_result,
                task_class=task_class,
                now=now,
            )
            # Fix 8: only set reputation_recorded=True when there is a real winner
            # (or participants); a settle with an empty/winner-less result that folds
            # zero rows is not "recorded" in any meaningful sense.
            summary["reputation_recorded"] = _winner_id(merged_result) is not None

            # Extract the winner id from the trusted result for the summary.
            winner = trusted_result.get("winner") if isinstance(trusted_result, dict) else None
            if isinstance(winner, dict):
                claimant = winner.get("claimant")
                if isinstance(claimant, dict):
                    summary["winner"] = claimant.get("id")

        except Exception as exc:  # noqa: BLE001 — I1: never propagate
            summary["settled_ok"] = False
            summary["error"] = str(exc)
            summary["settle_envelope_stage"] = "orchestration_crashed"

    finally:
        # ── Step 8: Release anti-sybil slots (ALWAYS, even on crash) ────────
        # B1: wrapped so a release failure never masks the original exception
        # and never leaks slots (TTL sweep will free them if this raises).
        try:
            antisybil.release(operators_path, job_id=job_id)
        except Exception:  # noqa: BLE001
            pass  # never mask the original error; TTL sweep frees the slot later

    return summary


# ─── CLI wrapper functions ────────────────────────────────────────────────────


def _emit(result: dict) -> None:
    """Emit the result as JSON to stdout and exit with the appropriate code."""
    print(json.dumps(result, indent=2, default=str))
    # M2: exit 0 ONLY on explicit ok:True; anything else (False, missing) → 1.
    sys.exit(0 if result.get("ok") is True else 1)


def cmd_tournament_run(args: argparse.Namespace) -> None:
    """CLI handler for ``tournament-run``.

    Parses CLI args, constructs all paths, and calls run_tournament with the
    documented default adapters (raise-with-guidance until the launcher is wired
    for _spawn_fn/_inbox_read/_dispatch_reveal). _settle defaults to settle_job.

    For production use, a skill/orchestrator wraps run_tournament with real
    session_spawn/inbox adapters. This CLI is the direct-invocation entry point.

    Note: re-running the same job_id re-admits/re-records (no Python-side
    idempotency guard; the TS settle CLI has a settled.json guard on its side).
    """
    models = [m.strip() for m in (args.models or "").split(",") if m.strip()]

    # B2: guard against empty model list (would silently run a no-op tournament).
    if not models:
        _emit({"ok": False, "error": "--models is empty; provide at least one model string"})
        return

    # Derive paths from args with sensible defaults.
    job_id: str = args.job_id
    job_dir = Path(f".atlas-ai/tournament/jobs/{job_id}")
    held_root = Path(".atlas-ai/cdd")
    operators_path = Path(".atlas-ai/tournament/operators.json")
    reputation_path = Path(".atlas-ai/reputation.jsonl")

    # Derive card_id from card path (filename without suffix).
    card_path = Path(args.card)
    card_id = card_path.stem

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        summary = run_tournament(
            card_path=card_path,
            task_id=args.task,
            base_ref=args.base_ref,
            models=models,
            job_id=job_id,
            card_id=card_id,
            bounty_amount=int(args.bounty),
            job_poster=args.job_poster,
            job_dir=job_dir,
            held_root=held_root,
            operators_path=operators_path,
            reputation_path=reputation_path,
            orchestrator_session="",
            task_class=getattr(args, "task_class", "coding"),
            task_prompt=f"Tournament task for card {card_id} (task {args.task})",
            card_ref=card_id,
            now=now,
            window_s=float(getattr(args, "window", 120.0)),
            enforce_slash=bool(getattr(args, "enforce_slash", False)),
            # Real adapters must be wired by the orchestrator skill; the defaults
            # raise RuntimeError with guidance if called directly.
            _spawn_fn=default_launcher_adapter,
            _inbox_read=default_inbox_adapter,
            _dispatch_reveal=default_reveal_adapter,
        )
        _emit({"ok": True, **summary})
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": str(exc)})


def cmd_tournament_status(args: argparse.Namespace) -> None:
    """CLI handler for ``tournament-status``.

    Reads the folded reputation snapshot + active operator count and emits JSON.
    """
    reputation_path = Path(getattr(args, "reputation_path", None) or ".atlas-ai/reputation.jsonl")
    operators_path = Path(getattr(args, "operators_path", None) or ".atlas-ai/tournament/operators.json")

    reputation = summarize_reputation(reputation_path)

    # Count active operator slots.
    active_operators = 0
    if operators_path.is_file():
        try:
            import json as _json
            state = _json.loads(operators_path.read_text())
            active_operators = sum(
                1 for e in state.get("entries", [])
                if e.get("active", False)
            )
        except Exception:  # noqa: BLE001
            active_operators = 0

    # Serialise the reputation dict (tuple keys → string).
    rep_serialized = {
        f"{executor_id}|{tc}": stats
        for (executor_id, tc), stats in reputation.items()
    }

    _emit({
        "ok": True,
        "reputation": rep_serialized,
        "active_operators": active_operators,
    })
