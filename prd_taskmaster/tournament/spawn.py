"""Tournament roster builder and spawn dispatcher.

Architecture note (matches engine pattern):
  - This module COMPUTES the roster and gates it via antisybil.admit.
  - It NEVER calls session_spawn directly at module load or in its core functions.
  - The actual session_spawn calls are injected via _spawn_fn / default_launcher_adapter.
  - Unit tests inject a stub _spawn_fn — no live launcher coupling.

Usage::

    from prd_taskmaster.tournament.spawn import build_roster, spawn_roster

    roster = build_roster(
        models=["claude:sonnet", "claude:haiku"],
        job_id="job-abc",
        task_prompt="...",
        card_ref="card-123",
        base_ref="abc1234",          # REQUIRED: fork-point commit for diff hash
        report_to="orchestrator-inbox",
        operators_path=Path(".atlas-ai/tournament/operators.json"),
        now="2026-06-17T00:00:00+00:00",
    )
    handles = spawn_roster(roster, _spawn_fn=my_launcher_adapter)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from prd_taskmaster.tournament import antisybil
from prd_taskmaster.tournament.antisybil import PER_JOB_CAP_N, SybilLimitError

# ─── RacerSpec dataclass ──────────────────────────────────────────────────────

@dataclass
class RacerSpec:
    """Deterministic spec for one tournament racer.

    All fields are set at build time; no random data.
    entry_fee_paid and fakery_stake flow from antisybil.admit → Submission.
    """
    claimant_id: str
    operator_id: str
    model: str
    job_id: str
    prompt: str
    isolation: str
    report_to: str
    entry_fee_paid: int
    fakery_stake: int


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _derive_operator_id(model: str) -> str:
    """Derive a stable operator_id from a model string.

    Rules:
      - "claude:sonnet"       → "claude:sonnet"
      - "claude:haiku"        → "claude:haiku"
      - "openrouter:gpt-5"    → "openrouter:gpt-5"
      - Same provider+model   → same operator_id (rate-limit applies)
      - Different providers   → different operator_ids

    The operator is identified by the full "provider:model" string so that
    different providers are treated as distinct operators even if the model
    name is the same, while the same provider+model submitted twice shares
    an operator slot and will hit the rate limit on the second entry.
    """
    # The spec says: operator_id = backend/provider portion before `:` plus the model.
    # i.e., the full model string IS the operator_id — same provider+model twice
    # shares an operator and will hit the rate limit.
    return model


def _build_racer_prompt(
    *,
    task_prompt: str,
    job_id: str,
    card_ref: str,
    claimant_id: str,
    base_ref: str,
    report_to: str,
) -> str:
    """Build the commit-reveal prompt for one racer.

    The prompt embeds:
      - The original task_prompt.
      - The shared job_id (so the orchestrator can match replies).
      - The card_ref (the CDD card this racer must satisfy).
      - base_ref: the fork-point commit so racers compute a reproducible diff hash
        via ``git diff {base_ref}..HEAD | sha256sum``.
      - report_to: the orchestrator inbox address where the racer must send its
        commit-reveal report (claimant_id, commit SHA, diff hash).
      - Explicit commit-reveal instructions.
    """
    return (
        f"# Tournament Task\n\n"
        f"**Job ID**: {job_id}\n"
        f"**Claimant ID**: {claimant_id}\n"
        f"**Card Reference**: {card_ref}\n\n"
        f"## Task\n\n"
        f"{task_prompt}\n\n"
        f"## Commit-Reveal Instructions\n\n"
        f"1. Perform all your work in your assigned worktree.\n"
        f"2. When complete, commit your changes with a clear commit message.\n"
        f"3. Compute your diff hash: `git diff {base_ref}..HEAD | sha256sum`.\n"
        f"4. Report the following to the orchestrator inbox **{report_to}** "
        f"(keyed by job_id={job_id!r}):\n"
        f"   - Your commit SHA (`git rev-parse HEAD`).\n"
        f"   - The SHA-256 hash of your diff (from step 3).\n"
        f"   - Your claimant_id={claimant_id!r}.\n"
        f"   - Your self-reported exit code (0=success, non-zero=failure).\n"
        f"5. Do NOT push to the main branch. Work only in your worktree.\n"
        f"6. The oracle will independently verify your commit against the card spec.\n"
    )


# ─── Core build function ──────────────────────────────────────────────────────

def build_roster(
    *,
    models: "list[str]",
    job_id: str,
    task_prompt: str,
    card_ref: str,
    base_ref: str,
    report_to: str = "",
    operators_path: "str | Path",
    now: str,
    _admit: "Callable[..., dict]" = antisybil.admit,
    _release: "Callable[..., None]" = antisybil.release,
) -> "list[RacerSpec]":
    """Build a deterministic admission-gated roster of RacerSpecs.

    Parameters
    ----------
    models:
        Ordered list of DISTINCT model strings (e.g. ["claude:sonnet", "claude:haiku"]).
        Duplicate models are rejected up-front with ValueError — a tournament
        races DISTINCT executors.  Note: operator_id = model string, so the same
        model submitted twice would trip the per-operator rate-limit at the 2nd
        entry; the up-front dup check catches this earlier with a clearer error.
        len(models) must be <= PER_JOB_CAP_N or SybilLimitError is raised up front.
    job_id:
        Unique tournament job identifier.
    task_prompt:
        The task description for all racers.
    card_ref:
        CDD card reference (shared across all racers in the job).
    base_ref:
        REQUIRED. The fork-point / base commit SHA that all worktrees branch from.
        Embedded verbatim in every racer's commit-reveal prompt so they can compute
        a reproducible diff hash: ``git diff {base_ref}..HEAD | sha256sum``.
    report_to:
        Orchestrator inbox identifier; embedded in each racer's prompt.
    operators_path:
        Path to operators.json (admission persistence).
    now:
        ISO-8601 UTC timestamp (deterministic; never calls datetime.now()).
    _admit:
        Injectable admit function (default = antisybil.admit). Tests inject a stub.
    _release:
        Injectable release function (default = antisybil.release). Used for
        rollback when a mid-roster admit fails.

    Returns
    -------
    list[RacerSpec] — one per model, in input order, with entry_fee_paid/fakery_stake set.

    Raises
    ------
    ValueError
        If models contains duplicates (a tournament races DISTINCT executors).
    SybilLimitError("job_cap_exceeded")
        Up-front if len(models) > PER_JOB_CAP_N.
    SybilLimitError("job_cap_exceeded") / SybilLimitError("operator_rate_limited")
        Per-racer if antisybil.admit rejects the entry.  Any already-admitted
        racers from THIS roster are released before re-raising, leaving no leaked
        active entries.
    """
    operators_path = Path(operators_path)

    # I3: dup-model guard — duplicates are confusing and will hit rate-limit.
    seen: set[str] = set()
    dups: list[str] = []
    for m in models:
        if m in seen:
            dups.append(m)
        seen.add(m)
    if dups:
        raise ValueError(f"duplicate models in roster: {sorted(set(dups))!r}")

    # Up-front cap guard — fail fast before any admit calls.
    if len(models) > PER_JOB_CAP_N:
        raise SybilLimitError("job_cap_exceeded")

    roster: list[RacerSpec] = []

    for i, model in enumerate(models):
        operator_id = _derive_operator_id(model)
        claimant_id = f"{job_id}:{i}:{model}"

        # I1: Admission gate — on failure, roll back all already-admitted entries
        # from THIS roster so no active slots are leaked.
        try:
            admission = _admit(
                operators_path,
                operator_id=operator_id,
                job_id=job_id,
                claimant_id=claimant_id,
                now=now,
            )
        except SybilLimitError:
            # Release every claimant admitted so far in this roster call.
            for already in roster:
                _release(
                    operators_path,
                    job_id=job_id,
                    claimant_id=already.claimant_id,
                )
            raise

        prompt = _build_racer_prompt(
            task_prompt=task_prompt,
            job_id=job_id,
            card_ref=card_ref,
            claimant_id=claimant_id,
            base_ref=base_ref,
            report_to=report_to,
        )

        roster.append(
            RacerSpec(
                claimant_id=claimant_id,
                operator_id=operator_id,
                model=model,
                job_id=job_id,
                prompt=prompt,
                isolation="worktree",
                report_to=report_to,
                entry_fee_paid=admission["entry_fee_paid"],
                fakery_stake=admission["fakery_stake"],
            )
        )

    return roster


# ─── Spawn dispatcher ─────────────────────────────────────────────────────────

def spawn_roster(
    roster: "list[RacerSpec]",
    *,
    _spawn_fn: "Callable[[RacerSpec], dict]",
) -> "list[dict]":
    """Dispatch each RacerSpec through _spawn_fn; fail-isolate individual spawn errors.

    Parameters
    ----------
    roster:
        List of RacerSpecs from build_roster.
    _spawn_fn:
        REQUIRED. Callable that accepts a RacerSpec and returns a handle dict
        (at minimum {"claimant_id": ..., "session_id": ...}).
        Use ``default_launcher_adapter`` for production; inject a stub in tests.
        There is NO default here to prevent accidental live-launcher coupling.

    Returns
    -------
    list[dict] — one entry per racer.
        Successful spawn: ``{"claimant_id": ..., "session_id": ..., "spawned": True, ...}``.
        Failed spawn:     ``{"claimant_id": ..., "spawned": False, "error": str}``.

    Notes
    -----
    A single failing spawn does NOT abort the roster. Each racer's spawn is
    attempted independently; failures are recorded with spawned=False.
    """
    handles: list[dict] = []

    for spec in roster:
        try:
            handle = _spawn_fn(spec)
            # Ensure the claimant_id and spawned flag are always present.
            handle = dict(handle)
            handle.setdefault("claimant_id", spec.claimant_id)
            handle["spawned"] = True
        except Exception as exc:  # noqa: BLE001
            handle = {
                "claimant_id": spec.claimant_id,
                "spawned": False,
                "error": str(exc),
            }

        handles.append(handle)

    return handles


# ─── Live adapter documentation (no-op at module load) ───────────────────────

def default_launcher_adapter(spec: RacerSpec) -> dict:
    """Thin documented wrapper showing the intended session_spawn mapping.

    This function documents the live wiring from RacerSpec → session_spawn without
    importing or calling the launcher MCP at module load. Call it only when the
    atlas-launcher MCP is available (inside an orchestrator skill, not in tests).

    Intended mapping::

        session_spawn(
            task=spec.prompt,
            model=spec.model,
            isolation=spec.isolation,   # always "worktree"
            report_to=spec.report_to,
            session_name=spec.claimant_id,
        )

    Raises
    ------
    RuntimeError
        Always — this adapter requires the atlas-launcher MCP to be wired.
        In production, replace with a real adapter that calls session_spawn.
    """
    raise RuntimeError(
        "default_launcher_adapter requires the atlas-launcher MCP to be available. "
        "Wire a real adapter that calls mcp__atlas-launcher__session_spawn with:\n"
        f"  task={spec.prompt[:80]!r}...\n"
        f"  model={spec.model!r}\n"
        f"  isolation={spec.isolation!r}\n"
        f"  report_to={spec.report_to!r}\n"
        f"  session_name={spec.claimant_id!r}\n"
        "Pass your adapter as _spawn_fn to spawn_roster()."
    )
