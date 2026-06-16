"""Anti-Sybil admission control for the tournament spawner.

Free AI identities are infinite and free — so we need economic gates.
Every racer entering a job must:
  1. Not exceed the per-job cap (PER_JOB_CAP_N).
  2. Not exceed the same operator's active rate limit (PER_OPERATOR_RATE_LIMIT).

Admission is atomic via locked_update (no race between two concurrent callers).
Persistence lives under .atlas-ai/tournament/operators.json.

Shape::
    {
        "entries": [
            {
                "operator_id": str,
                "job_id": str,
                "claimant_id": str,
                "admitted_at": str,   # ISO-8601 UTC
                "expires_at": str,    # ISO-8601 UTC  (admitted_at + TTL_SECONDS)
                "active": bool
            },
            ...
        ]
    }

TTL / crashed-job cleanup
-------------------------
Each admitted entry carries ``expires_at`` (now + TTL_SECONDS).  Inside every
``admit`` call the transform sweeps expired entries (sets active=False) BEFORE
counting, so crashed-job slots self-free after TTL_SECONDS.

``sweep_expired(state, now)`` is a pure helper — also useful from tests or a
separate maintenance job.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from prd_taskmaster.lib import locked_update

# ─── Constants ────────────────────────────────────────────────────────────────

ENTRY_FEE_E: int = 1
FAKERY_STAKE_MULT: int = 5        # S = 5 * E
PER_JOB_CAP_N: int = 8
PER_OPERATOR_RATE_LIMIT: int = 3
TTL_SECONDS: int = 4 * 3600      # 4 hours — matches launcher max_lifetime



# ─── Typed errors ─────────────────────────────────────────────────────────────

class SybilLimitError(Exception):
    """Raised when an admission check fails.

    Attributes
    ----------
    reason:
        One of "job_cap_exceeded" or "operator_rate_limited".
    """

    VALID_REASONS = frozenset({"job_cap_exceeded", "operator_rate_limited"})

    def __init__(self, reason: str) -> None:
        if reason not in self.VALID_REASONS:
            raise ValueError(f"Invalid SybilLimitError reason: {reason!r}")
        super().__init__(reason)
        self.reason = reason


# ─── Pure helpers (no I/O) ────────────────────────────────────────────────────

def sweep_expired(state: dict, now: str) -> dict:
    """Deactivate entries whose expires_at is in the past (pure — mutates in place).

    Parameters
    ----------
    state:
        Loaded operators.json dict (mutated in place for efficiency).
    now:
        ISO-8601 UTC timestamp to compare against expires_at.

    Returns the same dict (mutated) for chaining convenience.

    Notes
    -----
    Entries without an ``expires_at`` field are left untouched (backwards
    compatible with data written before TTL was introduced).
    """
    try:
        now_dt = datetime.fromisoformat(now)
    except (ValueError, TypeError):
        return state

    for entry in state.get("entries", []):
        if not entry.get("active", False):
            continue
        expires_at = entry.get("expires_at")
        if not expires_at:
            continue
        try:
            exp_dt = datetime.fromisoformat(expires_at)
        except (ValueError, TypeError):
            continue
        if exp_dt <= now_dt:
            entry["active"] = False

    return state


def active_count_for_job(state: dict, job_id: str) -> int:
    """Count active entries for a given job_id (pure, on a loaded dict)."""
    return sum(
        1
        for e in state.get("entries", [])
        if e.get("job_id") == job_id and e.get("active", False)
    )


def active_count_for_operator(state: dict, operator_id: str) -> int:
    """Count active entries for a given operator_id across all jobs (pure)."""
    return sum(
        1
        for e in state.get("entries", [])
        if e.get("operator_id") == operator_id and e.get("active", False)
    )


# ─── Stateful API ─────────────────────────────────────────────────────────────

def admit(
    operators_path: "str | Path",
    *,
    operator_id: str,
    job_id: str,
    claimant_id: str,
    now: str,
    entry_fee: int = ENTRY_FEE_E,
    stake_mult: int = FAKERY_STAKE_MULT,
    n_cap: int = PER_JOB_CAP_N,
    rate_limit: int = PER_OPERATOR_RATE_LIMIT,
) -> dict:
    """Admit a racer to a job, enforcing per-job cap and per-operator rate limit.

    Parameters
    ----------
    operators_path:
        Path to operators.json (created if absent).
    operator_id:
        Identifies the AI provider+model (e.g. "claude:sonnet").
    job_id:
        Tournament job identifier.
    claimant_id:
        Unique racer identifier for this job slot.
    now:
        ISO-8601 UTC timestamp (passed in for determinism).
    entry_fee:
        E — entry fee amount.
    stake_mult:
        S multiplier so S = entry_fee * stake_mult.
    n_cap:
        Maximum active racers per job.
    rate_limit:
        Maximum concurrent active entries per operator across all jobs.

    Returns
    -------
    ``{"entry_fee_paid": E, "fakery_stake": S}``

    Raises
    ------
    SybilLimitError("job_cap_exceeded")
        When the per-job cap would be breached.
    SybilLimitError("operator_rate_limited")
        When the operator already has rate_limit active entries.
    """
    operators_path = Path(operators_path)

    # Compute expires_at from now + TTL_SECONDS.
    try:
        now_dt = datetime.fromisoformat(now)
        # Ensure timezone-aware for arithmetic; fallback to UTC if naive.
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        from datetime import timedelta
        expires_dt = now_dt + timedelta(seconds=TTL_SECONDS)
        expires_at = expires_dt.isoformat()
    except (ValueError, TypeError):
        expires_at = now  # degenerate fallback

    result: dict = {}
    error: SybilLimitError | None = None

    def _transform(current: str) -> str:
        nonlocal result, error

        state: dict
        if current.strip():
            try:
                state = json.loads(current)
            except json.JSONDecodeError:
                state = {"entries": []}
        else:
            state = {"entries": []}

        if not isinstance(state.get("entries"), list):
            state["entries"] = []

        # ── Sweep expired entries BEFORE counting (I2) ────────────────────────
        sweep_expired(state, now)

        # ── Check per-job cap ─────────────────────────────────────────────────
        job_active = active_count_for_job(state, job_id)
        if job_active >= n_cap:
            error = SybilLimitError("job_cap_exceeded")
            return current  # no change — abort inside transform (m3: no ghost write)

        # ── Check per-operator rate limit ─────────────────────────────────────
        op_active = active_count_for_operator(state, operator_id)
        if op_active >= rate_limit:
            error = SybilLimitError("operator_rate_limited")
            return current  # no change (m3: no ghost write)

        # ── Admit ─────────────────────────────────────────────────────────────
        state["entries"].append({
            "operator_id": operator_id,
            "job_id": job_id,
            "claimant_id": claimant_id,
            "admitted_at": now,
            "expires_at": expires_at,
            "active": True,
        })

        result = {
            "entry_fee_paid": entry_fee,
            "fakery_stake": entry_fee * stake_mult,
        }
        return json.dumps(state, indent=2)

    locked_update(operators_path, _transform)

    if error is not None:
        raise error

    return result


def release(
    operators_path: "str | Path",
    *,
    job_id: str,
    claimant_id: "str | None" = None,
) -> None:
    """Mark entries inactive, freeing operator rate-limit slots.

    Parameters
    ----------
    operators_path:
        Path to operators.json.
    job_id:
        Release all active entries for this job (or just one claimant).
    claimant_id:
        If provided, release only the matching claimant; otherwise release
        ALL active entries for the job (post-settlement cleanup).
    """
    operators_path = Path(operators_path)

    def _transform(current: str) -> str:
        if not current.strip():
            return current

        try:
            state = json.loads(current)
        except json.JSONDecodeError:
            return current

        if not isinstance(state.get("entries"), list):
            return current

        for entry in state["entries"]:
            if entry.get("job_id") != job_id:
                continue
            if not entry.get("active", False):
                continue
            if claimant_id is None or entry.get("claimant_id") == claimant_id:
                entry["active"] = False

        return json.dumps(state, indent=2)

    locked_update(operators_path, _transform)
