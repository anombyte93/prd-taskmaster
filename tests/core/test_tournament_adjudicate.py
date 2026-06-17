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
  T9. settle_job: stub sleeps → raises ValueError (timeout) — B1.
  T10. adjudicate_submission: bad entry_fee_paid / fakery_stake (non-int string) → 0 — B2.
  T11. adjudicate_job: one malformed racer (no claimant_id) → fail-closed ERROR submission,
       other valid racers still adjudicated, job writes submissions.json — I1 / M2.
  T12. settle_job: non-existent binary → raises ValueError — M3.
  T13. adjudicate_submission: evidence_dir + ledger_dir created before oracle runs — I2.
  T14. adjudicate_submission: claimant_id path traversal → sanitized in path, original id
       preserved in Submission.claimant.id — I3.
"""

from __future__ import annotations

import json
import os
import stat
import time
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

    # M1 — only one call; the dead first call has been removed.
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


# ---------------------------------------------------------------------------
# T9: settle_job timeout — B1
# ---------------------------------------------------------------------------

def test_settle_job_timeout_raises(tmp_path):
    """settle_job with a stub that sleeps → raises ValueError mentioning timeout."""
    stub = tmp_path / "fake_atlas_sleep.py"
    stub.write_text(
        "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\nprint('{}')\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    # Override the timeout to 1s so the test is fast.
    env = {**os.environ, "ATLAS_TOURNAMENT_TIMEOUT_S": "1"}
    # We patch the env variable; settle_job reads it on each call.
    old = os.environ.get("ATLAS_TOURNAMENT_TIMEOUT_S")
    try:
        os.environ["ATLAS_TOURNAMENT_TIMEOUT_S"] = "1"
        with pytest.raises(ValueError, match="timed out"):
            settle_job(
                job_dir=job_dir,
                tournament_cmd=[str(stub)],
            )
    finally:
        if old is None:
            os.environ.pop("ATLAS_TOURNAMENT_TIMEOUT_S", None)
        else:
            os.environ["ATLAS_TOURNAMENT_TIMEOUT_S"] = old


# ---------------------------------------------------------------------------
# T10: bad fee fields (non-int string) → coerced to 0 — B2
# ---------------------------------------------------------------------------

def test_adjudicate_submission_bad_fee_fields_coerce_to_zero(tmp_path):
    """entry_fee_paid / fakery_stake with non-int string → 0, not TypeError."""
    racer = _make_racer()
    racer["entry_fee_paid"] = "not-a-number"
    racer["fakery_stake"] = None

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

    assert sub["entryFeePaid"] == 0
    assert sub["fakeryStake"] == 0
    # The rest of the submission is still valid
    assert sub["oracle"]["verdict"] == "PASS"
    assert sub["claimant"]["id"] == "racer-1"


# ---------------------------------------------------------------------------
# T11: adjudicate_job with one malformed racer → fail-closed ERROR, job continues — I1 / M2
# ---------------------------------------------------------------------------

def test_adjudicate_job_malformed_racer_fail_closed(tmp_path):
    """A racer dict missing claimant_id/commit_sha → fail-closed ERROR submission.

    The job must NOT crash, and other valid racers are still adjudicated correctly.
    submissions.json is written with all entries including the ERROR one.
    """
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    # Malformed racer: no claimant_id or commit_sha
    malformed = {"worktree_path": "/tmp/repo"}
    valid = _make_racer(claimant_id="valid-racer", commit_sha="cafebabe")

    submissions = adjudicate_job(
        job_dir=job_dir,
        racers=[malformed, valid],
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        task_id="1",
        start_commit="start123",
        job_id="job-99",
        card_id="card-1",
        bounty_amount=500,
        job_poster="poster",
        _grade=_stub_grade_pass,
        _sweep=_stub_sweep_wired,
    )

    # Both entries present
    assert len(submissions) == 2

    # The fail-closed submission for the malformed racer.
    # oracle.verdict must be "FAIL" (in-contract; the TS type union is "PASS"|"FAIL").
    # reachability.verdict carries "ERROR" (that union does include ERROR).
    err_sub = submissions[0]
    assert err_sub["oracle"]["verdict"] == "FAIL"
    assert err_sub["reachability"]["verdict"] == "ERROR"
    assert "error" in err_sub["oracle"]

    # The valid racer is still adjudicated normally
    ok_sub = submissions[1]
    assert ok_sub["claimant"]["id"] == "valid-racer"
    assert ok_sub["oracle"]["verdict"] == "PASS"
    assert ok_sub["reachability"]["verdict"] == "WIRED"

    # submissions.json written and parseable
    subs_path = job_dir / "submissions.json"
    assert subs_path.exists()
    parsed = json.loads(subs_path.read_text())
    assert len(parsed) == 2


# ---------------------------------------------------------------------------
# T12: settle_job with non-existent binary → raises ValueError — M3
# ---------------------------------------------------------------------------

def test_settle_job_oserror_raises(tmp_path):
    """settle_job pointing at a non-existent binary → raises ValueError."""
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ValueError, match="invocation failed"):
        settle_job(
            job_dir=job_dir,
            tournament_cmd=["/nonexistent/binary/that/does/not/exist"],
        )


# ---------------------------------------------------------------------------
# T13: evidence_dir + ledger_dir created before oracle runs — I2
# ---------------------------------------------------------------------------

def test_adjudicate_submission_creates_dirs(tmp_path):
    """adjudicate_submission creates evidence_dir and ledger_dir before calling oracle."""
    created_dirs: list[Path] = []

    def _grade_capturing_dirs(*, card_path, repo_path, commit_sha, held_root,
                               evidence_dir, ledger_dir, oracle_cmd=None):
        # At the point the oracle is called, both dirs must already exist.
        created_dirs.append(Path(evidence_dir))
        created_dirs.append(Path(ledger_dir))
        assert Path(evidence_dir).is_dir(), f"evidence_dir not created: {evidence_dir}"
        assert Path(ledger_dir).is_dir(), f"ledger_dir not created: {ledger_dir}"
        return ("PASS", {"verdict": "PASS", "exitCode": 0, "evidenceRef": "e",
                         "sandboxImageDigest": "s", "ledgerEventId": "l"})

    racer = _make_racer(claimant_id="dir-check-racer")
    job_dir = tmp_path / "job"
    # Do NOT pre-create job_dir — adjudicate_submission must create the subdirs itself.

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=job_dir,
        task_id="1",
        start_commit="start123",
        _grade=_grade_capturing_dirs,
        _sweep=_stub_sweep_wired,
    )

    assert sub["oracle"]["verdict"] == "PASS"
    # dirs were checked inside the grade stub
    assert len(created_dirs) == 2


# ---------------------------------------------------------------------------
# T14: claimant_id path traversal sanitized in path, original id preserved — I3
# ---------------------------------------------------------------------------

def test_adjudicate_submission_claimant_id_path_sanitized(tmp_path):
    """claimant_id containing path traversal chars → safe path component.

    The ORIGINAL claimant_id must appear in Submission.claimant.id (settlement
    identity must be preserved). Only the filesystem path is sanitized.
    """
    traversal_id = "../../../etc/passwd"
    racer = _make_racer(claimant_id=traversal_id)
    job_dir = tmp_path / "job"

    checked_dirs: list[Path] = []

    def _grade_checking_path(*, card_path, repo_path, commit_sha, held_root,
                              evidence_dir, ledger_dir, oracle_cmd=None):
        checked_dirs.append(Path(evidence_dir))
        return ("PASS", {"verdict": "PASS", "exitCode": 0, "evidenceRef": "e",
                         "sandboxImageDigest": "s", "ledgerEventId": "l"})

    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=job_dir,
        task_id="1",
        start_commit="start123",
        _grade=_grade_checking_path,
        _sweep=_stub_sweep_wired,
    )

    # Original identity preserved for settlement
    assert sub["claimant"]["id"] == traversal_id

    # Path must NOT escape job_dir/evidence/
    assert len(checked_dirs) == 1
    evidence_dir = checked_dirs[0]
    # The evidence_dir must be a child of job_dir/evidence/
    evidence_root = job_dir / "evidence"
    assert str(evidence_dir).startswith(str(evidence_root)), (
        f"Path traversal not sanitized: {evidence_dir} not under {evidence_root}"
    )
    # And it must not contain the literal traversal sequence
    assert ".." not in str(evidence_dir), f".. still in path: {evidence_dir}"


# ---------------------------------------------------------------------------
# Fix 3: fail-closed adjudicate_job ERROR submission → oracle.verdict == "FAIL"
# ---------------------------------------------------------------------------

def test_adjudicate_job_fail_closed_oracle_verdict_is_fail(tmp_path):
    """Fix 3: fail-closed ERROR submission from adjudicate_job must set
    oracle.verdict='FAIL' (in-contract), NOT 'ERROR' (out-of-union).
    reachability.verdict remains 'ERROR' (that union includes ERROR).
    """
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    # Malformed racer forces adjudicate_job's except branch.
    malformed = {}  # missing claimant_id, commit_sha, worktree_path

    submissions = adjudicate_job(
        job_dir=job_dir,
        racers=[malformed],
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        task_id="1",
        start_commit="start123",
        job_id="job-fail-closed",
        card_id="card-1",
        bounty_amount=0,
        job_poster="poster",
        _grade=_stub_grade_pass,
        _sweep=_stub_sweep_wired,
    )

    assert len(submissions) == 1
    sub = submissions[0]
    # The key assertion: oracle.verdict must be the in-contract "FAIL"
    assert sub["oracle"]["verdict"] == "FAIL", (
        f"oracle.verdict should be 'FAIL' (in-contract); got {sub['oracle']['verdict']!r}"
    )
    assert sub["reachability"]["verdict"] == "ERROR"
    assert "error" in sub["oracle"]


# ---------------------------------------------------------------------------
# Fix 4: unexpected _grade failure → fail-closed FAIL (not crash)
# ---------------------------------------------------------------------------

def test_adjudicate_submission_unexpected_grade_failure_fail_closed(tmp_path):
    """Fix 4: a _grade raising TypeError (not OracleCardError) must be caught,
    set oracle.verdict='FAIL' and oracle.error, not propagate.
    """
    def _grade_raises_type_error(*, card_path, repo_path, commit_sha, held_root,
                                  evidence_dir, ledger_dir, oracle_cmd=None):
        raise TypeError("unexpected type in grade_card")

    racer = _make_racer()
    sub = adjudicate_submission(
        racer,
        card_path=tmp_path / "card.json",
        held_root=tmp_path / "held",
        job_dir=tmp_path / "job",
        task_id="1",
        start_commit="start123",
        _grade=_grade_raises_type_error,
        _sweep=_stub_sweep_wired,
    )

    assert sub["oracle"]["verdict"] == "FAIL", (
        f"Unexpected _grade error must degrade to FAIL; got {sub['oracle']['verdict']!r}"
    )
    assert "error" in sub["oracle"]
    assert "TypeError" in sub["oracle"]["error"] or "unexpected type" in sub["oracle"]["error"]
    # Submission is otherwise complete (no crash).
    assert sub["claimant"]["id"] == "racer-1"
    assert sub["reachability"]["verdict"] == "WIRED"
