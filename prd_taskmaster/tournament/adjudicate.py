"""Tournament adjudicator: run oracle + reachability gates per racer submission.

Produces trusted Submission dicts matching the TS atlas-protocol spine, writes
submissions.json + job.json, and shells `atlas tournament settle`.

Fail-closed: a bad card or sweep means FAIL/ERROR for THAT submission only —
the job is never aborted and a bad racer never gets a false PASS.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from prd_taskmaster.lib import atomic_write
from prd_taskmaster.oracle_bridge import OracleCardError, grade_card
from prd_taskmaster.reachability_cmd import run_reachability_sweep


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _str(value: Any, default: str = "") -> str:
    """Return str(value) or default if value is None/missing."""
    if value is None:
        return default
    return str(value)


def _int_or_none(value: Any) -> "int | None":
    """Return int(value) if coercible, else None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tournament_cmd() -> list[str]:
    """Configurable CLI invocation for atlas tournament settle.

    Override with ATLAS_TOURNAMENT_CMD (shell-split), e.g.:
        ATLAS_TOURNAMENT_CMD="node /path/to/atlas-protocol/apps/cli/dist/index.js"
    """
    raw = os.environ.get("ATLAS_TOURNAMENT_CMD")
    if raw:
        return shlex.split(raw)
    return ["atlas"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def adjudicate_submission(
    racer: dict,
    *,
    card_path: "str | Path",
    held_root: "str | Path",
    job_dir: "str | Path",
    task_id: str,
    start_commit: str,
    oracle_cmd: "list[str] | None" = None,
    _grade=grade_card,
    _sweep=run_reachability_sweep,
) -> dict:
    """Run both gates for a single racer and return a trusted Submission dict.

    Parameters
    ----------
    racer:
        Dict with keys:
            claimant_id, commit_sha, worktree_path,
            self_reported_exit, commit_hash, revealed_at,
            entry_fee_paid, fakery_stake
    card_path:
        Path to the CDD card JSON (shared across all racers in a job).
    held_root:
        Held root passed to the oracle gate.
    job_dir:
        Base directory for this job. Evidence is written to
        <job_dir>/evidence/<claimant_id>/ and ledger to <job_dir>/ledger/.
    task_id:
        The task ID string for the reachability sweep.
    start_commit:
        The commit SHA recorded when work on the task began.
    oracle_cmd:
        Optional explicit oracle command. Falls back to ATLAS_ORACLE_CMD env / 'atlas'.
    _grade, _sweep:
        Injectable for testing — defaults to the real gate functions.

    Returns
    -------
    A dict matching the TS Submission shape exactly.
    """
    job_dir = Path(job_dir)
    claimant_id = str(racer["claimant_id"])

    # ── Gate 1: oracle ────────────────────────────────────────────────────────
    evidence_dir = job_dir / "evidence" / claimant_id
    ledger_dir = job_dir / "ledger"

    try:
        oracle_verdict, oracle_detail = _grade(
            card_path=card_path,
            repo_path=racer["worktree_path"],
            commit_sha=racer["commit_sha"],
            held_root=held_root,
            evidence_dir=evidence_dir,
            ledger_dir=ledger_dir,
            oracle_cmd=oracle_cmd,
        )
    except OracleCardError as exc:
        # Bad card: fail-closed — FAIL for this submission, never raise.
        oracle_verdict = "FAIL"
        oracle_detail = {"error": str(exc)}

    # ── Gate 2: reachability ──────────────────────────────────────────────────
    try:
        reach = _sweep(task_id, start_commit, cwd=racer["worktree_path"])
        reach_verdict = reach.get("verdict", "ERROR")
    except Exception as exc:  # noqa: BLE001
        reach_verdict = "ERROR"

    # ── Assemble Submission ───────────────────────────────────────────────────
    # Map oracle detail keys safely: missing → "" / null (never invent values).
    # If the detail carries an "error" key (e.g. from a caught OracleCardError
    # or a fail-closed oracle invocation), pass it through so the caller can
    # diagnose the reason for FAIL without inventing evidence values.
    oracle_block: dict = {
        "verdict": oracle_verdict,           # TRUSTED
        "exitCode": _int_or_none(oracle_detail.get("exitCode")),
        "evidenceRef": _str(oracle_detail.get("evidenceRef")),
        "sandboxImageDigest": _str(oracle_detail.get("sandboxImageDigest")),
        "ledgerEventId": _str(oracle_detail.get("ledgerEventId")),
    }
    if "error" in oracle_detail:
        oracle_block["error"] = oracle_detail["error"]

    return {
        "claimant": {
            "kind": "executor",
            "id": claimant_id,
        },
        "commitSha": racer["commit_sha"],
        "selfReportedExit": _int_or_none(racer.get("self_reported_exit")),
        "oracle": oracle_block,
        "reachability": {"verdict": reach_verdict},
        "commitHash": racer.get("commit_hash", ""),
        "revealedAt": racer.get("revealed_at", ""),
        "entryFeePaid": int(racer.get("entry_fee_paid", 0)),
        "fakeryStake": int(racer.get("fakery_stake", 0)),
    }


def adjudicate_job(
    *,
    job_dir: "str | Path",
    racers: "list[dict]",
    card_path: "str | Path",
    held_root: "str | Path",
    task_id: str,
    start_commit: str,
    job_id: str,
    card_id: str,
    bounty_amount: int,
    job_poster: str,
    oracle_cmd: "list[str] | None" = None,
    _grade=grade_card,
    _sweep=run_reachability_sweep,
) -> "list[dict]":
    """Adjudicate all racers for a job, write submissions.json + job.json.

    Runs adjudicate_submission sequentially for each racer, collecting the
    Submission dicts. Writes both output files atomically. Returns the list.
    """
    job_dir = Path(job_dir)

    submissions = [
        adjudicate_submission(
            racer,
            card_path=card_path,
            held_root=held_root,
            job_dir=job_dir,
            task_id=task_id,
            start_commit=start_commit,
            oracle_cmd=oracle_cmd,
            _grade=_grade,
            _sweep=_sweep,
        )
        for racer in racers
    ]

    # Write submissions.json atomically.
    atomic_write(
        job_dir / "submissions.json",
        json.dumps(submissions, indent=2, default=str),
    )

    # Write job.json atomically.
    job_meta = {
        "jobId": job_id,
        "cardId": card_id,
        "bountyAmount": bounty_amount,
        "jobPoster": job_poster,
    }
    atomic_write(
        job_dir / "job.json",
        json.dumps(job_meta, indent=2, default=str),
    )

    return submissions


def settle_job(
    *,
    job_dir: "str | Path",
    tournament_cmd: "list[str] | None" = None,
    enforce_slash: bool = False,
) -> dict:
    """Shell the TS CLI to settle the tournament and return the parsed envelope.

    Parameters
    ----------
    job_dir:
        Path to the job directory (contains submissions.json + job.json).
    tournament_cmd:
        Optional explicit tournament command. Falls back to ATLAS_TOURNAMENT_CMD
        env var (shell-split) or ["atlas"].
    enforce_slash:
        If True, passes --enforce-slash to the CLI.

    Returns
    -------
    The parsed JSON envelope from the CLI. If the CLI exits non-zero or
    `ok` is False, returns the envelope as-is (does NOT raise). Only raises
    if stdout is not parseable JSON.

    Raises
    ------
    ValueError:
        If the CLI stdout cannot be parsed as JSON.
    """
    cmd = (tournament_cmd or _tournament_cmd()) + [
        "tournament", "settle",
        "--job", str(job_dir),
    ]
    if enforce_slash:
        cmd.append("--enforce-slash")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"tournament CLI invocation failed: {exc}") from exc

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"tournament CLI produced unparseable output: {exc!r}\n"
            f"stdout={proc.stdout[:500]!r}\nstderr={proc.stderr[:500]!r}"
        ) from exc

    # Fail-closed on ok:false — return the envelope, let the caller decide.
    return envelope
