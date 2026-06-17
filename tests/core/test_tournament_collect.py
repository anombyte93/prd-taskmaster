"""Unit tests for prd_taskmaster.tournament.collect — the commit-reveal collector.

All external I/O is injected:
  - _inbox_read   : stub returning canned commit-phase messages.
  - _dispatch_reveal : stub returning canned reveal payloads.
  - _compute_hash : stub recomputing the diff hash (NO real git).
  - clock         : a FakeClock that fast-forwards monotonic time and sleeps
                    WITHOUT any real waiting (proves the loop never hangs).

No live launcher / git / sleep is ever touched.
"""
from __future__ import annotations

import pytest

from prd_taskmaster.tournament.collect import (
    Clock,
    CollectResult,
    FakeClock,
    RealClock,
    collect_tournament,
    default_inbox_adapter,
    default_reveal_adapter,
    _compute_diff_hash,
)
from prd_taskmaster.tournament.spawn import RacerSpec


# ─── Helpers ─────────────────────────────────────────────────────────────────


def make_spec(claimant_id: str, *, entry_fee_paid: int, fakery_stake: int) -> RacerSpec:
    """Build a RacerSpec carrying the fee fields the collector passes through."""
    return RacerSpec(
        claimant_id=claimant_id,
        operator_id=claimant_id,
        model="claude:sonnet",
        job_id="job-1",
        prompt="do the thing",
        isolation="worktree",
        report_to="orch-inbox",
        entry_fee_paid=entry_fee_paid,
        fakery_stake=fakery_stake,
    )


def make_handles(claimant_ids):
    return [
        {
            "claimant_id": cid,
            "session_name": f"sess-{cid}",
            "worktree_path": f"/wt/{cid}",
        }
        for cid in claimant_ids
    ]


def commit_msg(job_id, claimant_id, commit_sha, commit_hash):
    return {
        "job_id": job_id,
        "claimant_id": claimant_id,
        "commit_sha": commit_sha,
        "commit_hash": commit_hash,
    }


# A FakeClock whose monotonic clock starts at 0 and advances on every sleep
# (and a poll that registers no progress would otherwise spin — so we use
# a clock that ALSO advances by poll_interval on each poll via sleep()).
def fast_clock(start: float = 0.0):
    return FakeClock(start=start)


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_happy_three_commit_reveal_match():
    """3 racers commit + reveal, recomputed hashes match → 3 valid racers, 0 rejected."""
    roster = [
        make_spec("c0", entry_fee_paid=10, fakery_stake=5),
        make_spec("c1", entry_fee_paid=20, fakery_stake=7),
        make_spec("c2", entry_fee_paid=30, fakery_stake=9),
    ]
    handles = make_handles(["c0", "c1", "c2"])

    committed = {
        "c0": commit_msg("job-1", "c0", "sha-c0", "HASH0"),
        "c1": commit_msg("job-1", "c1", "sha-c1", "HASH1"),
        "c2": commit_msg("job-1", "c2", "sha-c2", "HASH2"),
    }

    def inbox_read(*, job_id):
        assert job_id == "job-1"
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": committed[claimant_id]["commit_sha"],
            "self_reported_exit": 0,
        }

    # recompute returns the SAME hash each racer committed → all match.
    committed_hash = {"c0": "HASH0", "c1": "HASH1", "c2": "HASH2"}

    def compute_hash(worktree, base_ref, commit_sha):
        # find the claimant by its commit_sha
        for cid, m in committed.items():
            if m["commit_sha"] == commit_sha:
                return committed_hash[cid]
        return ""

    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        window_s=120.0,
        poll_interval_s=2.0,
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=fast_clock(),
    )

    assert isinstance(result, CollectResult)
    assert result.rejected == []
    assert len(result.racers) == 3

    by_id = {r["claimant_id"]: r for r in result.racers}
    assert set(by_id) == {"c0", "c1", "c2"}

    fees = {"c0": (10, 5), "c1": (20, 7), "c2": (30, 9)}
    required_keys = {
        "claimant_id",
        "commit_sha",
        "worktree_path",
        "self_reported_exit",
        "commit_hash",
        "revealed_at",
        "entry_fee_paid",
        "fakery_stake",
    }
    for cid, r in by_id.items():
        # exact adjudicate shape — every key present
        assert required_keys.issubset(r.keys()), f"{cid} missing keys"
        assert r["commit_sha"] == committed[cid]["commit_sha"]
        assert r["worktree_path"] == f"/wt/{cid}"
        assert r["self_reported_exit"] == 0
        assert r["commit_hash"] == committed[cid]["commit_hash"]
        assert r["revealed_at"]  # non-empty timestamp/marker
        ef, fs = fees[cid]
        assert r["entry_fee_paid"] == ef
        assert r["fakery_stake"] == fs


def test_anti_copy_hash_mismatch_rejected():
    """Racer commits H1 but recompute yields H2 → rejected hash_mismatch, NOT in racers."""
    roster = [make_spec("c0", entry_fee_paid=10, fakery_stake=5)]
    handles = make_handles(["c0"])
    committed = {"c0": commit_msg("job-1", "c0", "sha-c0", "H1")}

    def inbox_read(*, job_id):
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": "sha-c0",
            "self_reported_exit": 0,
        }

    def compute_hash(worktree, base_ref, commit_sha):
        return "H2"  # diff-copy attack: recomputed hash differs from committed H1

    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=fast_clock(),
    )

    assert result.racers == []
    assert len(result.rejected) == 1
    assert result.rejected[0]["claimant_id"] == "c0"
    assert result.rejected[0]["reason"] == "hash_mismatch"


def test_window_timeout_no_commit_does_not_hang():
    """One racer never commits → after FakeClock passes window_s it's rejected;
    others are collected; the loop terminates (proven by FakeClock, no real sleep)."""
    roster = [
        make_spec("c0", entry_fee_paid=1, fakery_stake=1),
        make_spec("c1", entry_fee_paid=2, fakery_stake=2),  # never commits
    ]
    handles = make_handles(["c0", "c1"])

    # only c0 ever appears in the inbox
    committed = {"c0": commit_msg("job-1", "c0", "sha-c0", "H0")}

    def inbox_read(*, job_id):
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": "sha-c0",
            "self_reported_exit": 0,
        }

    def compute_hash(worktree, base_ref, commit_sha):
        return "H0"

    clock = fast_clock()
    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        window_s=10.0,
        poll_interval_s=2.0,
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=clock,
    )

    # c0 collected
    assert [r["claimant_id"] for r in result.racers] == ["c0"]
    # c1 rejected for never committing within the window
    rej = {r["claimant_id"]: r["reason"] for r in result.rejected}
    assert rej == {"c1": "no_commit"}
    # the loop must have ADVANCED time past the window (proves it polled+slept
    # via the FakeClock rather than spinning forever or sleeping for real)
    assert clock.now() >= 10.0
    # and it must have slept at least once (no real wall-clock wait happened)
    assert clock.sleeps  # non-empty record of sleep() durations


def test_zero_poll_interval_still_terminates():
    """Degenerate poll_interval_s=0 with a never-committing racer must NOT busy-spin.

    The window-cannot-hang guarantee requires strictly-monotonic progress to the
    deadline each iteration. With poll_interval_s=0 the per-iteration advance is
    floored to a positive minimum, so the FakeClock crosses the window and the
    loop terminates (it would hang forever before the floor fix)."""
    roster = [
        make_spec("c0", entry_fee_paid=1, fakery_stake=1),
        make_spec("c1", entry_fee_paid=2, fakery_stake=2),  # never commits
    ]
    handles = make_handles(["c0", "c1"])
    committed = {"c0": commit_msg("job-1", "c0", "sha-c0", "H0")}

    def inbox_read(*, job_id):
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": "sha-c0",
            "self_reported_exit": 0,
        }

    def compute_hash(worktree, base_ref, commit_sha):
        return "H0"

    clock = fast_clock()
    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        window_s=1.0,
        poll_interval_s=0.0,  # degenerate — must not stall progress
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=clock,
    )

    assert [r["claimant_id"] for r in result.racers] == ["c0"]
    rej = {r["claimant_id"]: r["reason"] for r in result.rejected}
    assert rej == {"c1": "no_commit"}
    # The clock must have advanced past the window (proves monotonic progress,
    # not a spin), and every recorded sleep was strictly positive.
    assert clock.now() >= 1.0
    assert clock.sleeps
    assert all(s > 0 for s in clock.sleeps)


def test_committed_but_no_reveal():
    """Racer committed but reveal returns nothing → rejected no_reveal."""
    roster = [make_spec("c0", entry_fee_paid=10, fakery_stake=5)]
    handles = make_handles(["c0"])
    committed = {"c0": commit_msg("job-1", "c0", "sha-c0", "H0")}

    def inbox_read(*, job_id):
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return None  # session went dark, no reveal

    def compute_hash(worktree, base_ref, commit_sha):
        return "H0"

    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=fast_clock(),
    )

    assert result.racers == []
    assert len(result.rejected) == 1
    assert result.rejected[0]["claimant_id"] == "c0"
    assert result.rejected[0]["reason"] == "no_reveal"


def test_git_error_empty_hash_fails_closed():
    """_compute_hash returns '' (git error) → mismatch → rejected hash_mismatch (fail-closed)."""
    roster = [make_spec("c0", entry_fee_paid=10, fakery_stake=5)]
    handles = make_handles(["c0"])
    committed = {"c0": commit_msg("job-1", "c0", "sha-c0", "H0")}

    def inbox_read(*, job_id):
        return list(committed.values())

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": "sha-c0",
            "self_reported_exit": 0,
        }

    def compute_hash(worktree, base_ref, commit_sha):
        return ""  # git blew up → fail closed

    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=fast_clock(),
    )

    assert result.racers == []
    assert result.rejected == [{"claimant_id": "c0", "reason": "hash_mismatch"}]


def test_duplicate_commit_messages_first_wins_no_crash():
    """Two commit messages for one claimant → first wins, no crash, single racer."""
    roster = [make_spec("c0", entry_fee_paid=10, fakery_stake=5)]
    handles = make_handles(["c0"])

    msgs = [
        commit_msg("job-1", "c0", "sha-first", "HFIRST"),
        commit_msg("job-1", "c0", "sha-second", "HSECOND"),  # duplicate / late
    ]

    def inbox_read(*, job_id):
        return list(msgs)

    def dispatch_reveal(*, claimant_id, session_name, worktree_path):
        # reveal echoes whatever sha the collector tracked as committed
        return {
            "claimant_id": claimant_id,
            "worktree_path": worktree_path,
            "commit_sha": "sha-first",
            "self_reported_exit": 0,
        }

    def compute_hash(worktree, base_ref, commit_sha):
        # recompute matches the FIRST committed hash
        return "HFIRST"

    result = collect_tournament(
        job_id="job-1",
        roster=roster,
        handles=handles,
        base_ref="base-abc",
        orchestrator_session="orch",
        _inbox_read=inbox_read,
        _dispatch_reveal=dispatch_reveal,
        _compute_hash=compute_hash,
        clock=fast_clock(),
    )

    assert result.rejected == []
    assert len(result.racers) == 1
    r = result.racers[0]
    assert r["claimant_id"] == "c0"
    # first commit wins
    assert r["commit_sha"] == "sha-first"
    assert r["commit_hash"] == "HFIRST"


# ─── Clock / adapter contract tests ───────────────────────────────────────────


def test_fakeclock_does_not_wait_and_records_sleeps():
    clock = FakeClock(start=100.0)
    assert clock.now() == 100.0
    clock.sleep(2.5)
    assert clock.now() == 102.5
    clock.sleep(1.0)
    assert clock.now() == 103.5
    assert clock.sleeps == [2.5, 1.0]


def test_realclock_is_a_clock():
    assert isinstance(RealClock(), Clock)


def test_default_reveal_adapter_raises_without_launcher():
    """The default reveal adapter must NOT import the launcher; it raises guidance."""
    with pytest.raises(RuntimeError):
        default_reveal_adapter(
            claimant_id="c0",
            session_name="sess-c0",
            worktree_path="/wt/c0",
        )


def test_default_inbox_adapter_raises_without_launcher():
    """The default inbox adapter must NOT import the launcher; it raises guidance."""
    with pytest.raises(RuntimeError):
        default_inbox_adapter(job_id="j")


def test_compute_diff_hash_fail_closed_on_git_error():
    """_compute_diff_hash returns '' (not a hash) when git fails — fail closed."""

    def fake_runner(cmd, **kwargs):
        raise OSError("git not found")

    h = _compute_diff_hash(
        "/no/such/worktree",
        "base-abc",
        "sha-xyz",
        _run=fake_runner,
    )
    assert h == ""
