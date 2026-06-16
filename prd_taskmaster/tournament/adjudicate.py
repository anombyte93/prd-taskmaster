"""Tournament adjudicator: run oracle + reachability gates per racer submission.

Produces trusted Submission dicts matching the TS atlas-protocol spine, writes
submissions.json + job.json, and shells `atlas tournament settle`.

Fail-closed: a bad card or sweep means FAIL/ERROR for THAT submission only —
the job is never aborted and a bad racer never gets a false PASS.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from prd_taskmaster.lib import atomic_write
from prd_taskmaster.oracle_bridge import OracleCardError, grade_card
from prd_taskmaster.reachability_cmd import run_reachability_sweep

log = logging.getLogger(__name__)

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


def _sanitize_path_component(value: str) -> str:
    """Sanitize a claimant_id for use as a filesystem path component.

    Strips path separators and '..' to prevent directory traversal.
    Only used for the evidence_dir path — the original claimant.id
    is preserved in the Submission for settlement identity.
    """
    # Take only the final component (strips any leading dir parts)
    safe = Path(value).name
    # Replace any remaining '..' sequences
    safe = safe.replace("..", "_")
    # Replace forward and back slashes that Path.name may not have caught
    safe = safe.replace("/", "_").replace("\\", "_")
    # Fall back to a placeholder if the result is empty
    return safe or "_unknown_"


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

    # I3 — sanitize claimant_id for use as a path component only.
    # The original claimant_id is preserved in the Submission's claimant.id.
    safe_id = _sanitize_path_component(claimant_id)

    # ── Gate 1: oracle ────────────────────────────────────────────────────────
    evidence_dir = job_dir / "evidence" / safe_id
    ledger_dir = job_dir / "ledger"

    # I2 — ensure dirs exist before the oracle writes into them.
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)

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
            "id": claimant_id,      # ORIGINAL identity preserved for settlement
        },
        "commitSha": racer["commit_sha"],
        "selfReportedExit": _int_or_none(racer.get("self_reported_exit")),
        "oracle": oracle_block,
        "reachability": {"verdict": reach_verdict},
        "commitHash": racer.get("commit_hash", ""),
        "revealedAt": racer.get("revealed_at", ""),
        # B2 — safe coercion: bad/missing entry_fee_paid or fakery_stake → 0,
        # not a TypeError crash.
        "entryFeePaid": _int_or_none(racer.get("entry_fee_paid")) or 0,
        "fakeryStake": _int_or_none(racer.get("fakery_stake")) or 0,
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
    Submission dicts. Never aborts the whole job: any unexpected exception from
    adjudicate_submission is caught per-racer and replaced with a fail-closed
    ERROR submission. Returns the list.
    """
    job_dir = Path(job_dir)

    submissions: list[dict] = []
    for racer in racers:
        # I1 — per-racer fail-closed containment: unexpected exceptions (e.g.
        # KeyError on a malformed racer) must not abort the whole job.
        try:
            sub = adjudicate_submission(
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
        except Exception as exc:  # noqa: BLE001
            # Fail-closed: produce an ERROR submission instead of crashing.
            # reachability.verdict="ERROR" ⟹ passesBothGates=false on the TS side.
            claimant_id = racer.get("claimant_id", "unknown") if isinstance(racer, dict) else "unknown"
            commit_sha = racer.get("commit_sha", "unknown") if isinstance(racer, dict) else "unknown"
            log.exception(
                "Unexpected error adjudicating racer %r (commit %r); inserting ERROR submission",
                claimant_id,
                commit_sha,
            )
            sub = {
                "claimant": {
                    "kind": "executor",
                    "id": str(claimant_id),
                },
                "commitSha": str(commit_sha),
                "selfReportedExit": None,
                "oracle": {
                    "verdict": "ERROR",
                    "exitCode": None,
                    "evidenceRef": "",
                    "sandboxImageDigest": "",
                    "ledgerEventId": "",
                    "error": f"adjudication failed: {exc}",
                },
                "reachability": {"verdict": "ERROR"},
                "commitHash": "",
                "revealedAt": "",
                "entryFeePaid": 0,
                "fakeryStake": 0,
            }
        submissions.append(sub)

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
        If the CLI stdout cannot be parsed as JSON, the process cannot be
        launched (OSError/SubprocessError), or the process times out.
    """
    # B1 — timeout: default 120s, overridable via ATLAS_TOURNAMENT_TIMEOUT_S.
    try:
        timeout_s = int(os.environ.get("ATLAS_TOURNAMENT_TIMEOUT_S", "120"))
    except (TypeError, ValueError):
        timeout_s = 120

    cmd = (tournament_cmd or _tournament_cmd()) + [
        "tournament", "settle",
        "--job", str(job_dir),
    ]
    if enforce_slash:
        cmd.append("--enforce-slash")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"tournament CLI timed out after {timeout_s}s"
        ) from exc
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
