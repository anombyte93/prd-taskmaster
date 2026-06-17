"""Tests for the independent out-of-band re-execution watcher.

The watcher re-adjudicates settled tournament submissions from PRIMARY EVIDENCE
(the claimed commit + the CDD card), compares its independently-derived verdict
to the adjudicator's recorded verdict, accumulates a concordance ledger over real
*slash decisions*, and exposes a FAIL-CLOSED gate that permits real
(--enforce-slash) forfeiture only behind an observed track record.

Hardened contract (post adversarial review):
  * ABSTAIN — inability to independently verify (oracle could not run, no worktree,
    failed hash recompute) is NEVER counted as grounds to slash. It abstains and
    BLOCKS the permit. Only POSITIVE independent evidence confirms a slash.
  * Whole-job veto — ANY discrepancy in the job (including a cheating winner the
    in-band adjudicator passed) blocks the permit.
  * No self-bootstrapping — the historical concordance excludes the in-flight job
    and is measured over real slash *decisions*, not trivial double-PASS winners.
  * Read-only — the watcher writes ONLY its own ledger.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from prd_taskmaster.tournament import watcher


# ── helpers ──────────────────────────────────────────────────────────────────

def _submission(
    claimant_id: str,
    *,
    oracle: str = "PASS",
    reach: str = "WIRED",
    commit_hash: str = "hash-ok",
    commit_sha: str = "c0ffee",
) -> dict:
    return {
        "claimant": {"kind": "executor", "id": claimant_id},
        "commitSha": commit_sha,
        "oracle": {"verdict": oracle},
        "reachability": {"verdict": reach},
        "commitHash": commit_hash,
    }


def _write_job(job_dir: Path, submissions: list[dict], job_id: str = "job-1") -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "submissions.json").write_text(json.dumps(submissions))
    (job_dir / "job.json").write_text(json.dumps({"jobId": job_id}))


def _stub_gates(*, oracle="PASS", detail=None, reach="WIRED", recomputed_hash="hash-ok"):
    return (
        lambda **kw: (oracle, detail if detail is not None else {}),
        lambda task_id, start_commit, cwd=None: {"verdict": reach},
        lambda worktree, base_ref, commit_sha, **kw: recomputed_hash,
    )


def _radj(submission, tmp_path, *, worktree=None, **stubs):
    grade, sweep, hsh = _stub_gates(**stubs)
    return watcher.re_adjudicate_submission(
        submission,
        worktree=tmp_path if worktree is None else worktree,
        repo_root=str(tmp_path), card_path=tmp_path / "card.json", held_root=tmp_path,
        job_dir=tmp_path, task_id="7", start_commit="base", base_ref="base",
        _grade=grade, _sweep=sweep, _hash=hsh,
    )


def _v(claimant_id, *, agreement, slash_grounds, recorded_passes_both):
    """Build a per-submission verdict (the subset permit_enforce_slash consumes)."""
    return {
        "claimant_id": claimant_id,
        "agreement": agreement,
        "slash_grounds": slash_grounds,
        "recorded_passes_both": recorded_passes_both,
    }


# ── re_adjudicate_submission: classification ─────────────────────────────────

def test_confirm_when_watcher_agrees_pass(tmp_path):
    v = _radj(_submission("ex-a", oracle="PASS", reach="WIRED"), tmp_path,
              oracle="PASS", reach="WIRED", recomputed_hash="hash-ok")
    assert v["watcher_passes_both"] is True
    assert v["slash_grounds"] is False
    assert v["verified"] is True
    assert v["agreement"] == "CONFIRM"


def test_confirm_when_watcher_agrees_fail(tmp_path):
    # Adjudicator recorded FAIL; watcher independently also FAILs (clean grade) → confirmed slash.
    v = _radj(_submission("ex-b", oracle="FAIL", reach="WIRED"), tmp_path,
              oracle="FAIL", reach="WIRED", recomputed_hash="hash-ok")
    assert v["slash_grounds"] is True
    assert v["recorded_passes_both"] is False
    assert v["agreement"] == "CONFIRM"


def test_discrepancy_when_watcher_passes_but_recorded_failed(tmp_path):
    v = _radj(_submission("ex-c", oracle="FAIL", reach="WIRED"), tmp_path,
              oracle="PASS", reach="WIRED", recomputed_hash="hash-ok")
    assert v["slash_grounds"] is False
    assert v["recorded_passes_both"] is False
    assert v["agreement"] == "DISCREPANCY"


def test_discrepancy_when_watcher_fails_but_recorded_passed(tmp_path):
    # Cheater-caught direction: in-band let it through (recorded PASS), watcher independently FAILs.
    v = _radj(_submission("ex-w", oracle="PASS", reach="WIRED"), tmp_path,
              oracle="FAIL", reach="WIRED", recomputed_hash="hash-ok")
    assert v["slash_grounds"] is True
    assert v["recorded_passes_both"] is True
    assert v["agreement"] == "DISCREPANCY"


def test_reachability_orphan_is_slash_grounds(tmp_path):
    v = _radj(_submission("ex-o", oracle="PASS", reach="WIRED"), tmp_path,
              oracle="PASS", reach="ORPHAN", recomputed_hash="hash-ok")
    assert v["slash_grounds"] is True
    assert v["watcher_passes_both"] is False


def test_reachability_exempt_passes(tmp_path):
    v = _radj(_submission("ex-x", oracle="PASS", reach="EXEMPT"), tmp_path,
              oracle="PASS", reach="EXEMPT", recomputed_hash="hash-ok")
    assert v["watcher_passes_both"] is True
    assert v["slash_grounds"] is False
    assert v["agreement"] == "CONFIRM"


def test_real_hash_mismatch_is_tamper_discrepancy(tmp_path):
    # A real (non-empty) recomputed hash that DIFFERS from recorded → positive tamper.
    v = _radj(_submission("ex-d", oracle="PASS", reach="WIRED", commit_hash="hash-ok"), tmp_path,
              oracle="PASS", reach="WIRED", recomputed_hash="DIFFERENT-REAL-HASH")
    assert v["tamper"] is True
    assert v["slash_grounds"] is True
    assert v["agreement"] == "DISCREPANCY"  # recorded PASS but tamper detected


# ── ABSTAIN: inability to verify is NEVER grounds to slash ────────────────────

def test_abstain_when_oracle_raises(tmp_path):
    def boom(**kw):
        raise RuntimeError("oracle exploded")
    grade, sweep, hsh = _stub_gates(reach="WIRED", recomputed_hash="hash-ok")
    v = watcher.re_adjudicate_submission(
        _submission("ex-e", oracle="FAIL", reach="WIRED"),
        worktree=str(tmp_path), repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, job_dir=tmp_path, task_id="7", start_commit="base", base_ref="base",
        _grade=boom, _sweep=sweep, _hash=hsh,
    )
    assert v["watcher_oracle_error"] is True
    assert v["verified"] is False
    assert v["slash_grounds"] is False     # could not verify → NOT grounds to slash
    assert v["agreement"] == "ABSTAIN"


def test_abstain_when_oracle_detail_has_error(tmp_path):
    # grade_card is fail-closed: it can return ("FAIL", {"error": ...}) for an INFRA error,
    # which must NOT be read as a genuine independent fail.
    v = _radj(_submission("ex-f", oracle="FAIL", reach="WIRED"), tmp_path,
              oracle="FAIL", detail={"error": "oracle CLI crashed"}, reach="WIRED", recomputed_hash="hash-ok")
    assert v["watcher_oracle_error"] is True
    assert v["slash_grounds"] is False
    assert v["agreement"] == "ABSTAIN"


def test_abstain_when_no_worktree(tmp_path):
    # Worktree creation failed: never fall back to repo_root HEAD; reachability/hash abstain.
    grade, sweep, hsh = _stub_gates(oracle="PASS", reach="WIRED", recomputed_hash="hash-ok")
    v = watcher.re_adjudicate_submission(
        _submission("ex-n", oracle="PASS", reach="WIRED"),
        worktree=None, repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, job_dir=tmp_path, task_id="7", start_commit="base", base_ref="base",
        _grade=grade, _sweep=sweep, _hash=hsh,
    )
    assert v["watcher_reachability"] == "ABSTAIN"
    assert v["tamper"] is False           # cannot claim tamper without a real recompute
    assert v["hash_recomputed"] is False


def test_sweep_raises_is_abstain_reach(tmp_path):
    def boom_sweep(task_id, start_commit, cwd=None):
        raise RuntimeError("grep blew up")
    grade, _sweep, hsh = _stub_gates(oracle="PASS", recomputed_hash="hash-ok")
    v = watcher.re_adjudicate_submission(
        _submission("ex-s", oracle="PASS", reach="WIRED"),
        worktree=str(tmp_path), repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, job_dir=tmp_path, task_id="7", start_commit="base", base_ref="base",
        _grade=grade, _sweep=boom_sweep, _hash=hsh,
    )
    assert v["watcher_reachability"] == "ERROR"
    assert v["slash_grounds"] is False    # ERROR reachability is not ORPHAN → no grounds


# ── re_adjudicate_job: ledger + read-only ────────────────────────────────────

def test_job_appends_one_ledger_row_with_decisions(tmp_path):
    job_dir = tmp_path / "jobs" / "job-1"
    _write_job(job_dir, [
        _submission("ex-a", oracle="PASS", reach="WIRED"),
        _submission("ex-b", oracle="FAIL", reach="WIRED"),
    ], job_id="job-1")
    ledger = tmp_path / "watcher.jsonl"
    grade, sweep, hsh = _stub_gates(oracle="PASS", reach="WIRED", recomputed_hash="hash-ok")
    rec = watcher.re_adjudicate_job(
        job_dir=job_dir, repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, task_id="7", start_commit="base", base_ref="base",
        now="2026-06-17T00:00:00Z", ledger_path=ledger,
        _grade=grade, _sweep=sweep, _hash=hsh, _worktree_for=lambda sha: str(tmp_path),
    )
    assert rec["ok"] is True
    assert rec["observations"] == 2
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["job_id"] == "job-1"
    assert rows[0]["decisions"] == 1      # one recorded-fail (ex-b) → one slash decision
    assert "confirmed_slashes" in rows[0]


def test_job_missing_submissions_returns_error_no_ledger(tmp_path):
    job_dir = tmp_path / "jobs" / "empty"
    job_dir.mkdir(parents=True)
    ledger = tmp_path / "watcher.jsonl"
    rec = watcher.re_adjudicate_job(
        job_dir=job_dir, repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, task_id="7", start_commit="base", base_ref="base",
        now="2026-06-17T00:00:00Z", ledger_path=ledger, _worktree_for=lambda sha: str(tmp_path),
    )
    assert rec["ok"] is False
    assert not ledger.exists()


def test_job_writes_only_watcher_ledger(tmp_path):
    job_dir = tmp_path / "jobs" / "job-1"
    _write_job(job_dir, [_submission("ex-a")], job_id="job-1")
    ledger = tmp_path / "watcher.jsonl"
    reputation = tmp_path / "reputation.jsonl"
    telemetry = tmp_path / "telemetry.jsonl"
    grade, sweep, hsh = _stub_gates(recomputed_hash="hash-ok")
    watcher.re_adjudicate_job(
        job_dir=job_dir, repo_root=str(tmp_path), card_path=tmp_path / "card.json",
        held_root=tmp_path, task_id="7", start_commit="base", base_ref="base",
        now="2026-06-17T00:00:00Z", ledger_path=ledger,
        _grade=grade, _sweep=sweep, _hash=hsh, _worktree_for=lambda sha: str(tmp_path),
    )
    assert ledger.exists()
    assert not reputation.exists()
    assert not telemetry.exists()


# ── permit_enforce_slash: the fail-closed real-slash gate ────────────────────

def _seed_ledger(ledger: Path, *, decisions: int, confirmed: int, job_id: str = "hist") -> None:
    ledger.write_text(json.dumps({
        "job_id": job_id, "ts": "2026-06-01T00:00:00Z",
        "decisions": decisions, "confirmed_slashes": confirmed,
        "discrepancies": 0, "observations": decisions, "confirms": confirmed,
    }) + "\n")


def test_permit_blocks_below_min_observations(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS - 1, confirmed=watcher.MIN_OBSERVATIONS - 1)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert out["observations"] < watcher.MIN_OBSERVATIONS


def test_permit_blocks_on_discrepancy_among_slashes(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-c", agreement="DISCREPANCY", slash_grounds=False, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "ex-c" in out["discrepancies"]


def test_permit_blocks_on_cheating_winner_discrepancy(tmp_path):
    # The slashed racer is confirmed, but a WINNER is a discrepancy (watcher fails one the
    # in-band adjudicator passed) → the whole job is blocked.
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),     # confirmed slash
        _v("ex-win", agreement="DISCREPANCY", slash_grounds=True, recorded_passes_both=True),  # cheating winner
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "ex-win" in out["discrepancies"]


def test_permit_blocks_on_abstained_slash(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-a", agreement="ABSTAIN", slash_grounds=False, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False


def test_permit_blocks_on_abstained_winner(tmp_path):
    # Real coin moves only when the watcher reproduced the WHOLE adjudication — an
    # unverifiable (ABSTAIN) winner blocks the slash even though the loser is confirmed.
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),    # confirmed slash
        _v("ex-win", agreement="ABSTAIN", slash_grounds=False, recorded_passes_both=True),   # unverified winner
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "ex-win" in out["abstained"]


def test_permit_reason_surfaces_winner_discrepancy_over_empty_slash(tmp_path):
    # A cheating winner (recorded PASS, watcher DISCREPANCY) with NO to-be-slashed
    # subs must surface the discrepancy in the reason, not a benign 'no to-be-slashed'.
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-win", agreement="DISCREPANCY", slash_grounds=True, recorded_passes_both=True),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "ex-win" in out["discrepancies"]
    assert "discrepanc" in out["reason"].lower()
    assert "no to-be-slashed" not in out["reason"].lower()


def test_permit_blocks_on_empty_to_slash(tmp_path):
    # No to-be-slashed submissions → never a blanket green-light.
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-a", agreement="CONFIRM", slash_grounds=False, recorded_passes_both=True),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "no to-be-slashed" in out["reason"].lower()


def test_permit_allows_when_confirmed_and_track_record(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-a", agreement="CONFIRM", slash_grounds=False, recorded_passes_both=True),    # clean winner
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),    # confirmed slash
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is True
    assert out["confirmed"] == ["ex-b"]
    assert out["discrepancies"] == []


def test_permit_blocks_mixed_batch_one_discrepancy_vetoes(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),
        _v("ex-c", agreement="DISCREPANCY", slash_grounds=False, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "ex-c" in out["discrepancies"]


def test_permit_excludes_in_flight_job_from_track_record(tmp_path):
    # The current job's own ledger row must NOT count toward its own gate.
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS, job_id="job-1")
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger, current_job_id="job-1")
    assert out["permitted"] is False           # only prior (excluded) row existed → 0 obs
    assert out["observations"] == 0


def test_permit_concordance_boundary(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    # exactly threshold → permitted
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS,
                 confirmed=round(watcher.ACCURACY_THRESHOLD * watcher.MIN_OBSERVATIONS))
    record = {"job_id": "job-1", "submissions": [
        _v("ex-b", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),
    ]}
    assert watcher.permit_enforce_slash(record, ledger_path=ledger)["permitted"] is True
    # below threshold → blocked
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS,
                 confirmed=int(0.90 * watcher.MIN_OBSERVATIONS))
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert out["permitted"] is False
    assert "track record" in out["reason"].lower()


def test_permit_confirms_tamper_slash(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    record = {"job_id": "job-1", "submissions": [
        _v("ex-t", agreement="CONFIRM", slash_grounds=True, recorded_passes_both=False),
    ]}
    out = watcher.permit_enforce_slash(record, ledger_path=ledger)
    assert "ex-t" in out["confirmed"]
    assert out["permitted"] is True


def test_permit_fail_closed_on_bad_record(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    out = watcher.permit_enforce_slash({"submissions": "not-a-list"}, ledger_path=ledger)
    assert out["permitted"] is False
    assert out["reason"]


# ── concordance summary + CLI handlers ───────────────────────────────────────

def test_concordance_summary_reports_readiness(tmp_path):
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    summ = watcher.concordance_summary(ledger)
    assert summ["observations"] == watcher.MIN_OBSERVATIONS
    assert summ["concordance"] == 1.0
    assert summ["real_slash_ready"] is True


def test_concordance_summary_empty_ledger_not_ready(tmp_path):
    summ = watcher.concordance_summary(tmp_path / "missing.jsonl")
    assert summ["observations"] == 0
    assert summ["real_slash_ready"] is False


def test_concordance_clamps_malformed_rows(tmp_path):
    # A malformed row with confirmed > decisions must not inflate concordance past 1.0.
    ledger = tmp_path / "watcher.jsonl"
    ledger.write_text(json.dumps({"job_id": "bad", "decisions": 5, "confirmed_slashes": 999}) + "\n")
    summ = watcher.concordance_summary(ledger)
    assert summ["concordance"] <= 1.0


def test_concordance_ignores_nonnumeric_rows(tmp_path):
    # A malformed ledger row with a non-numeric field must not crash watcher-status.
    ledger = tmp_path / "watcher.jsonl"
    ledger.write_text(
        json.dumps({"job_id": "bad", "decisions": "oops", "confirmed_slashes": None}) + "\n"
        + json.dumps({"job_id": "ok", "decisions": 4, "confirmed_slashes": 4}) + "\n"
    )
    summ = watcher.concordance_summary(ledger)   # must not raise
    assert summ["observations"] == 4             # only the valid row counts


def test_resolve_repo_root_falls_back_outside_git(tmp_path):
    from prd_taskmaster.tournament.cmd import _resolve_repo_root
    # A non-git directory → falls back to the default rather than raising.
    assert _resolve_repo_root(cwd=str(tmp_path), default="SENTINEL") == "SENTINEL"


def test_cmd_watcher_status_emits_ok_json(tmp_path, capsys):
    import argparse
    from prd_taskmaster.tournament.cmd import cmd_watcher_status
    ledger = tmp_path / "watcher.jsonl"
    _seed_ledger(ledger, decisions=watcher.MIN_OBSERVATIONS, confirmed=watcher.MIN_OBSERVATIONS)
    with pytest.raises(SystemExit) as exc:
        cmd_watcher_status(argparse.Namespace(ledger_path=str(ledger)))
    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["real_slash_ready"] is True


def test_cmd_watcher_run_missing_job_is_fail_closed(tmp_path, capsys):
    import argparse
    from prd_taskmaster.tournament.cmd import cmd_watcher_run
    ledger = tmp_path / "watcher.jsonl"
    args = argparse.Namespace(
        job=str(tmp_path / "no-such-job"), repo_root=".", card=str(tmp_path / "card.json"),
        task="7", base_ref="base", held_root=str(tmp_path / "cdd"), ledger_path=str(ledger),
    )
    with pytest.raises(SystemExit) as exc:
        cmd_watcher_run(args)
    assert exc.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert not ledger.exists()
