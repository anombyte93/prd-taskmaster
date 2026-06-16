"""Anti-Sybil admission tests — no live launcher, no real MCP.

Coverage:
  AS1. admit N racers up to PER_JOB_CAP_N — all succeed.
  AS2. (N+1)th racer for a job → SybilLimitError("job_cap_exceeded").
  AS3. Same operator admitted up to PER_OPERATOR_RATE_LIMIT — next → SybilLimitError("operator_rate_limited").
  AS4. release frees slots: admit to rate_limit, release one, admit again succeeds.
  AS5. Returned dict has {"entry_fee_paid": E, "fakery_stake": S} with S = 5 * E.
  AS6. operators.json round-trips via locked_update (shape preserved, valid JSON).
  AS7. active_count_for_job / active_count_for_operator helpers work on loaded state.
  AS8. release(claimant_id=None) frees all entries for a job.
  AS9. release(claimant_id=X) frees only that claimant, not others.
  AS10. admit with custom entry_fee + stake_mult propagates correctly.
  AS11. sweep_expired deactivates entries past expires_at (pure helper).
  AS12. Expired entries auto-free inside admit's transform (TTL sweep).
  AS13. Concurrency: exactly PER_JOB_CAP_N threads succeed; the rest raise job_cap_exceeded.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from prd_taskmaster.tournament.antisybil import (
    ENTRY_FEE_E,
    FAKERY_STAKE_MULT,
    PER_JOB_CAP_N,
    PER_OPERATOR_RATE_LIMIT,
    TTL_SECONDS,
    SybilLimitError,
    active_count_for_job,
    active_count_for_operator,
    admit,
    release,
    sweep_expired,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

NOW = "2026-06-17T00:00:00+00:00"
# A timestamp far in the future (past any TTL)
FAR_FUTURE = "2099-01-01T00:00:00+00:00"
# A timestamp well in the past (already expired)
PAST = "2020-01-01T00:00:00+00:00"


@pytest.fixture()
def ops_path(tmp_path: Path) -> Path:
    return tmp_path / ".atlas-ai" / "tournament" / "operators.json"


# ─── AS1 / AS2: per-job cap ───────────────────────────────────────────────────

class TestJobCap:
    def test_admit_up_to_cap_succeeds(self, ops_path: Path) -> None:
        """AS1: N distinct claimants for one job all succeed."""
        for i in range(PER_JOB_CAP_N):
            result = admit(
                ops_path,
                operator_id=f"claude:racer-{i}",
                job_id="job-1",
                claimant_id=f"job-1:{i}:racer",
                now=NOW,
            )
            assert result["entry_fee_paid"] == ENTRY_FEE_E
            assert result["fakery_stake"] == ENTRY_FEE_E * FAKERY_STAKE_MULT

    def test_n_plus_1_raises_job_cap_exceeded(self, ops_path: Path) -> None:
        """AS2: (N+1)th racer for the same job raises job_cap_exceeded."""
        for i in range(PER_JOB_CAP_N):
            admit(
                ops_path,
                operator_id=f"claude:racer-{i}",
                job_id="job-cap",
                claimant_id=f"job-cap:{i}:racer",
                now=NOW,
            )

        with pytest.raises(SybilLimitError) as exc_info:
            admit(
                ops_path,
                operator_id="claude:overflow",
                job_id="job-cap",
                claimant_id=f"job-cap:{PER_JOB_CAP_N}:racer",
                now=NOW,
            )

        assert exc_info.value.reason == "job_cap_exceeded"

    def test_job_cap_does_not_bleed_across_jobs(self, ops_path: Path) -> None:
        """Full cap on job-A should not affect job-B."""
        for i in range(PER_JOB_CAP_N):
            admit(
                ops_path,
                operator_id=f"claude:racer-{i}",
                job_id="job-A",
                claimant_id=f"job-A:{i}:racer",
                now=NOW,
            )

        # job-B should still accept
        result = admit(
            ops_path,
            operator_id="claude:racer-0",
            job_id="job-B",
            claimant_id="job-B:0:racer",
            now=NOW,
        )
        assert result["entry_fee_paid"] == ENTRY_FEE_E


# ─── AS3: per-operator rate limit ─────────────────────────────────────────────

class TestOperatorRateLimit:
    def test_admit_up_to_rate_limit_succeeds(self, ops_path: Path) -> None:
        """AS3 first half: same operator admitted PER_OPERATOR_RATE_LIMIT times."""
        for i in range(PER_OPERATOR_RATE_LIMIT):
            result = admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id=f"job-rate-{i}",
                claimant_id=f"job-rate-{i}:0:sonnet",
                now=NOW,
            )
            assert result["entry_fee_paid"] == ENTRY_FEE_E

    def test_operator_rate_limit_exceeded(self, ops_path: Path) -> None:
        """AS3 second half: one more → operator_rate_limited."""
        for i in range(PER_OPERATOR_RATE_LIMIT):
            admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id=f"job-orl-{i}",
                claimant_id=f"job-orl-{i}:0:sonnet",
                now=NOW,
            )

        with pytest.raises(SybilLimitError) as exc_info:
            admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id="job-orl-overflow",
                claimant_id="job-orl-overflow:0:sonnet",
                now=NOW,
            )

        assert exc_info.value.reason == "operator_rate_limited"

    def test_different_operators_independent(self, ops_path: Path) -> None:
        """Different operator_ids don't share rate-limit slots."""
        for i in range(PER_OPERATOR_RATE_LIMIT):
            admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id=f"job-ind-{i}",
                claimant_id=f"job-ind-{i}:0:sonnet",
                now=NOW,
            )

        # Different operator should still work
        result = admit(
            ops_path,
            operator_id="claude:haiku",
            job_id="job-ind-haiku",
            claimant_id="job-ind-haiku:0:haiku",
            now=NOW,
        )
        assert result["entry_fee_paid"] == ENTRY_FEE_E


# ─── AS4: release frees slots ─────────────────────────────────────────────────

class TestRelease:
    def test_release_frees_operator_slot(self, ops_path: Path) -> None:
        """AS4: admit to rate_limit, release one, admit again succeeds."""
        job_ids = [f"job-rel-{i}" for i in range(PER_OPERATOR_RATE_LIMIT)]
        for j in job_ids:
            admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id=j,
                claimant_id=f"{j}:0:sonnet",
                now=NOW,
            )

        # At limit — this would fail
        with pytest.raises(SybilLimitError) as exc_info:
            admit(
                ops_path,
                operator_id="claude:sonnet",
                job_id="job-rel-over",
                claimant_id="job-rel-over:0:sonnet",
                now=NOW,
            )
        assert exc_info.value.reason == "operator_rate_limited"

        # Release one job's claimant
        release(ops_path, job_id=job_ids[0], claimant_id=f"{job_ids[0]}:0:sonnet")

        # Now admit succeeds again
        result = admit(
            ops_path,
            operator_id="claude:sonnet",
            job_id="job-rel-retry",
            claimant_id="job-rel-retry:0:sonnet",
            now=NOW,
        )
        assert result["entry_fee_paid"] == ENTRY_FEE_E

    def test_release_whole_job(self, ops_path: Path) -> None:
        """AS8: release(claimant_id=None) frees all entries for a job."""
        for i in range(3):
            admit(
                ops_path,
                operator_id=f"claude:racer-{i}",
                job_id="job-bulk-release",
                claimant_id=f"job-bulk-release:{i}:racer",
                now=NOW,
            )

        release(ops_path, job_id="job-bulk-release")

        state = json.loads(ops_path.read_text())
        bulk_entries = [
            e for e in state["entries"]
            if e["job_id"] == "job-bulk-release"
        ]
        assert all(not e["active"] for e in bulk_entries)

    def test_release_single_claimant(self, ops_path: Path) -> None:
        """AS9: release(claimant_id=X) frees only that claimant."""
        for i in range(3):
            admit(
                ops_path,
                operator_id=f"claude:racer-{i}",
                job_id="job-single-release",
                claimant_id=f"job-single-release:{i}:racer",
                now=NOW,
            )

        release(ops_path, job_id="job-single-release", claimant_id="job-single-release:1:racer")

        state = json.loads(ops_path.read_text())
        entries = {
            e["claimant_id"]: e
            for e in state["entries"]
            if e["job_id"] == "job-single-release"
        }
        assert entries["job-single-release:0:racer"]["active"] is True
        assert entries["job-single-release:1:racer"]["active"] is False
        assert entries["job-single-release:2:racer"]["active"] is True


# ─── AS5: fee amounts ─────────────────────────────────────────────────────────

class TestFeeAmounts:
    def test_default_fee_is_entry_fee_e(self, ops_path: Path) -> None:
        """AS5: entry_fee_paid=E, fakery_stake=5*E with defaults."""
        result = admit(
            ops_path,
            operator_id="claude:sonnet",
            job_id="job-fee",
            claimant_id="job-fee:0:sonnet",
            now=NOW,
        )
        assert result["entry_fee_paid"] == ENTRY_FEE_E
        assert result["fakery_stake"] == ENTRY_FEE_E * FAKERY_STAKE_MULT
        assert result["fakery_stake"] == ENTRY_FEE_E * 5  # S = 5E

    def test_default_constants_are_1_and_5(self) -> None:
        """Constants E=1, MULT=5 → S=5 for default invocation."""
        assert ENTRY_FEE_E == 1
        assert FAKERY_STAKE_MULT == 5
        assert ENTRY_FEE_E * FAKERY_STAKE_MULT == 5

    def test_custom_entry_fee_and_stake_mult(self, ops_path: Path) -> None:
        """AS10: custom entry_fee + stake_mult propagates correctly."""
        result = admit(
            ops_path,
            operator_id="claude:sonnet",
            job_id="job-custom-fee",
            claimant_id="job-custom-fee:0:sonnet",
            now=NOW,
            entry_fee=10,
            stake_mult=3,
        )
        assert result["entry_fee_paid"] == 10
        assert result["fakery_stake"] == 30  # 10 * 3


# ─── AS6: persistence (operators.json round-trip) ─────────────────────────────

class TestPersistence:
    def test_operators_json_round_trips(self, ops_path: Path) -> None:
        """AS6: after admit, operators.json is valid JSON with correct shape."""
        admit(
            ops_path,
            operator_id="claude:sonnet",
            job_id="job-persist",
            claimant_id="job-persist:0:sonnet",
            now=NOW,
        )

        assert ops_path.exists()
        state = json.loads(ops_path.read_text())
        assert isinstance(state, dict)
        assert "entries" in state
        assert isinstance(state["entries"], list)

        entry = state["entries"][0]
        assert entry["operator_id"] == "claude:sonnet"
        assert entry["job_id"] == "job-persist"
        assert entry["claimant_id"] == "job-persist:0:sonnet"
        assert entry["admitted_at"] == NOW
        assert entry["active"] is True
        # TTL field must be present
        assert "expires_at" in entry

    def test_multiple_admits_accumulate(self, ops_path: Path) -> None:
        """Multiple admits append to entries list; all are valid JSON."""
        for i in range(3):
            admit(
                ops_path,
                operator_id=f"claude:model-{i}",
                job_id="job-acc",
                claimant_id=f"job-acc:{i}:model",
                now=NOW,
            )

        state = json.loads(ops_path.read_text())
        assert len(state["entries"]) == 3

    def test_operators_json_created_if_absent(self, ops_path: Path) -> None:
        """operators.json is created when it doesn't exist."""
        assert not ops_path.exists()
        admit(
            ops_path,
            operator_id="claude:sonnet",
            job_id="job-create",
            claimant_id="job-create:0:sonnet",
            now=NOW,
        )
        assert ops_path.exists()


# ─── AS7: pure helpers ────────────────────────────────────────────────────────

class TestPureHelpers:
    def _make_state(self) -> dict:
        return {
            "entries": [
                {"operator_id": "claude:sonnet", "job_id": "job-1", "claimant_id": "c1", "active": True},
                {"operator_id": "claude:sonnet", "job_id": "job-2", "claimant_id": "c2", "active": True},
                {"operator_id": "claude:haiku",  "job_id": "job-1", "claimant_id": "c3", "active": True},
                {"operator_id": "claude:sonnet", "job_id": "job-1", "claimant_id": "c4", "active": False},
            ]
        }

    def test_active_count_for_job(self) -> None:
        """AS7a: active_count_for_job counts only active=True for a job."""
        state = self._make_state()
        assert active_count_for_job(state, "job-1") == 2   # c1 (active) + c3 (active); c4 inactive
        assert active_count_for_job(state, "job-2") == 1
        assert active_count_for_job(state, "job-x") == 0

    def test_active_count_for_operator(self) -> None:
        """AS7b: active_count_for_operator counts only active=True for operator."""
        state = self._make_state()
        assert active_count_for_operator(state, "claude:sonnet") == 2  # c1+c2 (c4 inactive)
        assert active_count_for_operator(state, "claude:haiku") == 1
        assert active_count_for_operator(state, "claude:opus") == 0

    def test_helpers_handle_empty_state(self) -> None:
        """Helpers return 0 on empty/missing entries."""
        assert active_count_for_job({}, "job-1") == 0
        assert active_count_for_operator({}, "claude:sonnet") == 0
        assert active_count_for_job({"entries": []}, "job-1") == 0


# ─── AS11: sweep_expired (pure helper, I2) ────────────────────────────────────

class TestSweepExpired:
    def test_sweep_deactivates_past_entries(self) -> None:
        """AS11 (I2): sweep_expired marks entries with expires_at in the past as inactive."""
        state = {
            "entries": [
                {
                    "operator_id": "claude:sonnet",
                    "job_id": "job-ttl",
                    "claimant_id": "c1",
                    "active": True,
                    "expires_at": PAST,  # already expired
                },
                {
                    "operator_id": "claude:haiku",
                    "job_id": "job-ttl",
                    "claimant_id": "c2",
                    "active": True,
                    "expires_at": FAR_FUTURE,  # still valid
                },
            ]
        }
        sweep_expired(state, NOW)
        assert state["entries"][0]["active"] is False, "expired entry should be deactivated"
        assert state["entries"][1]["active"] is True, "future entry should remain active"

    def test_sweep_leaves_already_inactive_alone(self) -> None:
        """sweep_expired doesn't touch entries already inactive."""
        state = {
            "entries": [
                {
                    "operator_id": "claude:sonnet",
                    "job_id": "job-x",
                    "claimant_id": "c1",
                    "active": False,
                    "expires_at": PAST,
                },
            ]
        }
        sweep_expired(state, NOW)
        # Still False, not changed (already inactive)
        assert state["entries"][0]["active"] is False

    def test_sweep_leaves_no_expires_at_alone(self) -> None:
        """Entries without expires_at are not touched (backwards compat)."""
        state = {
            "entries": [
                {
                    "operator_id": "claude:sonnet",
                    "job_id": "job-old",
                    "claimant_id": "c1",
                    "active": True,
                    # No expires_at field
                },
            ]
        }
        sweep_expired(state, NOW)
        assert state["entries"][0]["active"] is True

    def test_sweep_returns_same_state_dict(self) -> None:
        """sweep_expired returns the same dict object (mutates in place)."""
        state = {"entries": []}
        result = sweep_expired(state, NOW)
        assert result is state

    def test_expired_entry_no_longer_counts_toward_cap(self, ops_path: Path) -> None:
        """AS12 (I2): an entry past its TTL auto-frees inside admit's locked transform."""
        # Admit PER_JOB_CAP_N racers with expires_at in the PAST (simulate crashed jobs).
        # We directly write the state to operators.json with past expires_at.
        ops_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "entries": [
                {
                    "operator_id": f"claude:racer-{i}",
                    "job_id": "job-ttl-sweep",
                    "claimant_id": f"job-ttl-sweep:{i}:racer",
                    "admitted_at": PAST,
                    "expires_at": PAST,   # already expired
                    "active": True,
                }
                for i in range(PER_JOB_CAP_N)
            ]
        }
        ops_path.write_text(json.dumps(state, indent=2))

        # Now admit should succeed because the TTL sweep fires inside the transform
        # and frees all the expired (phantom) slots.
        result = admit(
            ops_path,
            operator_id="claude:newcomer",
            job_id="job-ttl-sweep",
            claimant_id=f"job-ttl-sweep:{PER_JOB_CAP_N}:newcomer",
            now=NOW,
        )
        assert result["entry_fee_paid"] == ENTRY_FEE_E

    def test_ttl_constant_is_4_hours(self) -> None:
        """TTL_SECONDS must be 4 hours (matching launcher max_lifetime)."""
        assert TTL_SECONDS == 4 * 3600


# ─── AS13: concurrency / atomicity (I4) ──────────────────────────────────────

class TestConcurrencyAtomicity:
    def test_exactly_n_admits_succeed_under_concurrency(self, ops_path: Path) -> None:
        """AS13 (I4): 20 concurrent threads → exactly PER_JOB_CAP_N succeed, rest raise."""
        N_THREADS = 20
        successes: list[str] = []
        failures: list[str] = []
        lock = threading.Lock()

        def _try_admit(thread_id: int) -> None:
            try:
                admit(
                    ops_path,
                    operator_id=f"claude:racer-{thread_id}",
                    job_id="job-concurrent",
                    claimant_id=f"job-concurrent:{thread_id}:racer",
                    now=NOW,
                )
                with lock:
                    successes.append(f"thread-{thread_id}")
            except SybilLimitError as exc:
                with lock:
                    failures.append(exc.reason)

        threads = [threading.Thread(target=_try_admit, args=(i,)) for i in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly PER_JOB_CAP_N slots must have been admitted.
        assert len(successes) == PER_JOB_CAP_N, (
            f"Expected {PER_JOB_CAP_N} successes, got {len(successes)}: {successes}"
        )
        # The rest must all be job_cap_exceeded (not some silent data corruption).
        assert len(failures) == N_THREADS - PER_JOB_CAP_N
        assert all(r == "job_cap_exceeded" for r in failures), (
            f"Unexpected failure reasons: {set(failures)}"
        )

        # Verify the on-disk state is consistent.
        state = json.loads(ops_path.read_text())
        active = [e for e in state["entries"] if e.get("active")]
        assert len(active) == PER_JOB_CAP_N, (
            f"On-disk active count mismatch: {len(active)}"
        )


# ─── SybilLimitError typing ───────────────────────────────────────────────────

class TestSybilLimitError:
    def test_reason_attribute_accessible(self) -> None:
        err = SybilLimitError("job_cap_exceeded")
        assert err.reason == "job_cap_exceeded"

    def test_is_exception_subclass(self) -> None:
        assert issubclass(SybilLimitError, Exception)

    def test_invalid_reason_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            SybilLimitError("not_a_valid_reason")

    def test_operator_rate_limited_reason(self) -> None:
        err = SybilLimitError("operator_rate_limited")
        assert err.reason == "operator_rate_limited"

    def test_str_is_reason(self) -> None:
        err = SybilLimitError("job_cap_exceeded")
        assert str(err) == "job_cap_exceeded"
