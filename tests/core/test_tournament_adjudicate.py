"""Tournament adjudicator tests — gates are fully mocked; no real podman/CLI invoked.

Mirrors the style of tests/core/test_oracle_bridge.py.

Coverage:
  T1. adjudicate_submission: PASS oracle + WIRED reach → full Submission shape.
  T2. adjudicate_submission: FAIL oracle with missing detail keys → evidenceRef/
      sandboxImageDigest/ledgerEventId default to "", exitCode to null.
  T3. adjudicate_submission: OracleCardError → fail-closed (oracle.verdict=="FAIL"), no crash.
  T4. adjudicate_submission: _sweep raises → reachability.verdict=="ERROR".
  T5. adjudicate_job: writes submissions.json (valid JSON array, N entries) + job.json
      (correct shape); both parse.
  T6. settle_job: stub exits 0 with ok:true → returns parsed envelope.
  T7. settle_job: stub exits 1 with ok:false → returns ok:false WITHOUT raising.
  T8. settle_job: stub emits garbage → raises ValueError.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from prd_taskmaster.oracle_bridge import OracleCardError
from prd_taskmaster.tournament.adjudicate import (
    adjudicate_job,
    adjudicate_submission,
    settle_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_racer(
    *,
    claimant_id: str = "racer-1",
    commit_sha: str = "deadbeef",
    worktree_path: str = "/tmp/repo",
    self_reported_exit: "int | None" = 0,
    commit_hash: str = "sha256:abc",
    revealed_at: str = "2026-06-17T00:00:00Z",
    entry_fee_paid: int = 100,
    fakery_stake: int = 50,
) -> dict:
    return {
        "claimant_id": claimant_id,
        "commit_sha": commit_sha,
        "worktree_path": worktree_path,
        "self_reported_exit": self_reported_exit,
        "commit_hash": commit_hash,
        "revealed_at": revealed_at,
        "entry_fee_paid": entry_fee_paid,
        "fakery_stake": fakery_stake,
    }


def _stub_grade_pass(*, card_path, repo_path, commit_sha, held_root, evidence_dir, ledger_dir, oracle_cmd=None):
    return (
        "PASS",
        {
            "verdict": "PASS",
            "exitCode": 0,
            "evidenceRef": "evd",
            "sandboxImageDigest": "sha256:x",
            "ledgerEventId": "evt",
        },
    )


def _stub_grade_fail_sparse(*, card_path, repo_path, commit_sha, held_root, evidence_dir, ledger_dir, oracle_cmd=None):
    """FAIL with no extra detail keys — exercises the default-mapping logic."""
    return ("FAIL", {"verdict": "FAIL"})


def _stub_sweep_wired(task_id, start_commit, cwd=None):
    return {"verdict": "WIRED", "module": "foo", "importers": [], "reachable_via": []}


def _stub_sweep_orphan(task_id, start_commit, cwd=None):
    return {"verdict": "ORPHAN", "module": "bar", "importers": [], "reachable_via": []}


def _stub_grade_card_error(*, card_path, repo_path, commit_sha, held_root, evidence_dir, ledger_dir, oracle_cmd=None):
    raise OracleCardError("no 'grading' block in card")


def _stub_sweep_raises(task_id, start_commit, cwd=None):
    raise RuntimeError("sweep crashed")


# ---------------------------------------------------------------------------
# T1: Full PASS + WIRED — assert exact Submission shape
# ---------------------------------------------------------------------------

def test_adjudicate_submission_pass_wired(tmp_path):
    """PASS oracle + WIRED reach → Submission shape matches TS spine exactly."""
    racer = _make_racer()

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=tmp_path / "job",
        task_id="1",
        start_commit="start123",
        _grade=_stub_grade_pass,
        _sweep=_stub_sweep_wired,
    )

    # claimant block
    assert sub["claimant"]["kind"] == "executor"
    assert sub["claimant"]["id"] == "racer-1"

    # commit metadata
    assert sub["commitSha"] == "deadbeef"

    # self_reported_exit is passed through from the racer
    assert sub["selfReportedExit"] == 0

    # trusted oracle block
    assert sub["oracle"]["verdict"] == "PASS"
    assert sub["oracle"]["exitCode"] == 0
    assert sub["oracle"]["evidenceRef"] == "evd"
    assert sub["oracle"]["sandboxImageDigest"] == "sha256:x"
    assert sub["oracle"]["ledgerEventId"] == "evt"

    # reachability
    assert sub["reachability"]["verdict"] == "WIRED"

    # commit-reveal passthrough
    assert sub["commitHash"] == "sha256:abc"
    assert sub["revealedAt"] == "2026-06-17T00:00:00Z"

    # fees
    assert sub["entryFeePaid"] == 100
    assert sub["fakeryStake"] == 50


# ---------------------------------------------------------------------------
# T2: Missing oracle detail keys → "" / null defaults (empty-evidence safety)
# ---------------------------------------------------------------------------

def test_adjudicate_submission_missing_oracle_detail_keys(tmp_path):
    """FAIL oracle with no detail keys → evidenceRef/sandboxImageDigest/ledgerEventId == ""
    and exitCode == null. This is the empty-evidence safety contract."""
    racer = _make_racer(self_reported_exit=1)

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=tmp_path / "job",
        task_id="1",
        start_commit="start123",
        _grade=_stub_grade_fail_sparse,
        _sweep=_stub_sweep_wired,
    )

    assert sub["oracle"]["verdict"] == "FAIL"
    assert sub["oracle"]["exitCode"] is None           # null, not absent
    assert sub["oracle"]["evidenceRef"] == ""          # empty string, not a fake value
    assert sub["oracle"]["sandboxImageDigest"] == ""
    assert sub["oracle"]["ledgerEventId"] == ""


# ---------------------------------------------------------------------------
# T3: OracleCardError → fail-closed FAIL, no crash
# ---------------------------------------------------------------------------

def test_adjudicate_submission_oracle_card_error_fail_closed(tmp_path):
    """OracleCardError from grade_card → oracle.verdict=='FAIL', never raises."""
    racer = _make_racer()

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "bad_card.json",
        held_root=tmp_path / "held",
        job_dir=tmp_path / "job",
        task_id="1",
        start_commit="start123",
        _grade=_stub_grade_card_error,
        _sweep=_stub_sweep_wired,
    )

    assert sub["oracle"]["verdict"] == "FAIL"
    assert "error" in sub["oracle"]
    # The rest of the submission is still valid
    assert sub["claimant"]["kind"] == "executor"
    assert sub["reachability"]["verdict"] == "WIRED"


# ---------------------------------------------------------------------------
# T4: sweep raises → reachability.verdict == "ERROR"
# ---------------------------------------------------------------------------

def test_adjudicate_submission_sweep_raises_fail_closed(tmp_path):
    """If _sweep raises, reachability.verdict=='ERROR' — never crashes the job."""
    racer = _make_racer()

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=tmp_path / "job",
        task_id="1",
        start_commit="start123",
        _grade=_stub_grade_pass,
        _sweep=_stub_sweep_raises,
    )

    assert sub["reachability"]["verdict"] == "ERROR"
    # Oracle still passes through normally
    assert sub["oracle"]["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# T5: adjudicate_job writes submissions.json + job.json
# ---------------------------------------------------------------------------

def test_adjudicate_job_writes_output_files(tmp_path):
    """adjudicate_job writes valid submissions.json (N entries) and job.json."""
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    racers = [
        _make_racer(claimant_id="racer-1", commit_sha="aaa"),
        _make_racer(claimant_id="racer-2", commit_sha="bbb"),
    ]

    submissions = adjudicate_job(
        job_dir=job_dir,
        racers=racers,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        task_id="1",
        start_commit="start123",
        job_id="job-42",
        card_id="card-7",
        bounty_amount=1000,
        job_poster="poster-user",
        _grade=_stub_grade_pass,
        _sweep=_stub_sweep_wired,
    )

    # Return value is the list
    assert isinstance(submissions, list)
    assert len(submissions) == 2

    # submissions.json exists and parses as an array of 2
    subs_path = job_dir / "submissions.json"
    assert subs_path.exists()
    parsed_subs = json.loads(subs_path.read_text())
    assert isinstance(parsed_subs, list)
    assert len(parsed_subs) == 2

    # Each submission has the right claimant id
    ids = {s["claimant"]["id"] for s in parsed_subs}
    assert ids == {"racer-1", "racer-2"}

    # job.json exists and has correct shape
    job_path = job_dir / "job.json"
    assert job_path.exists()
    job_meta = json.loads(job_path.read_text())
    assert job_meta["jobId"] == "job-42"
    assert job_meta["cardId"] == "card-7"
    assert job_meta["bountyAmount"] == 1000
    assert job_meta["jobPoster"] == "poster-user"


# ---------------------------------------------------------------------------
# T6: settle_job with ok:true stub
# ---------------------------------------------------------------------------

def _write_stub_script(path: Path, exit_code: int, output: str) -> None:
    """Write a tiny shell stub that prints output and exits with exit_code."""
    path.write_text(
        f"#!/usr/bin/env python3\nimport sys\nprint({output!r})\nsys.exit({exit_code})\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_settle_job_ok_true(tmp_path):
    """settle_job with a stub that exits 0 + ok:true → returns parsed envelope."""
    stub = tmp_path / "fake_atlas.py"
    canned = json.dumps({"ok": True, "stage": "done", "payouts": []})
    _write_stub_script(stub, 0, canned)

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    result = settle_job(
        job_dir=job_dir,
        tournament_cmd=[str(stub), "tournament", "settle"],
        # tournament_cmd is what the adjudicator prepends — but settle_job itself
        # builds: tournament_cmd + ["tournament","settle","--job",job_dir]
        # so we pass only the binary here
    )
    # settle_job constructs: tournament_cmd + ["tournament","settle","--job",...]
    # We need just the stub binary as tournament_cmd
    result = settle_job(
        job_dir=job_dir,
        tournament_cmd=[str(stub)],
    )

    assert result["ok"] is True
    assert result["stage"] == "done"


# ---------------------------------------------------------------------------
# T7: settle_job with ok:false stub → returns envelope WITHOUT raising
# ---------------------------------------------------------------------------

def test_settle_job_ok_false_no_raise(tmp_path):
    """settle_job with a stub that exits 1 + ok:false → returns ok:false, does NOT raise."""
    stub = tmp_path / "fake_atlas_fail.py"
    canned = json.dumps({"ok": False, "stage": "apply_settlement", "error": "slash threshold not met"})
    _write_stub_script(stub, 1, canned)

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    result = settle_job(
        job_dir=job_dir,
        tournament_cmd=[str(stub)],
    )

    assert result["ok"] is False
    assert result["stage"] == "apply_settlement"


# ---------------------------------------------------------------------------
# T8: settle_job with garbage output → raises ValueError
# ---------------------------------------------------------------------------

def test_settle_job_garbage_raises(tmp_path):
    """settle_job with a stub that emits non-JSON → raises ValueError."""
    stub = tmp_path / "fake_atlas_garbage.py"
    _write_stub_script(stub, 0, "this is not json at all")

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ValueError, match="unparseable"):
        settle_job(
            job_dir=job_dir,
            tournament_cmd=[str(stub)],
        )
