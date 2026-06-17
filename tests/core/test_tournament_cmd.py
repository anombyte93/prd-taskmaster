"""Tournament orchestration command tests — all adapters injected, NO live launcher/oracle/podman.

Coverage:
  TC1. happy end-to-end (stubbed): 3 racers spawn, commit-reveal, adjudicate, settle, reputation.
       Assert: roster built (admission persisted), collected 3, submissions.json written,
       _settle called, record_tournament updated reputation (winner has n_wins>0),
       anti-sybil slots released (operators.json entries inactive), summary settled_ok=True,
       winner="r1".
  TC2. settle fail-closed: _settle returns ok:false → summary settled_ok=False, NO winner
       recorded in reputation, slots STILL released.
  TC3. partial collect: one racer fails hash verification → only valid racers adjudicated;
       summary rejected non-empty.
  TC4. release-on-crash: _settle raises RuntimeError → run_tournament RETURNS (never raises),
       summary settled_ok=False, settle_envelope_stage="orchestration_crashed", slots freed.
  TC5. status: after a run, cmd_tournament_status (via summarize_reputation) returns the
       recorded reputation.
  TC8. zero racers collected → summary stage="no_racers_collected", settled_ok=False,
       _settle NOT called, slots released.
  TC9. slash data preserved → --enforce-slash settle envelope with non-empty applied.slashed
       increments the slashed executor's slashed count in reputation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from prd_taskmaster.tournament.collect import FakeClock
from prd_taskmaster.tournament.cmd import run_tournament
from prd_taskmaster.reputation import summarize_reputation


# ─── Constants ────────────────────────────────────────────────────────────────

NOW = "2026-06-17T00:00:00+00:00"
JOB_ID = "test-job-001"
CARD_ID = "task-7"
BASE_REF = "deadbeef1234"
MODELS = ["claude:sonnet", "claude:haiku", "openrouter:gpt-5"]


# ─── Stub factories ───────────────────────────────────────────────────────────

def _make_spawn_fn(models=MODELS, job_id=JOB_ID):
    """Return a _spawn_fn stub that returns a valid handle for each racer.

    The handle shape mimics what the real launcher returns: claimant_id +
    session_id (NOT session_name — the orchestrator normalises this).
    worktree_path is also set so collect can do the recompute.
    """
    def _stub(spec):
        return {
            "claimant_id": spec.claimant_id,
            "session_id": spec.claimant_id,  # launcher returns session_id
            "worktree_path": f"/tmp/worktrees/{spec.claimant_id}",
            "spawned": True,
        }
    return _stub


def _make_inbox_read(committed_handles, *, job_id=JOB_ID, fake_hash="aabbcc112233" * 5):
    """Return an _inbox_read stub that returns commit messages for all claimants.

    committed_handles: list of claimant_id strings that should commit.
    fake_hash: the committed hash value (must match _compute_hash stub).
    """
    def _stub(*, job_id=job_id):
        return [
            {
                "job_id": job_id,
                "claimant_id": cid,
                "commit_sha": f"sha_{cid}",
                "commit_hash": fake_hash,
            }
            for cid in committed_handles
        ]
    return _stub


def _make_dispatch_reveal(*, fake_hash="aabbcc112233" * 5):
    """Return a _dispatch_reveal stub that returns a valid reveal for each racer."""
    def _stub(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": f"sha_{claimant_id}",
            "self_reported_exit": 0,
        }
    return _stub


def _make_compute_hash(fake_hash="aabbcc112233" * 5):
    """Return a _compute_hash stub that always returns fake_hash."""
    def _stub(worktree, base_ref, commit_sha):
        return fake_hash
    return _stub


def _make_settle_ok(winner_claimant_id="r1"):
    """Return a _settle stub that returns ok:true with a canned result."""
    def _stub(*, job_dir, enforce_slash=False):
        return {
            "ok": True,
            "result": {
                "winner": {"claimant": {"id": winner_claimant_id}},
                "rankings": [
                    {"claimant": {"id": winner_claimant_id}, "rank": 1},
                ],
                "settledCost": 100,
            },
            "applied": {
                "slashed": [],
                "wouldSlash": [],
            },
            "stage": "done",
        }
    return _stub


def _make_settle_fail(stage="apply_settlement"):
    """Return a _settle stub that returns ok:false."""
    def _stub(*, job_dir, enforce_slash=False):
        return {
            "ok": False,
            "stage": stage,
            "error": "settlement failed",
        }
    return _stub


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_roster_claimant_ids(job_id=JOB_ID, models=MODELS):
    """Derive the expected claimant_ids for a roster (mirrors spawn._build_racer_prompt)."""
    return [f"{job_id}:{i}:{model}" for i, model in enumerate(models)]


def _make_card(tmp_path: Path) -> Path:
    """Write a minimal card JSON to tmp_path."""
    card = tmp_path / "task-7.json"
    card.write_text(json.dumps({
        "taskId": "7",
        "cardId": CARD_ID,
        "spec": "Implement something",
        "acceptance": ["criterion 1"],
    }))
    return card


def _run_args(tmp_path: Path, *, models=None, settle_fn=None, partial_commit_cids=None):
    """Build common kwargs for run_tournament with default stubs."""
    models_ = models or MODELS
    fake_hash = "aabbcc112233" * 5  # 60 hex chars — valid sha256-like

    # Roster claimant_ids depend on model list.
    all_cids = _build_roster_claimant_ids(JOB_ID, models_)
    committed_cids = partial_commit_cids if partial_commit_cids is not None else all_cids

    return dict(
        card_path=_make_card(tmp_path),
        task_id="7",
        base_ref=BASE_REF,
        models=models_,
        job_id=JOB_ID,
        card_id=CARD_ID,
        bounty_amount=100,
        job_poster="molle.atlas@gmail.com",
        job_dir=tmp_path / "jobs" / JOB_ID,
        held_root=tmp_path / "held",
        operators_path=tmp_path / "operators.json",
        reputation_path=tmp_path / "reputation.jsonl",
        orchestrator_session="orch-session-001",
        task_class="coding",
        task_prompt="Build the tournament orchestrator",
        card_ref=CARD_ID,
        now=NOW,
        window_s=0.01,   # tiny window so the test does not wait
        enforce_slash=False,
        _spawn_fn=_make_spawn_fn(models_, JOB_ID),
        _inbox_read=_make_inbox_read(committed_cids, job_id=JOB_ID, fake_hash=fake_hash),
        _dispatch_reveal=_make_dispatch_reveal(fake_hash=fake_hash),
        _compute_hash=_make_compute_hash(fake_hash),
        _settle=settle_fn or _make_settle_ok(),
        clock=FakeClock(start=0.0),
    )


# ─── TC1: Happy end-to-end ────────────────────────────────────────────────────

def test_tc1_happy_end_to_end(tmp_path):
    """TC1: 3 racers all pass — roster built, collected 3, settled ok, reputation recorded."""
    kwargs = _run_args(tmp_path)

    # Wrap _settle to track calls.
    settle_calls = []
    original_settle = kwargs["_settle"]
    def settle_spy(*, job_dir, enforce_slash=False):
        settle_calls.append({"job_dir": job_dir, "enforce_slash": enforce_slash})
        return original_settle(job_dir=job_dir, enforce_slash=enforce_slash)
    kwargs["_settle"] = settle_spy

    summary = run_tournament(**kwargs)

    # Roster and spawn.
    assert summary["roster_size"] == 3
    assert summary["spawned"] == 3

    # Collected all 3 — no rejected.
    assert summary["collected"] == 3
    assert summary["rejected"] == []

    # Settle was called exactly once.
    assert len(settle_calls) == 1

    # Summary correct.
    assert summary["settled_ok"] is True
    assert summary["winner"] == "r1"
    assert summary["reputation_recorded"] is True

    # submissions.json was written by adjudicate_job.
    job_dir = Path(kwargs["job_dir"])
    submissions_path = job_dir / "submissions.json"
    assert submissions_path.is_file(), "submissions.json must exist"
    subs = json.loads(submissions_path.read_text())
    assert isinstance(subs, list)
    assert len(subs) == 3  # one per collected racer

    # Reputation recorded: winner "r1" has n_wins >= 1 in the snapshot.
    rep = summarize_reputation(kwargs["reputation_path"])
    r1_entries = {k: v for k, v in rep.items() if k[0] == "r1"}
    assert r1_entries, "winner r1 must appear in reputation"
    for _, stats in r1_entries.items():
        assert stats["n_wins"] >= 1

    # Anti-sybil slots released: ALL operators.json entries for the job are inactive.
    ops_path = Path(kwargs["operators_path"])
    assert ops_path.is_file()
    ops = json.loads(ops_path.read_text())
    active_entries = [
        e for e in ops.get("entries", [])
        if e.get("job_id") == JOB_ID and e.get("active", False)
    ]
    assert active_entries == [], f"Active entries after release: {active_entries}"


# ─── TC2: Settle fail-closed ─────────────────────────────────────────────────

def test_tc2_settle_fail_closed(tmp_path):
    """TC2: settle returns ok:false → settled_ok=False, no winner in reputation, slots released."""
    kwargs = _run_args(tmp_path, settle_fn=_make_settle_fail("apply_settlement"))

    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is False
    assert summary["winner"] is None
    assert summary["reputation_recorded"] is False
    assert summary["settle_envelope_stage"] == "apply_settlement"

    # Reputation snapshot should NOT have any entries (nothing was recorded).
    rep = summarize_reputation(kwargs["reputation_path"])
    assert rep == {}, f"No reputation should be recorded on settle failure; got {rep}"

    # Slots released even on settle failure.
    ops_path = Path(kwargs["operators_path"])
    if ops_path.is_file():
        ops = json.loads(ops_path.read_text())
        active_entries = [
            e for e in ops.get("entries", [])
            if e.get("job_id") == JOB_ID and e.get("active", False)
        ]
        assert active_entries == []


# ─── TC3: Partial collect (hash mismatch for one racer) ──────────────────────

def test_tc3_partial_collect_hash_mismatch(tmp_path):
    """TC3: one racer has a mismatched hash → only 2 collected, rejected non-empty."""
    models = MODELS  # 3 racers
    all_cids = _build_roster_claimant_ids(JOB_ID, models)
    good_cids = all_cids[:2]
    bad_cid = all_cids[2]

    good_hash = "aabbcc112233" * 5
    bad_hash_committed = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    # The bad racer commits with bad_hash, but _compute_hash always returns good_hash.
    # This causes a hash_mismatch rejection for the bad racer.
    def _mixed_inbox_read(*, job_id):
        msgs = [
            {
                "job_id": job_id,
                "claimant_id": cid,
                "commit_sha": f"sha_{cid}",
                "commit_hash": good_hash,
            }
            for cid in good_cids
        ]
        msgs.append({
            "job_id": job_id,
            "claimant_id": bad_cid,
            "commit_sha": f"sha_{bad_cid}",
            "commit_hash": bad_hash_committed,  # different from recomputed
        })
        return msgs

    kwargs = _run_args(tmp_path)
    kwargs["_inbox_read"] = _mixed_inbox_read
    # _compute_hash always returns good_hash → bad_cid's committed hash won't match
    kwargs["_compute_hash"] = _make_compute_hash(good_hash)

    summary = run_tournament(**kwargs)

    # 2 collected, 1 rejected.
    assert summary["collected"] == 2
    assert len(summary["rejected"]) == 1
    assert summary["rejected"][0]["claimant_id"] == bad_cid
    assert summary["rejected"][0]["reason"] == "hash_mismatch"

    # submissions.json has only the 2 good racers.
    job_dir = Path(kwargs["job_dir"])
    submissions_path = job_dir / "submissions.json"
    assert submissions_path.is_file()
    subs = json.loads(submissions_path.read_text())
    assert len(subs) == 2


# ─── TC4: Release on crash ────────────────────────────────────────────────────

def test_tc4_release_on_crash(tmp_path):
    """TC4: _settle raises → run_tournament RETURNS (never propagates), summary captures crash,
    settle_envelope_stage="orchestration_crashed", settled_ok=False, slots freed.
    """
    def _crashing_settle(*, job_dir, enforce_slash=False):
        raise RuntimeError("Simulated settle crash")

    kwargs = _run_args(tmp_path, settle_fn=_crashing_settle)

    # run_tournament must NOT raise — it must return a summary with the crash captured.
    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is False, "settled_ok must be False on crash"
    assert summary["settle_envelope_stage"] == "orchestration_crashed", (
        f"stage must be 'orchestration_crashed'; got {summary.get('settle_envelope_stage')!r}"
    )
    assert "error" in summary, "summary must contain 'error' key on crash"
    assert "Simulated settle crash" in summary["error"]
    assert summary["reputation_recorded"] is False

    # The critical invariant: slots released.
    ops_path = Path(kwargs["operators_path"])
    if ops_path.is_file():
        ops = json.loads(ops_path.read_text())
        active_entries = [
            e for e in ops.get("entries", [])
            if e.get("job_id") == JOB_ID and e.get("active", False)
        ]
        assert active_entries == [], f"Slots must be freed even on crash; active: {active_entries}"


# ─── TC5: Status after a run ─────────────────────────────────────────────────

def test_tc5_status_after_run(tmp_path):
    """TC5: after a successful run, summarize_reputation shows the winner's record."""
    kwargs = _run_args(tmp_path)
    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is True
    assert summary["winner"] == "r1"

    # Verify via summarize_reputation (the same function cmd_tournament_status uses).
    rep = summarize_reputation(kwargs["reputation_path"])
    assert rep, "Reputation must be non-empty after a successful run"

    # At minimum, r1 must appear with n_wins=1 for the coding task_class.
    r1_coding = rep.get(("r1", "coding"))
    assert r1_coding is not None, "r1 must have a coding entry"
    assert r1_coding["n_wins"] == 1
    assert r1_coding["n_jobs"] >= 1
    assert r1_coding["win_rate"] > 0


# ─── TC6: Seed bank hook is called ───────────────────────────────────────────

def test_tc6_seed_bank_called(tmp_path):
    """TC6: when _seed_bank is provided, it is called before settle."""
    seed_calls = []

    def _seed_bank(*, job_dir, job, racers):
        seed_calls.append({"job_dir": str(job_dir), "job": job, "racer_count": len(racers)})

    kwargs = _run_args(tmp_path)
    kwargs["_seed_bank"] = _seed_bank

    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is True
    assert len(seed_calls) == 1
    assert seed_calls[0]["racer_count"] == 3  # all 3 collected
    assert seed_calls[0]["job"]["jobId"] == JOB_ID


# ─── TC7: Roster size + spawned count in summary ─────────────────────────────

def test_tc7_summary_counts(tmp_path):
    """TC7: summary roster_size == len(models), spawned == how many succeeded."""
    models_2 = MODELS[:2]  # Only 2 models
    all_cids = _build_roster_claimant_ids(JOB_ID, models_2)
    fake_hash = "aabbcc112233" * 5

    kwargs = dict(
        card_path=_make_card(tmp_path),
        task_id="7",
        base_ref=BASE_REF,
        models=models_2,
        job_id=JOB_ID,
        card_id=CARD_ID,
        bounty_amount=50,
        job_poster="test@example.com",
        job_dir=tmp_path / "jobs" / JOB_ID,
        held_root=tmp_path / "held",
        operators_path=tmp_path / "operators.json",
        reputation_path=tmp_path / "reputation.jsonl",
        orchestrator_session="",
        task_class="research",
        task_prompt="Research task",
        card_ref=CARD_ID,
        now=NOW,
        window_s=0.01,
        enforce_slash=False,
        _spawn_fn=_make_spawn_fn(models_2, JOB_ID),
        _inbox_read=_make_inbox_read(all_cids, job_id=JOB_ID, fake_hash=fake_hash),
        _dispatch_reveal=_make_dispatch_reveal(fake_hash=fake_hash),
        _compute_hash=_make_compute_hash(fake_hash),
        _settle=_make_settle_ok(),
        clock=FakeClock(start=0.0),
    )

    summary = run_tournament(**kwargs)
    assert summary["roster_size"] == 2
    assert summary["spawned"] == 2
    assert summary["collected"] == 2


# ─── TC8: Zero racers collected → short-circuit ───────────────────────────────

def test_tc8_zero_racers_collected(tmp_path):
    """TC8: all racers rejected → stage=no_racers_collected, settle NOT called, slots released."""
    settle_calls = []

    def _never_settle(*, job_dir, enforce_slash=False):
        settle_calls.append(True)
        return {"ok": True, "stage": "done", "result": {}}

    # inbox_read returns no commits → nobody commits → nobody collects.
    def _empty_inbox(*, job_id):
        return []  # no commits at all

    kwargs = _run_args(tmp_path, settle_fn=_never_settle)
    kwargs["_inbox_read"] = _empty_inbox

    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is False
    assert summary["settle_envelope_stage"] == "no_racers_collected"
    assert summary["collected"] == 0
    assert len(settle_calls) == 0, "_settle must NOT be called when no racers collected"
    assert summary["reputation_recorded"] is False

    # Slots still released even though we short-circuited.
    ops_path = Path(kwargs["operators_path"])
    if ops_path.is_file():
        ops = json.loads(ops_path.read_text())
        active_entries = [
            e for e in ops.get("entries", [])
            if e.get("job_id") == JOB_ID and e.get("active", False)
        ]
        assert active_entries == [], f"Slots must be freed even on zero-racer path; active: {active_entries}"


# ─── TC9: Slash data preserved to reputation ─────────────────────────────────

def test_tc9_slash_data_preserved_to_reputation(tmp_path):
    """TC9: settle envelope with applied.slashed non-empty → executor's slashed count increments."""
    slashed_executor = "r1"  # this is the winner too — slash still counts

    def _slash_settle(*, job_dir, enforce_slash=False):
        return {
            "ok": True,
            "stage": "done",
            "result": {
                "winner": {"claimant": {"id": slashed_executor}},
                "rankings": [
                    {"claimant": {"id": slashed_executor}, "rank": 1},
                    {"claimant": {"id": "r2"}, "rank": 2},
                ],
                "settledCost": 100,
            },
            "applied": {
                # Real --enforce-slash shape: {addr, amount}
                "slashed": [{"addr": slashed_executor, "amount": 50}],
                "wouldSlash": [],
            },
        }

    kwargs = _run_args(tmp_path, settle_fn=_slash_settle)
    kwargs["enforce_slash"] = True

    summary = run_tournament(**kwargs)

    assert summary["settled_ok"] is True
    assert summary["reputation_recorded"] is True

    rep = summarize_reputation(kwargs["reputation_path"])

    # The slashed executor must have slashed >= 1.
    r1_coding = rep.get((slashed_executor, "coding"))
    assert r1_coding is not None, f"{slashed_executor} must appear in reputation"
    assert r1_coding["slashed"] >= 1, (
        f"slashed executor {slashed_executor} must have slashed>=1; got {r1_coding['slashed']}"
    )
