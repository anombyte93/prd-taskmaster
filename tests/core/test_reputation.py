"""Trusted reputation store + UCB router tests — no live infra.

All I/O is to a tmp_path-scoped jsonl/snapshot pair; the router takes an injected
reference _route stub so fleet/availability is never touched live.

Coverage:
  R1. record_tournament: winner gets n_wins++ AND all participants n_jobs++
      (per-executor asserts); settled cost added to the winner only.
  R2. record_tournament: null winner → no win recorded, but n_jobs still ++.
  R3. record_tournament: an executor in slashed → slashed++.
  R4. Trust: the recorded winner is result.winner.claimant.id, NOT any
      self-reported field on a submission.
  R5. jsonl + snapshot are BOTH written; summarize_reputation reads back the
      correct win_rate (n_wins / n_jobs).
  R6. UCB exploit: a high-win-rate, many-jobs executor is chosen when every
      candidate has history (no unseen) — exploitation works.
  R7. UCB cold-start: an unseen executor (n=0) is ALWAYS sampled (exploring=True,
      score == +inf) even against a strong seen incumbent — cold-start open.
  R8. A task_class with ZERO history → every candidate is an explore pick
      (all scores +inf, exploring=True).
  R9. Never zero-weight: an unseen cheap candidate's score (+inf) beats a
      mediocre seen one; the cheap model is sampled.
  R10. p50 latency folds from the latencies map.
  R11. Fail-closed: garbage snapshot content → summarize_reputation returns {}.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from prd_taskmaster.reputation import (
    record_tournament,
    summarize_reputation,
    route_with_reputation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    *,
    ranked,
    winner_id=None,
    slashed=None,
    bounty=0,
    self_reported_winner=None,
):
    """Build a TournamentResult-shaped dict.

    ranked: list of executor ids (rank order).
    winner_id: TRUSTED winner executor id, or None.
    slashed: list of executor ids flagged slashed.
    self_reported_winner: a DIFFERENT id stuffed into self-reported fields to
        prove the store ignores it.
    """
    rankings = []
    for rank, eid in enumerate(ranked, start=1):
        entry = {"claimant": {"id": eid}, "rank": rank}
        if self_reported_winner is not None:
            # Adversarial: each submission claims IT won via a self-report field.
            entry["selfReportedExit"] = 0
            entry["selfClaimedWinner"] = self_reported_winner
        rankings.append(entry)

    result = {
        "rankings": rankings,
        "winner": {"claimant": {"id": winner_id}} if winner_id is not None else None,
        "slashed": list(slashed or []),
        "settledCost": bounty,
    }
    return result


def _rep_path(tmp_path: Path) -> Path:
    return tmp_path / ".atlas-ai" / "reputation.jsonl"


# ---------------------------------------------------------------------------
# record_tournament
# ---------------------------------------------------------------------------

def test_winner_gets_win_all_participants_get_job(tmp_path):
    """R1: winner n_wins++ AND every participant n_jobs++; cost to winner only."""
    path = _rep_path(tmp_path)
    record_tournament(
        reputation_path=path,
        result=_result(ranked=["alice", "bob", "carol"], winner_id="alice", bounty=100),
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )

    summary = summarize_reputation(path)
    assert summary[("alice", "standard")]["n_jobs"] == 1
    assert summary[("alice", "standard")]["n_wins"] == 1
    assert summary[("alice", "standard")]["settled_cost"] == 100
    # Non-winners participated but did not win.
    assert summary[("bob", "standard")]["n_jobs"] == 1
    assert summary[("bob", "standard")]["n_wins"] == 0
    assert summary[("bob", "standard")]["settled_cost"] == 0
    assert summary[("carol", "standard")]["n_jobs"] == 1
    assert summary[("carol", "standard")]["n_wins"] == 0


def test_null_winner_records_no_win_but_jobs_increment(tmp_path):
    """R2: a null winner → nobody wins, but n_jobs still increments."""
    path = _rep_path(tmp_path)
    record_tournament(
        reputation_path=path,
        result=_result(ranked=["alice", "bob"], winner_id=None, bounty=50),
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )

    summary = summarize_reputation(path)
    assert summary[("alice", "standard")]["n_jobs"] == 1
    assert summary[("alice", "standard")]["n_wins"] == 0
    assert summary[("bob", "standard")]["n_jobs"] == 1
    assert summary[("bob", "standard")]["n_wins"] == 0
    # No win → no settled cost anywhere.
    assert summary[("alice", "standard")]["settled_cost"] == 0
    assert summary[("bob", "standard")]["settled_cost"] == 0


def test_slashed_executor_gets_slashed_increment(tmp_path):
    """R3: an executor appearing in slashed → slashed++."""
    path = _rep_path(tmp_path)
    record_tournament(
        reputation_path=path,
        result=_result(
            ranked=["alice", "cheater"],
            winner_id="alice",
            slashed=["cheater"],
        ),
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )

    summary = summarize_reputation(path)
    assert summary[("cheater", "standard")]["slashed"] == 1
    assert summary[("cheater", "standard")]["n_jobs"] == 1
    assert summary[("cheater", "standard")]["n_wins"] == 0
    # Winner not slashed.
    assert summary[("alice", "standard")]["slashed"] == 0


def test_real_settle_envelope_slashed_addr_is_harvested(tmp_path):
    """R3b: the REAL settle envelope shape — applied.slashed: [{addr, amount}].

    Locks the contract to the TS source (balanceLedger.ts:382/506) rather than
    the test helper's simplified bare-id list. In --enforce-slash mode the slashed
    executor id lives in `addr` (NOT `claimant.id`/`id`); it must still increment
    `slashed`. Also carries the default-shadow `applied.wouldSlash` (claimant.id
    shape) which must be deduped to the SAME executor.
    """
    path = _rep_path(tmp_path)
    result = {
        "rankings": [
            {"claimant": {"id": "alice"}, "rank": 1},
            {"claimant": {"id": "cheater"}, "rank": 2},
        ],
        "winner": {"claimant": {"id": "alice"}},
        "applied": {
            # Real-slash mode: balanceLedger.ts pushes {addr, amount}.
            "slashed": [{"addr": "cheater", "amount": 5}],
            # Shadow-mode sibling, claimant.id shape, same executor.
            "wouldSlash": [
                {
                    "claimant": {"id": "cheater"},
                    "reason": "ORACLE_CONTRADICTS_CLAIM",
                    "amount": 5,
                }
            ],
        },
    }
    record_tournament(
        reputation_path=path,
        result=result,
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )

    summary = summarize_reputation(path)
    # The addr-shaped real slash IS harvested and counts exactly once.
    assert summary[("cheater", "standard")]["slashed"] == 1
    assert summary[("cheater", "standard")]["n_jobs"] == 1
    assert summary[("alice", "standard")]["slashed"] == 0


def test_trusted_winner_ignores_self_reported_field(tmp_path):
    """R4: recorded winner is result.winner.claimant.id, NOT a self-report.

    Every submission self-claims 'bob' won, but the TRUSTED winner is 'alice'.
    """
    path = _rep_path(tmp_path)
    record_tournament(
        reputation_path=path,
        result=_result(
            ranked=["alice", "bob"],
            winner_id="alice",            # TRUSTED
            self_reported_winner="bob",   # the lie
            bounty=10,
        ),
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )

    summary = summarize_reputation(path)
    # Trusted winner wins.
    assert summary[("alice", "standard")]["n_wins"] == 1
    assert summary[("alice", "standard")]["settled_cost"] == 10
    # The self-claimed 'winner' gets NO win.
    assert summary[("bob", "standard")]["n_wins"] == 0
    assert summary[("bob", "standard")]["settled_cost"] == 0


def test_jsonl_and_snapshot_both_written_and_win_rate(tmp_path):
    """R5: both files written; win_rate == n_wins/n_jobs after 2 tournaments."""
    path = _rep_path(tmp_path)
    snapshot = path.with_suffix(".json")

    # alice wins job 1, loses job 2 → 1/2.
    record_tournament(
        reputation_path=path,
        result=_result(ranked=["alice", "bob"], winner_id="alice"),
        task_class="standard",
        now="2026-06-17T00:00:00+00:00",
    )
    record_tournament(
        reputation_path=path,
        result=_result(ranked=["alice", "bob"], winner_id="bob"),
        task_class="standard",
        now="2026-06-17T00:00:01+00:00",
    )

    # jsonl: 2 event lines, each valid JSON.
    assert path.is_file()
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)  # parses

    # snapshot exists and parses.
    assert snapshot.is_file()
    json.loads(snapshot.read_text())

    summary = summarize_reputation(path)
    assert summary[("alice", "standard")]["n_jobs"] == 2
    assert summary[("alice", "standard")]["n_wins"] == 1
    assert summary[("alice", "standard")]["win_rate"] == pytest.approx(0.5)
    assert summary[("bob", "standard")]["n_jobs"] == 2
    assert summary[("bob", "standard")]["n_wins"] == 1
    assert summary[("bob", "standard")]["win_rate"] == pytest.approx(0.5)


def test_p50_latency_folds(tmp_path):
    """R10: p50 latency folds from the latencies map."""
    path = _rep_path(tmp_path)
    for i, lat in enumerate((100, 300, 200)):
        record_tournament(
            reputation_path=path,
            result=_result(ranked=["alice", "bob"], winner_id="alice"),
            task_class="standard",
            now=f"2026-06-17T00:00:0{i}+00:00",
            latencies={"alice": lat},
        )
    summary = summarize_reputation(path)
    # median of [100, 200, 300] (lower-of-two convention) == 200.
    assert summary[("alice", "standard")]["p50_latency_ms"] == 200


def test_latency_history_is_bounded(tmp_path):
    """R10b: raw latency history is capped so the snapshot can't grow unbounded.

    Folds many more samples than the retention window and asserts the persisted
    `_latencies` list is bounded to the most-recent window, while p50 stays the
    correct median over that retained tail.
    """
    from prd_taskmaster import reputation

    path = _rep_path(tmp_path)
    snapshot = path.with_suffix(".json")

    window = reputation._LATENCY_WINDOW
    total = window + 50
    for i in range(total):
        record_tournament(
            reputation_path=path,
            result=_result(ranked=["alice", "bob"], winner_id="alice"),
            task_class="standard",
            now=f"2026-06-17T00:00:00+00:0{i % 10}",
            latencies={"alice": float(i)},  # strictly increasing
        )

    # Persisted raw history is bounded to the retention window.
    records = json.loads(snapshot.read_text())["records"]
    key = next(k for k in records if k.startswith("alice"))
    assert len(records[key]["_latencies"]) == window

    # p50 stays correct over the retained tail (the last `window` samples,
    # i.e. values [50 .. total-1]; lower-of-two median).
    tail = list(range(total - window, total))
    expected = sorted(tail)[window // 2]
    summary = summarize_reputation(path)
    assert summary[("alice", "standard")]["p50_latency_ms"] == expected


def test_garbage_snapshot_is_fail_closed(tmp_path):
    """R11: a corrupt snapshot file → summarize_reputation returns {}."""
    path = _rep_path(tmp_path)
    snapshot = path.with_suffix(".json")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{ this is not json")
    assert summarize_reputation(path) == {}


# ---------------------------------------------------------------------------
# route_with_reputation — UCB
# ---------------------------------------------------------------------------

def _stub_route(task, config):
    """Reference router stub — returns a deterministic tier default."""
    return "claude:sonnet"


def _seed_history(path, *, winner, others, task_class, n, bounty=1):
    """Record n tournaments where `winner` always wins over `others`."""
    ranked = [winner, *others]
    for i in range(n):
        record_tournament(
            reputation_path=path,
            result=_result(ranked=ranked, winner_id=winner, bounty=bounty),
            task_class=task_class,
            now=f"2026-06-17T00:{i:02d}:00+00:00",
        )


def test_ucb_exploits_strong_seen_executor(tmp_path):
    """R6: with all candidates seen, the high-win-rate one is chosen (exploit)."""
    path = _rep_path(tmp_path)
    # 'champ' wins all 20; 'mid' participates (loses) all 20.
    _seed_history(path, winner="champ", others=["mid"], task_class="standard", n=20)

    task = {"id": 1, "task_class": "standard"}
    out = route_with_reputation(
        task=task,
        config={},
        reputation_path=path,
        candidates=["champ", "mid"],   # both seen, none unseen
        now="2026-06-17T01:00:00+00:00",
        _route=_stub_route,
    )

    assert out["chosen"] == "champ"
    assert out["exploring"] is False
    assert math.isfinite(out["scores"]["champ"])
    assert math.isfinite(out["scores"]["mid"])
    assert out["scores"]["champ"] > out["scores"]["mid"]
    assert out["base_route"] == "claude:sonnet"


def test_ucb_always_samples_unseen_coldstart(tmp_path):
    """R7: an unseen executor (n=0) is ALWAYS chosen over a strong seen one."""
    path = _rep_path(tmp_path)
    _seed_history(path, winner="champ", others=["mid"], task_class="standard", n=20)

    task = {"id": 1, "task_class": "standard"}
    out = route_with_reputation(
        task=task,
        config={},
        reputation_path=path,
        candidates=["champ", "goose-cheap"],   # goose-cheap is UNSEEN
        now="2026-06-17T01:00:00+00:00",
        _route=_stub_route,
    )

    assert out["chosen"] == "goose-cheap"
    assert out["exploring"] is True
    assert out["scores"]["goose-cheap"] == math.inf
    # The strong incumbent is finite → cold-start beats it.
    assert math.isfinite(out["scores"]["champ"])


def test_zero_history_task_class_all_explore(tmp_path):
    """R8: a task_class with zero history → every candidate is an explore pick."""
    path = _rep_path(tmp_path)
    # Seed history under a DIFFERENT task_class so this one is empty.
    _seed_history(path, winner="champ", others=["mid"], task_class="frontier", n=10)

    task = {"id": 1, "task_class": "standard"}  # no history here
    out = route_with_reputation(
        task=task,
        config={},
        reputation_path=path,
        candidates=["a", "b", "c"],
        now="2026-06-17T01:00:00+00:00",
        _route=_stub_route,
    )

    assert out["exploring"] is True
    assert all(out["scores"][c] == math.inf for c in ("a", "b", "c"))
    assert out["chosen"] in ("a", "b", "c")


def test_never_zero_weight_unseen_cheap_beats_mediocre_seen(tmp_path):
    """R9: an unseen cheap candidate (+inf) beats a mediocre seen one."""
    path = _rep_path(tmp_path)
    # 'mediocre' has a low win rate over its history.
    _seed_history(path, winner="other", others=["mediocre"], task_class="standard", n=8)

    task = {"id": 1, "task_class": "standard"}
    out = route_with_reputation(
        task=task,
        config={},
        reputation_path=path,
        candidates=["mediocre", "goose-cheap"],
        now="2026-06-17T01:00:00+00:00",
        _route=_stub_route,
    )

    # The unseen cheap model is NEVER zero-weighted — it wins on +inf.
    assert out["scores"]["goose-cheap"] == math.inf
    assert out["scores"]["goose-cheap"] > out["scores"]["mediocre"]
    assert out["chosen"] == "goose-cheap"
    assert out["exploring"] is True


def test_route_falls_back_when_reference_router_errors(tmp_path):
    """base_route is None (never fatal) when the reference router raises."""
    path = _rep_path(tmp_path)

    def _boom(task, config):
        raise RuntimeError("no backends")

    out = route_with_reputation(
        task={"id": 1, "task_class": "standard"},
        config={},
        reputation_path=path,
        candidates=["a", "b"],
        now="2026-06-17T01:00:00+00:00",
        _route=_boom,
    )
    assert out["base_route"] is None
    assert out["chosen"] in ("a", "b")


# ---------------------------------------------------------------------------
# Fix 6/7: _bounty_amount — NaN and negative values are clamped to 0.0
# ---------------------------------------------------------------------------

def test_nan_settled_cost_not_recorded_in_snapshot(tmp_path):
    """Fix 6: NaN settledCost in the result must fold to 0.0 (not serialized as NaN token)."""
    path = _rep_path(tmp_path)
    import math as _math

    # Use a result with NaN settledCost
    result = {
        "rankings": [{"claimant": {"id": "exec-a"}, "rank": 1}],
        "winner": {"claimant": {"id": "exec-a"}},
        "settledCost": float("nan"),
    }
    record_tournament(
        reputation_path=path,
        result=result,
        task_class="coding",
        now="2026-06-17T01:00:00+00:00",
    )

    # The snapshot must be valid JSON (no literal NaN token).
    snapshot_path = path.with_suffix(".json")
    assert snapshot_path.is_file()
    raw = snapshot_path.read_text()
    parsed = json.loads(raw)  # must not raise — NaN would break strict parsers

    # settled_cost must be 0.0 (clamped), not NaN.
    rep = summarize_reputation(path)
    entry = rep.get(("exec-a", "coding"))
    assert entry is not None
    assert _math.isfinite(entry["settled_cost"]), (
        f"settled_cost must be finite (not NaN); got {entry['settled_cost']}"
    )
    assert entry["settled_cost"] == 0.0, (
        f"NaN settledCost must be clamped to 0.0; got {entry['settled_cost']}"
    )


def test_negative_settled_cost_clamped_to_zero(tmp_path):
    """Fix 7: negative settledCost must be clamped to 0.0 (never corrupts cumulative cost)."""
    path = _rep_path(tmp_path)

    result = {
        "rankings": [{"claimant": {"id": "exec-b"}, "rank": 1}],
        "winner": {"claimant": {"id": "exec-b"}},
        "settledCost": -100,
    }
    record_tournament(
        reputation_path=path,
        result=result,
        task_class="coding",
        now="2026-06-17T01:00:00+00:00",
    )

    rep = summarize_reputation(path)
    entry = rep.get(("exec-b", "coding"))
    assert entry is not None
    assert entry["settled_cost"] == 0.0, (
        f"Negative settledCost must be clamped to 0.0; got {entry['settled_cost']}"
    )
