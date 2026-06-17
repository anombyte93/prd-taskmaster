"""Trusted reputation store + UCB router for Atlas Fleet executor selection.

This SUPERSEDES economy.py telemetry for routing decisions. economy.py keys on
SELF-reported exit codes — a racer can lie. Reputation is fed ONLY by the
TRUSTED ``TournamentResult.winner`` (the oracle-graded outcome from a settled
tournament), so an executor cannot inflate its own standing.

Store (mirrors the economy.py fold pattern):
  - ``.atlas-ai/reputation.jsonl`` — append-only event log (one row per
    ``record_tournament`` call), via ``lib.locked_update``.
  - ``.atlas-ai/reputation.json`` — folded snapshot keyed by
    ``(executor_id, task_class)``, via ``lib.locked_update`` (read-modify-write
    under flock; atomic replace on write).

Routing:
  - ``route_with_reputation`` computes a UCB1 score per candidate for the task's
    ``task_class`` and ALWAYS samples an unseen executor (cold-start stays open —
    an unseen candidate gets +inf and is never zero-weighted). It uses
    ``fleet.route_task`` only as a tier-appropriate reference/fallback; reputation
    NEVER gates OUT a new cheap model.

Fail-closed / deterministic:
  - All I/O goes through the injected ``lib.locked_update`` / ``atomic_write``.
  - ``now`` is injected (no ``datetime.now``); logic carries no randomness.
  - Malformed snapshot/jsonl content is skipped, never fatal.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable

from prd_taskmaster import fleet
from prd_taskmaster.lib import locked_update

# Default store paths (relative to the project root, like economy.TELEMETRY).
REPUTATION_JSONL = Path(".atlas-ai") / "reputation.jsonl"
REPUTATION_SNAPSHOT = Path(".atlas-ai") / "reputation.json"

# Cap on retained raw latency samples per (executor, task_class). The snapshot is
# re-serialized on every record_tournament, so an uncapped history would grow the
# file and the read-modify-write cost O(total tournaments) for a persistent fleet.
# p50 over the most-recent window is the routing-relevant signal anyway (stale
# samples from a since-improved executor only bias it), so we keep a bounded tail.
_LATENCY_WINDOW = 200


# ─── Path helpers ────────────────────────────────────────────────────────────

def _snapshot_path_for(jsonl_path: Path) -> Path:
    """Derive the folded-snapshot path that pairs with a jsonl event log.

    ``.../reputation.jsonl`` → ``.../reputation.json``. Any other suffix gets a
    sibling ``.snapshot.json`` so the two never collide.
    """
    jsonl_path = Path(jsonl_path)
    if jsonl_path.suffix == ".jsonl":
        return jsonl_path.with_suffix(".json")
    return jsonl_path.with_suffix(jsonl_path.suffix + ".snapshot.json")


# Unit-separator (ASCII 0x1f) cannot appear in an executor id / task class, so it
# is a collision-free delimiter for the composite JSON object key.
_KEY_SEP = "\x1f"


def _snapshot_key(executor_id: str, task_class: str) -> str:
    """Stable string key for the (executor_id, task_class) tuple in JSON.

    JSON object keys must be strings; we join with a unit-separator so neither
    part can forge a collision with another pair.
    """
    return f"{executor_id}{_KEY_SEP}{task_class}"


def _split_key(key: str) -> tuple[str, str]:
    executor_id, _, task_class = key.partition(_KEY_SEP)
    return executor_id, task_class


# ─── Coercion helpers (fail-closed: never crash on a bad row) ─────────────────

def _as_int(value, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _p50(values: "list[float]"):
    """Median (lower-of-two convention, matching economy.summarize_telemetry)."""
    clean = sorted(v for v in values if _as_number(v) is not None)
    if not clean:
        return None
    return clean[len(clean) // 2]


# ─── Trusted extraction from a TournamentResult ──────────────────────────────

def _winner_id(result: dict) -> "str | None":
    """The TRUSTED winning executor id, or None if there is no winner.

    Reads ``result.winner.claimant.id`` ONLY — never any self-reported field on
    a submission. A null/absent winner yields None (no win is recorded).
    """
    if not isinstance(result, dict):
        return None
    winner = result.get("winner")
    if not isinstance(winner, dict):
        return None
    claimant = winner.get("claimant")
    if not isinstance(claimant, dict):
        return None
    cid = claimant.get("id")
    return str(cid) if cid is not None else None


def _participant_ids(result: dict) -> "list[str]":
    """All executor ids that participated (appear in rankings), in rank order.

    De-duplicated, preserving first-seen order so per-executor n_jobs counts each
    participating executor exactly once per tournament.
    """
    out: list[str] = []
    seen: set[str] = set()
    rankings = result.get("rankings") if isinstance(result, dict) else None
    if not isinstance(rankings, list):
        return out
    for entry in rankings:
        if not isinstance(entry, dict):
            continue
        claimant = entry.get("claimant")
        if not isinstance(claimant, dict):
            continue
        cid = claimant.get("id")
        if cid is None:
            continue
        cid = str(cid)
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def _slashed_ids(result: dict) -> "set[str]":
    """Executor ids that were slashed (or wouldSlash) per the applied summary.

    The settle envelope carries an applied summary with per-claimant slash flags.
    We accept several shapes fail-closed:
      - result["slashed"] / result["wouldSlash"]: list of ids OR list of
        {claimant:{id}} OR {addr, amount} (real-slash envelope) OR {id: bool}.
      - result["rankings"][*] entries carrying slashed / wouldSlash booleans.
      - result["summary"] / result["applied"] nested copies of the above.
    """
    ids: set[str] = set()
    if not isinstance(result, dict):
        return ids

    def _harvest_list(value) -> None:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict):
                    claimant = item.get("claimant")
                    if isinstance(claimant, dict) and claimant.get("id") is not None:
                        ids.add(str(claimant["id"]))
                    elif item.get("id") is not None:
                        ids.add(str(item["id"]))
                    elif item.get("addr") is not None:
                        # Real-slash mode (balanceLedger.ts:506):
                        # applied.slashed.push({ addr, amount }). The executor id
                        # lives in `addr`, not `claimant.id`/`id`, so it must be
                        # harvested here or genuine --enforce-slash slashes are lost.
                        ids.add(str(item["addr"]))
        elif isinstance(value, dict):
            for k, v in value.items():
                if v:
                    ids.add(str(k))

    # Direct + nested containers.
    for container in (result, result.get("summary"), result.get("applied")):
        if not isinstance(container, dict):
            continue
        _harvest_list(container.get("slashed"))
        _harvest_list(container.get("wouldSlash"))

    # Per-ranking flags.
    rankings = result.get("rankings")
    if isinstance(rankings, list):
        for entry in rankings:
            if not isinstance(entry, dict):
                continue
            if entry.get("slashed") or entry.get("wouldSlash"):
                claimant = entry.get("claimant")
                if isinstance(claimant, dict) and claimant.get("id") is not None:
                    ids.add(str(claimant["id"]))

    return ids


def _bounty_amount(result: dict) -> float:
    """The settled cost / bounty awarded to the winner, fail-closed to 0.

    Looks at the common envelope shapes: result.bountyAmount / result.settledCost
    / result.summary.bountyAmount / winner.payout / winner.settledCost.

    Fix 6/7: NaN and negative values are clamped to 0.0 so the snapshot never
    contains a literal NaN token (invalid JSON for strict parsers) and cumulative
    settled_cost is never corrupted by a negative bounty.
    """
    def _safe_val(v) -> "float | None":
        """Return float(v) only if finite and non-negative; else None (skip)."""
        if v is None:
            return None
        fv = float(v)
        if math.isfinite(fv) and fv >= 0:
            return fv
        return None  # NaN, Inf, or negative → skip

    if not isinstance(result, dict):
        return 0.0
    for key in ("settledCost", "bountyAmount", "settled_cost", "bounty_amount", "bounty"):
        raw = _as_number(result.get(key))
        val = _safe_val(raw)
        if val is not None:
            return val
    summary = result.get("summary")
    if isinstance(summary, dict):
        for key in ("settledCost", "bountyAmount"):
            raw = _as_number(summary.get(key))
            val = _safe_val(raw)
            if val is not None:
                return val
    winner = result.get("winner")
    if isinstance(winner, dict):
        for key in ("payout", "settledCost", "bountyAmount"):
            raw = _as_number(winner.get(key))
            val = _safe_val(raw)
            if val is not None:
                return val
    return 0.0


# ─── Snapshot fold ────────────────────────────────────────────────────────────

def _empty_record() -> dict:
    return {
        "n_jobs": 0,
        "n_wins": 0,
        "settled_cost": 0.0,
        "slashed": 0,
        "p50_latency_ms": None,
        "_latencies": [],
    }


def _load_snapshot(current: str) -> dict:
    """Parse the snapshot JSON content fail-closed (bad content → empty)."""
    if not current or not current.strip():
        return {}
    try:
        data = json.loads(current)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    records = data.get("records")
    return records if isinstance(records, dict) else {}


# ─── Public API ───────────────────────────────────────────────────────────────

def record_tournament(
    *,
    reputation_path,
    result: dict,
    task_class: str,
    now: str,
    latencies: "dict | None" = None,
) -> dict:
    """Fold one TRUSTED TournamentResult into the reputation store.

    Parameters
    ----------
    reputation_path:
        Path to the append-only ``.jsonl`` event log. The paired folded snapshot
        is derived as the sibling ``.json``.
    result:
        The settle envelope's TournamentResult. Has ``rankings`` (list of
        ``{claimant:{id}, rank, ...}``), ``winner`` (``{claimant:{id}}`` or null),
        plus the applied summary carrying ``slashed`` / ``wouldSlash``.

        Accepts EITHER the full settle envelope ``{ok, result, applied, ...}``
        (where ``applied`` is a sibling of ``result`` and carries the real
        ``slashed: [{addr, amount}]`` list in --enforce-slash mode) OR a
        result-object that has ``applied``/``wouldSlash`` merged in. ``slashed``
        is scanned in BOTH ``result`` top-level and ``result.applied``. NOTE: if
        only the bare inner ``result`` is passed (no ``applied`` key), real-mode
        slashes are invisible — wire the caller to pass the full envelope or a
        merged view.
    task_class:
        The task class these executors raced under (the reputation key's 2nd part).
    now:
        Injected ISO-8601 timestamp recorded on the event (no datetime.now()).
    latencies:
        Optional ``{executor_id: latency_ms}`` map. Each value updates that
        executor's p50.

    Returns
    -------
    The folded snapshot record-map (``{(executor_id, task_class): {...}}``) for
    the executors touched by THIS tournament, with public fields only.

    Trust note
    ----------
    The winner is read from ``result.winner.claimant.id`` ONLY — NEVER from any
    self-reported exit/field on a submission. A null winner records no win.
    """
    jsonl_path = Path(reputation_path)
    snapshot_path = _snapshot_path_for(jsonl_path)

    task_class = str(task_class)
    latencies = latencies if isinstance(latencies, dict) else {}

    participants = _participant_ids(result)
    winner_id = _winner_id(result)
    slashed = _slashed_ids(result)
    bounty = _bounty_amount(result)

    # Ensure the winner counts as a participant even if rankings omitted it
    # (a trusted win implies participation).
    ordered_participants = list(participants)
    if winner_id is not None and winner_id not in ordered_participants:
        ordered_participants.append(winner_id)

    # ── 1. Append the jsonl event ─────────────────────────────────────────────
    event = {
        "ts": now,
        "task_class": task_class,
        "winner": winner_id,           # TRUSTED
        "participants": ordered_participants,
        "slashed": sorted(slashed),
        "settled_cost": bounty,
        "latencies": {str(k): v for k, v in latencies.items()},
    }
    event_line = json.dumps(event, default=str) + "\n"

    def _append(current: str) -> str:
        separator = "" if not current or current.endswith("\n") else "\n"
        return current + separator + event_line

    locked_update(jsonl_path, _append)

    # ── 2. Fold into the snapshot ─────────────────────────────────────────────
    touched: dict[str, dict] = {}

    def _fold(current: str) -> str:
        records = _load_snapshot(current)

        for executor_id in ordered_participants:
            key = _snapshot_key(executor_id, task_class)
            rec = records.get(key)
            if not isinstance(rec, dict):
                rec = _empty_record()
            else:
                # Normalize an existing record fail-closed.
                rec = {
                    "n_jobs": _as_int(rec.get("n_jobs")),
                    "n_wins": _as_int(rec.get("n_wins")),
                    "settled_cost": float(_as_number(rec.get("settled_cost")) or 0.0),
                    "slashed": _as_int(rec.get("slashed")),
                    "p50_latency_ms": rec.get("p50_latency_ms"),
                    "_latencies": [
                        v for v in (rec.get("_latencies") or [])
                        if _as_number(v) is not None
                    ][-_LATENCY_WINDOW:],
                }

            # Every participating executor: n_jobs += 1.
            rec["n_jobs"] += 1

            # Winner (TRUSTED): n_wins += 1 and add the settled cost/bounty.
            if winner_id is not None and executor_id == winner_id:
                rec["n_wins"] += 1
                rec["settled_cost"] += bounty

            # Slashed/wouldSlash: slashed += 1.
            if executor_id in slashed:
                rec["slashed"] += 1

            # p50 latency from this tournament's measurement, if provided.
            lat = _as_number(latencies.get(executor_id))
            if lat is not None:
                rec["_latencies"].append(lat)
                # Bound the retained tail so the snapshot does not grow without
                # limit over a long-running fleet (keep the most recent window).
                if len(rec["_latencies"]) > _LATENCY_WINDOW:
                    rec["_latencies"] = rec["_latencies"][-_LATENCY_WINDOW:]
                rec["p50_latency_ms"] = _p50(rec["_latencies"])

            records[key] = rec
            touched[key] = rec

        payload = {"records": records, "updated_at": now}
        return json.dumps(payload, indent=2, default=str)

    locked_update(snapshot_path, _fold)

    # Return public view of the touched records.
    return {
        key: {
            "n_jobs": rec["n_jobs"],
            "n_wins": rec["n_wins"],
            "win_rate": (rec["n_wins"] / rec["n_jobs"]) if rec["n_jobs"] else 0.0,
            "settled_cost": rec["settled_cost"],
            "slashed": rec["slashed"],
            "p50_latency_ms": rec["p50_latency_ms"],
        }
        for key, rec in touched.items()
    }


def summarize_reputation(reputation_path) -> dict:
    """Read back the folded snapshot keyed by ``(executor_id, task_class)``.

    Returns ``{(executor_id, task_class): {n_jobs, n_wins, win_rate,
    settled_cost, slashed, p50_latency_ms}}``. The tuple key is what the read-back
    ``summarize_telemetry`` never gave. Missing/garbage snapshot → empty dict
    (fail-closed).
    """
    snapshot_path = _snapshot_path_for(Path(reputation_path))
    if not snapshot_path.is_file():
        return {}
    records = _load_snapshot(snapshot_path.read_text())

    out: dict = {}
    for key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        executor_id, task_class = _split_key(key)
        n_jobs = _as_int(rec.get("n_jobs"))
        n_wins = _as_int(rec.get("n_wins"))
        out[(executor_id, task_class)] = {
            "n_jobs": n_jobs,
            "n_wins": n_wins,
            "win_rate": (n_wins / n_jobs) if n_jobs else 0.0,
            "settled_cost": float(_as_number(rec.get("settled_cost")) or 0.0),
            "slashed": _as_int(rec.get("slashed")),
            "p50_latency_ms": rec.get("p50_latency_ms"),
        }
    return out


def _task_class_of(task: dict) -> str:
    """Resolve the reputation task_class for a task.

    Prefers an explicit ``task_class`` field; falls back to the fleet complexity
    tier so reputation buckets align with routing tiers.
    """
    if isinstance(task, dict):
        explicit = task.get("task_class")
        if isinstance(explicit, str) and explicit:
            return explicit
    try:
        return fleet.task_tier(task)
    except Exception:  # noqa: BLE001 — fail-closed to a safe default bucket.
        return "standard"


def route_with_reputation(
    *,
    task: dict,
    config: dict,
    reputation_path,
    candidates: "list[str]",
    now: str,
    _route: Callable = fleet.route_task,
) -> dict:
    """Pick an executor via UCB1 over reputation, keeping cold-start OPEN.

    For the task's ``task_class``, each candidate's score is::

        score = win_rate + sqrt(2 * ln(total_jobs + 1) / n_executor_jobs)

    where ``total_jobs`` is the sum of n_jobs across the candidates for this
    task_class, and ``n_executor_jobs`` is the candidate's own n_jobs. An UNSEEN
    executor (``n_executor_jobs == 0``) scores ``+inf`` and is ALWAYS sampled —
    cold-start stays open; a new cheap model is NEVER zero-weighted or gated out.

    Parameters
    ----------
    task:
        The task dict (provides ``task_class`` / complexity tier).
    config:
        Fleet config (passed through to ``_route`` for the reference route).
    reputation_path:
        Path to the reputation jsonl (snapshot derived as sibling .json).
    candidates:
        Executor ids in contention (MUST include the cheap goose tier so it can
        be explored). Empty/garbage entries are ignored.
    now:
        Injected timestamp (unused in scoring; kept for signature symmetry and
        determinism guarantees — no clock is read internally).
    _route:
        Injectable reference router (default ``fleet.route_task``) used ONLY to
        compute ``base_route`` as a tier-appropriate fallback/reference. It does
        NOT gate the reputation choice.

    Returns
    -------
    dict with:
      - ``chosen``: the selected executor id.
      - ``scores``: ``{executor_id: score}`` (``float('inf')`` for unseen).
      - ``exploring``: True when the chosen executor is an unseen/low-n explore
        pick (n_executor_jobs == 0).
      - ``base_route``: the ``_route`` reference result (for callers; may be None
        if the reference router errors — never fatal here).
    """
    summary = summarize_reputation(reputation_path)
    task_class = _task_class_of(task)

    # Reference route (fail-closed: never let a reference error gate routing).
    try:
        base_route = _route(task, config)
    except Exception:  # noqa: BLE001
        base_route = None

    clean_candidates = [c for c in (candidates or []) if isinstance(c, str) and c]

    # n_jobs per candidate for THIS task_class; total over candidates.
    per_jobs: dict[str, int] = {}
    per_winrate: dict[str, float] = {}
    for cid in clean_candidates:
        rec = summary.get((cid, task_class))
        n_jobs = _as_int(rec.get("n_jobs")) if isinstance(rec, dict) else 0
        per_jobs[cid] = n_jobs
        per_winrate[cid] = float(rec.get("win_rate", 0.0)) if isinstance(rec, dict) else 0.0

    total_jobs = sum(per_jobs.values())
    ln_term = math.log(total_jobs + 1)

    scores: dict[str, float] = {}
    for cid in clean_candidates:
        n = per_jobs[cid]
        if n == 0:
            # Cold-start: NEVER zero-weight an unseen executor — always sampled.
            scores[cid] = math.inf
        else:
            exploration = math.sqrt(2.0 * ln_term / n)
            scores[cid] = per_winrate[cid] + exploration

    chosen = None
    if scores:
        # Deterministic tie-break: highest score, then input order.
        chosen = max(clean_candidates, key=lambda c: (scores[c], -clean_candidates.index(c)))

    exploring = bool(chosen is not None and per_jobs.get(chosen, 0) == 0)

    return {
        "chosen": chosen,
        "scores": scores,
        "exploring": exploring,
        "base_route": base_route,
    }
