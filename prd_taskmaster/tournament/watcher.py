"""Independent out-of-band re-execution watcher for the tournament marketplace.

The marketplace runs **shadow-slash only** until an independent watcher exists:
the in-band adjudicator records ``wouldSlash`` but burns no AtlasCoin. This module
is that watcher. It re-adjudicates settled submissions from PRIMARY EVIDENCE — the
claimed commit + the CDD card — *without trusting the recorded verdict*, compares
its independently-derived verdict to the adjudicator's, accumulates a concordance
ledger over real *slash decisions*, and exposes a FAIL-CLOSED gate
(:func:`permit_enforce_slash`) that allows real (``--enforce-slash``) forfeiture
only behind an observed track record.

Hardened invariants (the catastrophic failure is permitting an UNJUST real slash):
* **ABSTAIN, never confirm-on-inability.** Only POSITIVE independent evidence — a
  clean oracle re-run that FAILED, an ORPHAN reachability sweep, or a real diff
  hash that DIFFERS from the recorded one — counts as grounds to slash. If the
  watcher could not run a gate (oracle errored, no worktree, failed recompute) it
  ABSTAINS, which BLOCKS the permit.
* **Whole-job veto.** ANY discrepancy in the job — including a cheating *winner*
  the in-band adjudicator passed — blocks the permit.
* **No self-bootstrapping.** Historical concordance excludes the in-flight job and
  is measured over real slash *decisions*, not trivial double-PASS winners.
* **Read-only.** Uses the pure (non-card-writing) reachability sweep; writes ONLY
  its own ledger; never mutates tournament state, reputation, or AtlasCoin.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from prd_taskmaster import reachability_cmd as _rc
from prd_taskmaster.economy import append_telemetry
from prd_taskmaster.oracle_bridge import grade_card
from prd_taskmaster.reachability import sweep_task as _sweep_task
from prd_taskmaster.tournament.collect import _compute_diff_hash

# Real slashing stays gated until the watcher has a track record. High bar by
# design: it must independently uphold the vast majority of a meaningful sample of
# real slash DECISIONS before any AtlasCoin is ever burned.
ACCURACY_THRESHOLD = 0.95
MIN_OBSERVATIONS = 20

_PASS_REACH = {"WIRED", "EXEMPT"}
_DEFAULT_LEDGER = Path(".atlas-ai/tournament/watcher.jsonl")


# ── internal helpers ─────────────────────────────────────────────────────────

def _readonly_sweep(task_id: str, start_commit: str, cwd: "str | None" = None) -> dict:
    """Pure reachability sweep — returns a verdict WITHOUT mutating the CDD card.

    Reachability needs tasks.json + the CDD card, which are gitignored and absent
    from a fresh worktree checkout; any failure to load them ABSTAINS (it is best-
    effort, never card-writing, never a false WIRED).
    """
    try:
        repo_root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
        task = _rc._load_task(repo_root, task_id)
        verdict = _sweep_task(repo_root, task, start_commit)
        return verdict if isinstance(verdict, dict) else {"verdict": "ABSTAIN"}
    except Exception:  # noqa: BLE001 — best-effort, read-only, fail to ABSTAIN
        return {"verdict": "ABSTAIN"}


def _make_worktree(repo_root: str, commit_sha: str) -> "str | None":
    """Create a detached worktree at *commit_sha*; None on any git failure."""
    try:
        wt = tempfile.mkdtemp(prefix="atlas-watcher-")
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "--detach", wt, commit_sha],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            shutil.rmtree(wt, ignore_errors=True)
            return None
        return wt
    except Exception:  # noqa: BLE001 — fail-closed: no worktree on any error
        return None


def _drop_worktree(repo_root: str, wt: "str | None") -> None:
    if not wt:
        return
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", wt],
            capture_output=True, timeout=60,
        )
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(wt, ignore_errors=True)


def _passes_both(oracle_verdict: str, oracle_error: bool, reach_verdict: str) -> bool:
    return (oracle_verdict == "PASS" and not oracle_error) and reach_verdict in _PASS_REACH


def _recorded_passes_both(submission: dict) -> bool:
    oracle = (submission.get("oracle") or {}).get("verdict")
    reach = (submission.get("reachability") or {}).get("verdict")
    return oracle == "PASS" and reach in _PASS_REACH


# ── public API ───────────────────────────────────────────────────────────────

def re_adjudicate_submission(
    submission: dict,
    *,
    worktree: "str | None",
    repo_root: str,
    card_path: "str | Path",
    held_root: "str | Path",
    job_dir: "str | Path",
    task_id: str,
    start_commit: str,
    base_ref: str,
    oracle_cmd: "list[str] | None" = None,
    _grade: Callable[..., Any] = grade_card,
    _sweep: Callable[..., Any] = _readonly_sweep,
    _hash: Callable[..., str] = _compute_diff_hash,
) -> dict:
    """Independently re-adjudicate one submission from primary evidence.

    Returns a verdict dict. ``slash_grounds`` is True ONLY on positive independent
    evidence (clean oracle FAIL, ORPHAN sweep, or real differing hash). ``agreement``
    is ``ABSTAIN`` when the watcher could not independently verify (and there is no
    tamper), ``CONFIRM`` when its fail/pass conclusion matches the recorded one, and
    ``DISCREPANCY`` otherwise. ABSTAIN and DISCREPANCY both block the slash permit.
    """
    claimant_id = str((submission.get("claimant") or {}).get("id", "unknown"))
    commit_sha = str(submission.get("commitSha", ""))
    job_dir = Path(job_dir)

    evidence_dir = job_dir / "watcher-evidence" / claimant_id
    ledger_dir = job_dir / "watcher-ledger"
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ledger_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    # ── Gate 1: oracle — the workhorse independent re-execution ──────────────
    # grade_card is itself fail-closed: it returns ("FAIL", {"error": ...}) for an
    # INFRA failure rather than raising. We must NOT read that as a genuine fail.
    oracle_error = False
    try:
        watcher_oracle, detail = _grade(
            card_path=card_path, repo_path=repo_root, commit_sha=commit_sha,
            held_root=held_root, evidence_dir=evidence_dir, ledger_dir=ledger_dir,
            oracle_cmd=oracle_cmd,
        )
        if isinstance(detail, dict) and "error" in detail:
            oracle_error = True
    except Exception:  # noqa: BLE001 — gate could not run → abstain, never a PASS or a genuine FAIL
        watcher_oracle = "FAIL"
        oracle_error = True

    # ── Gate 2: reachability — best-effort, never falls back to repo_root ────
    if not worktree:
        # No worktree → we did NOT evaluate the racer's commit; abstain this axis.
        watcher_reach = "ABSTAIN"
    else:
        try:
            reach = _sweep(task_id, start_commit, cwd=worktree)
            watcher_reach = str(reach.get("verdict", "ERROR"))
        except Exception:  # noqa: BLE001
            watcher_reach = "ERROR"

    # ── Independent commit-reveal hash re-derivation (anti diff-copy) ────────
    recorded_hash = str(submission.get("commitHash", ""))
    recomputed = ""
    if worktree:
        try:
            recomputed = _hash(worktree, base_ref, commit_sha) or ""
        except Exception:  # noqa: BLE001
            recomputed = ""
    hash_recomputed = recomputed != ""
    # Tamper requires a REAL recomputed hash that DIFFERS — an empty/failed recompute
    # is "unverifiable", NOT positive tamper evidence (it must abstain, not confirm).
    tamper = hash_recomputed and (recomputed != recorded_hash)

    watcher_passes_both = _passes_both(str(watcher_oracle), oracle_error, watcher_reach)
    recorded_passes_both = _recorded_passes_both(submission)
    recorded_fail = not recorded_passes_both

    # POSITIVE independent grounds to slash.
    slash_grounds = (
        (str(watcher_oracle) == "FAIL" and not oracle_error)
        or watcher_reach == "ORPHAN"
        or tamper
    )
    # The watcher has an independent verdict iff the oracle genuinely ran.
    verified = not oracle_error

    if not verified and not tamper:
        agreement = "ABSTAIN"
    elif slash_grounds == recorded_fail:
        agreement = "CONFIRM"
    else:
        agreement = "DISCREPANCY"

    return {
        "claimant_id": claimant_id,
        "commit_sha": commit_sha,
        "watcher_oracle": str(watcher_oracle),
        "watcher_oracle_error": oracle_error,
        "watcher_reachability": watcher_reach,
        "watcher_passes_both": watcher_passes_both,
        "recorded_oracle": str((submission.get("oracle") or {}).get("verdict", "")),
        "recorded_reachability": str((submission.get("reachability") or {}).get("verdict", "")),
        "recorded_passes_both": recorded_passes_both,
        "recorded_hash": recorded_hash,
        "recomputed_hash": recomputed,
        "hash_recomputed": hash_recomputed,
        "tamper": tamper,
        "verified": verified,
        "slash_grounds": slash_grounds,
        "agreement": agreement,
    }


def re_adjudicate_job(
    *,
    job_dir: "str | Path",
    repo_root: str,
    card_path: "str | Path",
    held_root: "str | Path",
    task_id: str,
    start_commit: str,
    base_ref: str,
    now: str,
    oracle_cmd: "list[str] | None" = None,
    ledger_path: "str | Path | None" = None,
    _grade: Callable[..., Any] = grade_card,
    _sweep: Callable[..., Any] = _readonly_sweep,
    _hash: Callable[..., str] = _compute_diff_hash,
    _worktree_for: "Callable[[str], str | None] | None" = None,
) -> dict:
    """Re-adjudicate every submission in a settled job; append one ledger row.

    FAIL-CLOSED: a missing/unreadable submissions file returns ``{"ok": False, ...}``
    and writes NO ledger row. The ledger row records ``decisions`` (real slash
    decisions = recorded-fail submissions) and ``confirmed_slashes`` — the track
    record measures slash-detection skill, not trivial winners.
    """
    job_dir = Path(job_dir)
    ledger = Path(ledger_path) if ledger_path is not None else _DEFAULT_LEDGER

    try:
        submissions = json.loads((job_dir / "submissions.json").read_text())
        if not isinstance(submissions, list):
            raise ValueError("submissions.json is not a list")
    except Exception as exc:  # noqa: BLE001 — fail-closed, no ledger row
        return {"ok": False, "error": f"cannot read submissions: {exc}", "job_dir": str(job_dir)}

    try:
        job_meta = json.loads((job_dir / "job.json").read_text())
        job_id = str(job_meta.get("jobId", job_dir.name))
    except Exception:  # noqa: BLE001
        job_id = job_dir.name

    verdicts: list[dict] = []
    for sub in submissions:
        commit_sha = str((sub or {}).get("commitSha", ""))
        if _worktree_for is not None:
            wt = _worktree_for(commit_sha)
            owns_wt = False
        else:
            wt = _make_worktree(repo_root, commit_sha)
            owns_wt = True
        try:
            verdicts.append(
                re_adjudicate_submission(
                    sub, worktree=wt, repo_root=repo_root, card_path=card_path,
                    held_root=held_root, job_dir=job_dir, task_id=task_id,
                    start_commit=start_commit, base_ref=base_ref, oracle_cmd=oracle_cmd,
                    _grade=_grade, _sweep=_sweep, _hash=_hash,
                )
            )
        finally:
            if owns_wt:
                _drop_worktree(repo_root, wt)

    confirms = sum(1 for v in verdicts if v["agreement"] == "CONFIRM")
    discrepancies = sum(1 for v in verdicts if v["agreement"] == "DISCREPANCY")
    decisions = sum(1 for v in verdicts if not v["recorded_passes_both"])
    confirmed_slashes = sum(
        1 for v in verdicts
        if (not v["recorded_passes_both"]) and v["agreement"] == "CONFIRM" and v["slash_grounds"]
    )

    row = {
        "job_id": job_id,
        "ts": now,
        "observations": len(verdicts),
        "confirms": confirms,
        "discrepancies": discrepancies,
        "decisions": decisions,
        "confirmed_slashes": confirmed_slashes,
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ref = append_telemetry(row, path=ledger)

    return {
        "ok": True,
        "job_id": job_id,
        "observations": len(verdicts),
        "confirms": confirms,
        "discrepancies": discrepancies,
        "decisions": decisions,
        "confirmed_slashes": confirmed_slashes,
        "submissions": verdicts,
        "ledger_ref": ref,
    }


def _is_to_be_slashed(verdict: dict, slashed_ids: "set[str] | None") -> bool:
    """A submission is to-be-slashed if explicitly named, else if it failed the gates."""
    if slashed_ids is not None:
        return verdict.get("claimant_id") in slashed_ids
    return not verdict.get("recorded_passes_both", False)


def _read_concordance(
    ledger_path: "str | Path", *, exclude_job_id: "str | None" = None
) -> "tuple[int, int]":
    """Return (total_decisions, total_confirmed_slashes) across PRIOR ledger rows.

    Rows for ``exclude_job_id`` (the in-flight job) are skipped so a job can never
    vouch for its own gate. Malformed rows (confirmed > decisions, negatives) are
    clamped so they cannot inflate the track record.
    """
    p = Path(ledger_path)
    if not p.is_file():
        return (0, 0)
    decisions = confirmed = 0
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if exclude_job_id is not None and r.get("job_id") == exclude_job_id:
            continue
        try:
            d = max(int(r.get("decisions", 0) or 0), 0)
            c = max(int(r.get("confirmed_slashes", 0) or 0), 0)
        except (TypeError, ValueError):
            continue  # skip malformed rows rather than crash callers (e.g. watcher-status)
        c = min(c, d)  # clamp: confirmed can never exceed decisions
        decisions += d
        confirmed += c
    return (decisions, confirmed)


def concordance_summary(ledger_path: "str | Path") -> dict:
    """Summarize the watcher's historical track record over real slash decisions."""
    observations, confirmed = _read_concordance(ledger_path)
    conc = (confirmed / observations) if observations else 0.0
    conc = min(conc, 1.0)
    return {
        "observations": observations,
        "confirmed_slashes": confirmed,
        "concordance": conc,
        "min_observations": MIN_OBSERVATIONS,
        "accuracy_threshold": ACCURACY_THRESHOLD,
        "real_slash_ready": observations >= MIN_OBSERVATIONS and conc >= ACCURACY_THRESHOLD,
    }


def permit_enforce_slash(
    record: dict,
    *,
    ledger_path: "str | Path",
    slashed_ids: "set[str] | None" = None,
    current_job_id: "str | None" = None,
) -> dict:
    """FAIL-CLOSED gate: may real slashing be enforced for this job?

    ``permitted`` is True only when ALL of:
    * at least one to-be-slashed submission, and EVERY one is independently
      confirmed (positive grounds + CONFIRM agreement);
    * NO discrepancy anywhere in the job (a cheating winner vetoes the whole job);
    * NO abstained to-be-slashed submission (could-not-verify never permits);
    * historical concordance over PRIOR jobs clears the threshold over enough real
      slash decisions.
    Any error → ``permitted: False``.
    """
    try:
        subs = record.get("submissions")
        if not isinstance(subs, list):
            raise TypeError("record.submissions must be a list")

        job_id = current_job_id if current_job_id is not None else record.get("job_id")

        # Whole-job veto: real coin moves only when the watcher independently
        # reproduced the ENTIRE adjudication. Any discrepancy (incl. a cheating
        # winner) OR any ABSTAIN (a submission — winner or loser — the watcher
        # could not independently verify) blocks the permit.
        discrepancies = [
            str(v.get("claimant_id")) for v in subs if v.get("agreement") == "DISCREPANCY"
        ]
        abstained = [
            str(v.get("claimant_id")) for v in subs if v.get("agreement") == "ABSTAIN"
        ]

        to_slash = [v for v in subs if _is_to_be_slashed(v, slashed_ids)]
        confirmed = [
            str(v.get("claimant_id")) for v in to_slash
            if v.get("slash_grounds") and v.get("agreement") == "CONFIRM"
        ]

        observations, confirmed_hist = _read_concordance(ledger_path, exclude_job_id=job_id)
        concordance = min((confirmed_hist / observations) if observations else 0.0, 1.0)
        track_record_ok = observations >= MIN_OBSERVATIONS and concordance >= ACCURACY_THRESHOLD

        all_slashes_confirmed = bool(to_slash) and len(confirmed) == len(to_slash)
        permitted = bool(
            track_record_ok and not discrepancies and not abstained and all_slashes_confirmed
        )

        if permitted:
            reason = (
                f"permitted: {len(confirmed)} confirmed slash(es), "
                f"concordance={concordance:.3f} over {observations} prior decisions"
            )
        # Surface the most-serious finding FIRST: a discrepancy (incl. a cheating
        # winner) or an abstain must never be masked by the benign "nothing to
        # slash" message when to_slash happens to be empty.
        elif discrepancies:
            reason = f"blocked: {len(discrepancies)} discrepancy(ies) in the job"
        elif abstained:
            reason = f"blocked: {len(abstained)} submission(s) in the job could not be independently verified (abstain)"
        elif not to_slash:
            reason = "blocked: no to-be-slashed submissions to confirm"
        elif not track_record_ok:
            reason = (
                f"blocked: thin track record — {observations}/{MIN_OBSERVATIONS} prior "
                f"decisions, concordance={concordance:.3f}/{ACCURACY_THRESHOLD}"
            )
        else:
            reason = "blocked: not all to-be-slashed submissions confirmed"

        return {
            "permitted": permitted,
            "reason": reason,
            "confirmed": confirmed,
            "discrepancies": discrepancies,
            "abstained": abstained,
            "concordance": concordance,
            "observations": observations,
        }
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return {
            "permitted": False,
            "reason": f"error: {exc}",
            "confirmed": [],
            "discrepancies": [],
            "abstained": [],
            "concordance": 0.0,
            "observations": 0,
        }
