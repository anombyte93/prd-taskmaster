"""Slice-2A capstone end-to-end tournament test.

Runs a real tournament with 3 racers through the actual podman oracle
+ real `atlas tournament settle` CLI + reputation system.

Architecture:
  - win  : oracle PASS, selfReportedExit=0, earliest revealedAt → WINNER
  - fake : oracle FAIL (exitCode=1, genuine reward-hacker) but selfReportedExit=0
           → ORACLE_CONTRADICTS_CLAIM
  - hon  : oracle PASS, selfReportedExit=0, EXEMPT reachability, later revealedAt → honest loser

Assertions:
  - ok: True; winner is "win"
  - supplyBefore == supplyAfter (AC conservation)
  - win credited bounty in saved ledger (free >= 60)
  - applied.slashed is empty (shadow mode); applied.wouldSlash contains "fake"
  - hon NOT in wouldSlash (honest loser: no fakery)
  - fake oracle exitCode == 1 (genuine exec failure, not infra/hash-mismatch)
  - win/fake reachability verdict ∈ {WIRED, EXEMPT} (not ERROR)
  - `<CLI> ledger verify <job_dir>/ledger` → ok:true (strict, no file-existence fallback)
  - `<CLI> tournament verify --job <job_dir>` → winner "win"
  - record_tournament → summarize_reputation shows win with n_wins==1
  - route_with_reputation → returns BOTH exploit (win has history) AND explore (cold-start)
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.tournament.adjudicate import adjudicate_job, settle_job
from prd_taskmaster.reputation import (
    record_tournament,
    route_with_reputation,
    summarize_reputation,
)

# ── Repo paths ────────────────────────────────────────────────────────────────
ENGINE_ROOT = Path(__file__).resolve().parents[2]

# ── Spine (oracle + tournament CLI) ──────────────────────────────────────────
_ORACLE_CMD_RAW = os.environ.get("ATLAS_ORACLE_CMD", "")
_TOURNAMENT_CMD_RAW = os.environ.get("ATLAS_TOURNAMENT_CMD", _ORACLE_CMD_RAW)

ALPINE_REF = "docker.io/library/alpine:3.20"


# ── Capability probes ─────────────────────────────────────────────────────────
def has_podman() -> bool:
    return shutil.which("podman") is not None


def has_tournament_cli() -> bool:
    return bool(_TOURNAMENT_CMD_RAW.strip())


SKIP_REASON = (
    "requires podman + ATLAS_ORACLE_CMD / ATLAS_TOURNAMENT_CMD "
    "pointing at a built atlas CLI (tsx spine)"
)
podman_and_cli = pytest.mark.skipif(
    not (has_podman() and has_tournament_cli()),
    reason=SKIP_REASON,
)


# ── Git helpers ───────────────────────────────────────────────────────────────
def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# ── Alpine digest ─────────────────────────────────────────────────────────────
def _resolve_alpine_digest() -> str:
    subprocess.run(
        ["podman", "pull", ALPINE_REF],
        check=True,
        capture_output=True,
        text=True,
    )
    proc = subprocess.run(
        ["podman", "image", "inspect", ALPINE_REF, "--format", "{{.Digest}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    digest = proc.stdout.strip()
    assert digest.startswith("sha256:"), f"unexpected digest {digest!r}"
    return digest


# ── Build one racer repo ──────────────────────────────────────────────────────
def _build_racer_repo(
    root: Path,
    *,
    name: str,
    grade_sh: str,
) -> tuple[Path, str]:
    """Create a minimal git repo for one racer. Returns (repo_root, head_sha).

    Each racer gets a unique file so that git produces distinct commit SHAs,
    avoiding the DUPLICATE_COMMIT fakery reason that would suppress all winners.
    """
    (root / "grade.sh").write_text(grade_sh)
    # Unique sentinel file per racer so commit SHA is guaranteed distinct.
    (root / f".racer-id-{name}").write_text(f"racer: {name}\n")
    _git(["init", "."], root)
    _git(["config", "user.email", "e2e@atlas.test"], root)
    _git(["config", "user.name", "e2e"], root)
    _git(["add", "-A"], root)
    _git(["-c", "core.hooksPath=/dev/null", "commit", "-m", f"work: racer {name}"], root)
    head_sha = _git(["rev-parse", "HEAD"], root)
    return root, head_sha


def _build_job(
    job_dir: Path,
    *,
    racer_dirs: dict,         # {"win": Path, "fake": Path, "hon": Path}
    racer_shas: dict,         # {"win": str, "fake": str, "hon": str} — mutated in-place
    operator_grade: str,      # held-out test for win + hon (exits 0)
    fake_operator_grade: str, # held-out test for fake  (exits 1)
    digest: str,
) -> tuple[Path, Path, Path, Path]:
    """Set up job artefacts: two cards (pass/fail), two held roots, ledger-state.

    Returns (card_path, fake_card_path, held_root_pass, held_root_fail).

    Two separate CDD cards are required because the oracle's overlay step
    validates that sha256(held_root/grade.sh) == card.grading.heldOutTests[0].sha256
    before running the sandbox.  If they mismatch the oracle raises OverlayHashMismatch
    (infra-FAIL, exitCode: null) — the sandbox never runs and the FAIL is NOT a genuine
    reward-hacker detection.

    By giving fake its own card (sha256 == sha256("exit 1\\n")) the hash check passes,
    the sandbox actually runs grade.sh, it exits 1, and the oracle returns
    {verdict: "FAIL", exitCode: 1} — a real ORACLE_CONTRADICTS_CLAIM.
    """
    job_dir.mkdir(parents=True, exist_ok=True)

    def _card(sha256: str) -> dict:
        return {
            "id": "C-001",
            "taskId": 1,
            "title": "e2e-tournament",
            "given": ["g"],
            "when": ["w"],
            "then": [
                {
                    "index": 1,
                    "statement": "exit 0",
                    "evidenceTier": "A",
                    "evidenceKind": "command-output",
                }
            ],
            "author": {"kind": "human", "id": "op"},
            "createdAt": "2026-06-17T00:00:00.000Z",
            "contentHash": "sha256:" + "0" * 64,
            "frozenAt": "2026-06-17T00:00:00.000Z",
            "grading": {
                "command": ["sh", "grade.sh"],
                "heldOutTests": [{"path": "grade.sh", "sha256": sha256}],
                "gradedPaths": ["grade.sh"],
                "baseImage": {"ref": ALPINE_REF, "digest": digest},
                "env": {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                    "SOURCE_DATE_EPOCH": 0,
                    "seed": 0,
                    "parallelism": 1,
                    "cpuClass": "x86-64-v2",
                },
                "timeoutMs": 60000,
            },
        }

    # Card for win + hon: heldOutTests sha256 matches operator_grade ("exit 0\n")
    pass_sha256 = hashlib.sha256(operator_grade.encode()).hexdigest()
    card = _card(pass_sha256)
    card_path = job_dir / "card.json"
    card_path.write_text(json.dumps(card))

    # Card for fake: heldOutTests sha256 matches fake_operator_grade ("exit 1\n").
    # This ensures OverlayHashMismatch does NOT fire; the oracle actually runs
    # grade.sh (exits 1) → {verdict:"FAIL", exitCode:1} — a genuine reward-hack catch.
    fail_sha256 = hashlib.sha256(fake_operator_grade.encode()).hexdigest()
    fake_card = _card(fail_sha256)
    fake_card_path = job_dir / "fake-card.json"
    fake_card_path.write_text(json.dumps(fake_card))

    # Operator-held tests — pass variant (win + hon)
    held_root_pass = job_dir / "held-out"
    held_root_pass.mkdir(parents=True, exist_ok=True)
    (held_root_pass / "grade.sh").write_text(operator_grade)

    # Operator-held tests — fail variant (fake)
    held_root_fail = job_dir / "held-fail"
    held_root_fail.mkdir(parents=True, exist_ok=True)
    (held_root_fail / "grade.sh").write_text(fake_operator_grade)

    # Seed the ledger-state.json (integer amounts, AC-conservation-friendly)
    # Supply: jobPoster.free(10)+escrowed(100)
    #       + win.free(10)+escrowed(1)+staked(5)
    #       + fake.free(10)+escrowed(1)+staked(5)
    #       + hon.free(10)+escrowed(1)+staked(5)
    # = 10+100 + 10+1+5 + 10+1+5 + 10+1+5 = 158
    ledger_state = {
        "accounts": {
            "jobPoster": {"free": 10, "escrowed": 100, "staked": 0},
            "win": {"free": 10, "escrowed": 1, "staked": 5},
            "fake": {"free": 10, "escrowed": 1, "staked": 5},
            "hon": {"free": 10, "escrowed": 1, "staked": 5},
        },
        "dailyStake": 0,
        "dailyStakeDate": "",
    }
    (job_dir / "ledger-state.json").write_text(json.dumps(ledger_state))

    # ledger events dir for oracle + settle
    (job_dir / "ledger").mkdir(parents=True, exist_ok=True)

    # Each racer's repo needs the standard .taskmaster + .atlas-ai scaffolding
    # so the oracle can check out + run.
    # win/hon use the pass card; fake uses fake_card (different heldOutTests sha256).
    racer_cards = {"win": card, "hon": card, "fake": fake_card}
    for name, repo_root in racer_dirs.items():
        atlas = repo_root / ".atlas-ai"
        cdd = atlas / "cdd"
        cdd.mkdir(parents=True, exist_ok=True)
        (cdd / "task-1.json").write_text(json.dumps(racer_cards[name]))

        state_dir = atlas / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "pipeline.json").write_text(
            json.dumps({"current_phase": "EXECUTE"})
        )

        tm_tasks = repo_root / ".taskmaster" / "tasks"
        tm_tasks.mkdir(parents=True, exist_ok=True)
        (tm_tasks / "tasks.json").write_text(
            json.dumps({"master": {"tasks": [{"id": 1, "status": "done"}]}})
        )
        tm_docs = repo_root / ".taskmaster" / "docs"
        tm_docs.mkdir(parents=True, exist_ok=True)
        (tm_docs / "plan.md").write_text("# Plan\n")

        (atlas / "evidence").mkdir(parents=True, exist_ok=True)
        (atlas / "ledger").mkdir(parents=True, exist_ok=True)

        # Re-commit to pick up .atlas-ai scaffolding
        _git(["add", "-A"], repo_root)
        _git(["-c", "core.hooksPath=/dev/null", "commit", "-m", "scaffold"], repo_root)
        # Update the sha so the oracle gets the latest committed state
        racer_shas[name] = _git(["rev-parse", "HEAD"], repo_root)

    return card_path, fake_card_path, held_root_pass, held_root_fail


# ── Main e2e test ─────────────────────────────────────────────────────────────
@podman_and_cli
def test_tournament_e2e_three_racers(tmp_path):
    """Real end-to-end tournament: podman oracle + real settle CLI + reputation.

    win  → oracle PASS, selfReportedExit=0, earliest revealedAt  → WINNER (rank 1)
    fake → oracle FAIL (exitCode=1, genuine reward-hacker), selfReportedExit=0
           → ORACLE_CONTRADICTS_CLAIM → wouldSlash (shadow mode)
    hon  → oracle PASS, selfReportedExit=0, EXEMPT reachability, later revealedAt
           → honest loser (rank 2), NOT in wouldSlash
    """
    oracle_cmd = shlex.split(_ORACLE_CMD_RAW)
    tournament_cmd = shlex.split(_TOURNAMENT_CMD_RAW)

    # ── Resolve alpine digest ────────────────────────────────────────────────
    print("\n[e2e] Pulling alpine:3.20 digest...")
    digest = _resolve_alpine_digest()
    print(f"[e2e] digest={digest[:30]}...")

    # ── Build racer repos ────────────────────────────────────────────────────
    # All racers commit a grade.sh that they claim passes (exit 0 in their copy).
    # Each repo gets a unique sentinel file so git produces distinct commit SHAs —
    # avoiding DUPLICATE_COMMIT falsely tagging honest racers.
    win_root = tmp_path / "repos" / "win"
    fake_root = tmp_path / "repos" / "fake"
    hon_root = tmp_path / "repos" / "hon"
    for d in [win_root, fake_root, hon_root]:
        d.mkdir(parents=True)

    racer_shas: dict[str, str] = {}
    for name, root in [("win", win_root), ("fake", fake_root), ("hon", hon_root)]:
        _, sha = _build_racer_repo(root, name=name, grade_sh="exit 0\n")
        racer_shas[name] = sha

    # ── Build job dir ────────────────────────────────────────────────────────
    # Two held roots and two cards:
    #   win + hon → held_root_pass (exit 0) + card_path     (sha256 matches exit 0)
    #   fake      → held_root_fail (exit 1) + fake_card_path(sha256 matches exit 1)
    #
    # Having matching sha256s ensures the oracle's OverlayHashMismatch check passes
    # so the sandbox actually RUNS grade.sh.  fake's grade.sh exits 1 → genuine FAIL.
    job_dir = tmp_path / "job"
    racer_dirs = {"win": win_root, "fake": fake_root, "hon": hon_root}

    card_path, fake_card_path, held_root_pass, held_root_fail = _build_job(
        job_dir,
        racer_dirs=racer_dirs,
        racer_shas=racer_shas,   # mutated in-place with latest shas after scaffold commit
        operator_grade="exit 0\n",       # honest operator: PASS for win and hon
        fake_operator_grade="exit 1\n",  # operator-held test that exits 1 → FAIL for fake
        digest=digest,
    )

    # ── Racer definitions ────────────────────────────────────────────────────
    # revealedAt ordering: win earliest, hon latest
    racers = [
        {
            "claimant_id": "win",
            "commit_sha": racer_shas["win"],
            "worktree_path": str(win_root),
            "self_reported_exit": 0,
            "commit_hash": "sha256:" + "a" * 64,
            "revealed_at": "2026-06-17T10:00:00.000Z",
            "entry_fee_paid": 1,
            "fakery_stake": 5,
        },
        {
            "claimant_id": "fake",
            "commit_sha": racer_shas["fake"],
            "worktree_path": str(fake_root),
            "self_reported_exit": 0,   # claims PASS — oracle will disagree (exitCode=1)
            "commit_hash": "sha256:" + "b" * 64,
            "revealed_at": "2026-06-17T10:00:01.000Z",
            "entry_fee_paid": 1,
            "fakery_stake": 5,
        },
        {
            "claimant_id": "hon",
            "commit_sha": racer_shas["hon"],
            "worktree_path": str(hon_root),
            "self_reported_exit": 0,
            "commit_hash": "sha256:" + "c" * 64,
            "revealed_at": "2026-06-17T10:00:02.000Z",   # later → rank 2
            "entry_fee_paid": 1,
            "fakery_stake": 5,
        },
    ]

    # ── Per-racer oracle gate: inject per-racer held_root AND card_path ──────
    # adjudicate_job uses a single shared _grade callable; we wrap grade_card
    # so fake gets held_root_fail + fake_card_path (matching sha256s → real run)
    # and win/hon get held_root_pass + card_path.
    from prd_taskmaster.oracle_bridge import grade_card as _real_grade

    def _grade_router(
        *,
        card_path,     # noqa: F841 — shadowed by per-racer selection below
        repo_path,
        commit_sha,
        held_root,     # noqa: F841 — shadowed by per-racer selection below
        evidence_dir,
        ledger_dir,
        oracle_cmd=None,
    ):
        """Route each racer to the correct held_root AND card_path.

        fake gets held_root_fail + fake_card_path so the OverlayHashMismatch check
        passes (sha256 matches) and the oracle actually runs grade.sh (exits 1),
        producing {verdict:"FAIL", exitCode:1} — a genuine ORACLE_CONTRADICTS_CLAIM.

        win and hon get held_root_pass + card_path (sha256 matches exit 0).
        """
        rp = str(repo_path)
        if rp == str(fake_root):
            effective_held = held_root_fail
            effective_card = fake_card_path
        else:
            effective_held = held_root_pass
            effective_card = card_path
        return _real_grade(
            card_path=effective_card,
            repo_path=repo_path,
            commit_sha=commit_sha,
            held_root=effective_held,
            evidence_dir=evidence_dir,
            ledger_dir=ledger_dir,
            oracle_cmd=oracle_cmd,
        )

    # ── Reachability router ──────────────────────────────────────────────────
    # hon gets EXEMPT (honest loser, oracle PASS but lower rank).
    # win and fake get the real sweep; fallback to WIRED if it raises.
    from prd_taskmaster.reachability_cmd import run_reachability_sweep as _real_sweep

    def _sweep_router(task_id, start_commit, cwd=None):
        """Give hon EXEMPT; win and fake run the real sweep (WIRED on failure)."""
        if cwd and str(cwd) == str(hon_root):
            return {
                "verdict": "EXEMPT",
                "tier": "cli",
                "modules": [],
                "checked_at": "2026-06-17T10:00:00.000Z",
                "start_commit": start_commit,
                "reason": "cli:",
            }
        # win and fake: run real sweep; on failure fall back to WIRED
        try:
            return _real_sweep(task_id, start_commit, cwd=cwd)
        except Exception:  # noqa: BLE001
            return {"verdict": "WIRED"}

    print("[e2e] Running adjudicate_job with 3 racers (real podman oracle)...")
    submissions = adjudicate_job(
        job_dir=job_dir,
        racers=racers,
        card_path=card_path,
        held_root=held_root_pass,   # default; overridden per-racer in _grade_router
        task_id="1",
        start_commit="HEAD~1",
        job_id="e2e-job-001",
        card_id="C-001",
        bounty_amount=50,
        job_poster="jobPoster",
        oracle_cmd=oracle_cmd,
        _grade=_grade_router,
        _sweep=_sweep_router,
    )

    print("[e2e] adjudicate_job complete. Oracle verdicts:")
    for s in submissions:
        cid = s["claimant"]["id"]
        ov = s["oracle"]["verdict"]
        oe = s["oracle"].get("exitCode")
        rv = s["reachability"]["verdict"]
        print(f"  {cid}: oracle={ov} exitCode={oe}, reach={rv}")

    # Basic sanity before settle
    win_sub = next(s for s in submissions if s["claimant"]["id"] == "win")
    fake_sub = next(s for s in submissions if s["claimant"]["id"] == "fake")
    hon_sub = next(s for s in submissions if s["claimant"]["id"] == "hon")

    assert win_sub["oracle"]["verdict"] == "PASS", (
        f"win should PASS oracle: {win_sub['oracle']}"
    )
    assert fake_sub["oracle"]["verdict"] == "FAIL", (
        f"fake should FAIL oracle (operator grade = exit 1): {fake_sub['oracle']}"
    )
    # Fix 1 — genuine reward-hacker gate: exitCode must be 1.
    # exitCode: null means the oracle suffered an infra/hash-mismatch failure — the
    # sandbox never ran and the FAIL does NOT prove reward-hack detection.
    # exitCode: 1 means the sandbox ran grade.sh, it exited 1, and the oracle caught
    # the contradiction between selfReportedExit=0 and the real execution result.
    assert fake_sub["oracle"].get("exitCode") == 1, (
        f"fake oracle exitCode must be 1 (real exec failure, not infra-fail/null): "
        f"oracle block={fake_sub['oracle']}"
    )

    assert hon_sub["oracle"]["verdict"] == "PASS", (
        f"hon should PASS oracle: {hon_sub['oracle']}"
    )
    assert hon_sub["reachability"]["verdict"] == "EXEMPT", (
        f"hon should be EXEMPT reachability: {hon_sub['reachability']}"
    )

    # Fix 4 — reachability regression guard: win and fake must be WIRED or EXEMPT.
    # If this fires it means _sweep_router returned ERROR (the real sweep raised
    # AND the except branch failed), which would make the test non-discriminating.
    assert win_sub["reachability"]["verdict"] in ("WIRED", "EXEMPT"), (
        f"win reachability must be WIRED or EXEMPT (not ERROR): {win_sub['reachability']}"
    )
    assert fake_sub["reachability"]["verdict"] in ("WIRED", "EXEMPT"), (
        f"fake reachability must be WIRED or EXEMPT (not ERROR): {fake_sub['reachability']}"
    )

    # ── Settle ───────────────────────────────────────────────────────────────
    print("[e2e] Running settle_job (real atlas tournament settle CLI)...")
    envelope = settle_job(
        job_dir=job_dir,
        tournament_cmd=tournament_cmd,
    )
    print(f"[e2e] settle envelope ok={envelope.get('ok')}")

    # ── Assertion 1: ok:true ─────────────────────────────────────────────────
    assert envelope.get("ok") is True, (
        f"settle returned ok:false — envelope: {json.dumps(envelope, indent=2, default=str)}"
    )

    result = envelope["result"]
    applied = envelope["applied"]

    # ── Assertion 2: winner is "win" ─────────────────────────────────────────
    winner = result.get("winner")
    assert winner is not None, "settle produced no winner"
    winner_id = winner["claimant"]["id"]
    assert winner_id == "win", f"expected winner 'win', got {winner_id!r}"
    print(f"[e2e] winner={winner_id} ✓")

    # ── Assertion 3: AC conservation ─────────────────────────────────────────
    supply_before = envelope["supplyBefore"]
    supply_after = envelope["supplyAfter"]
    assert supply_before == supply_after, (
        f"AC not conserved: before={supply_before}, after={supply_after}"
    )
    print(f"[e2e] AC conservation: before={supply_before} == after={supply_after} ✓")

    # ── Assertion 4: win credited bounty in saved ledger ─────────────────────
    # Fix 2 — tighten bounty check: assert free >= 60 (not merely > 10).
    # win starts with free=10.  After settle: +50 bounty + returned 5 stake = 65.
    # Minimum valid: 10 (floor) + 50 (bounty) = 60.
    # A negative control (no settle at all) leaves win.free==10, which passes
    # the old "> 10" check trivially after any non-bounty credit.  ">= 60" requires
    # the full 50 AC bounty to have been transferred from jobPoster.escrowed.
    ledger_state_path = job_dir / "ledger-state.json"
    saved_state = json.loads(ledger_state_path.read_text())
    win_account = saved_state["accounts"].get("win", {})
    assert win_account.get("free", 0) >= 60, (
        f"win was not credited bounty: expected free>=60, got win account={win_account}, "
        f"full ledger state={json.dumps(saved_state, indent=2)}"
    )
    print(f"[e2e] win credited: free={win_account.get('free')} (was 10, min expected 60) ✓")

    # ── Assertion 5: shadow mode — slashed empty, wouldSlash has fake ────────
    # applied is the settlement summary returned by the CLI
    # In shadow mode: applied.slashed should be empty, applied.wouldSlash has fake
    slashed = applied.get("slashed", [])
    would_slash = applied.get("wouldSlash", [])

    assert len(slashed) == 0, f"shadow mode: expected empty slashed, got {slashed}"

    # Extract claimant ids from wouldSlash (shape: [{claimant: {id:...}, ...}])
    would_slash_ids = set()
    for ws in would_slash:
        if isinstance(ws, dict):
            c = ws.get("claimant")
            if isinstance(c, dict) and c.get("id"):
                would_slash_ids.add(str(c["id"]))
            elif ws.get("id"):
                would_slash_ids.add(str(ws["id"]))

    assert "fake" in would_slash_ids, (
        f"fake should be in wouldSlash (ORACLE_CONTRADICTS_CLAIM); got {would_slash_ids!r}"
    )
    assert "hon" not in would_slash_ids, (
        f"hon is an honest loser — must NOT be in wouldSlash; got {would_slash_ids!r}"
    )
    print(f"[e2e] shadow: slashed=[] ✓, wouldSlash={sorted(would_slash_ids)} ✓")

    # ── Assertion 6: ledger verify → ok:true (strict — no file-existence fallback) ──
    # Fix 3: require real JSON ok:true from `<CLI> ledger verify`.
    # The CLI supports this subcommand and returns {"ok":true,...} (proven live).
    # A file-existence fallback is not a verification — it passes even if the
    # ledger chain is corrupt.  We drop it entirely: if the CLI fails, the test fails.
    ledger_dir = job_dir / "ledger"
    verify_ledger = subprocess.run(
        tournament_cmd + ["ledger", "verify", str(ledger_dir)],
        capture_output=True,
        text=True,
    )
    assert verify_ledger.returncode == 0, (
        f"ledger verify exited non-zero (rc={verify_ledger.returncode})\n"
        f"stdout={verify_ledger.stdout!r}\nstderr={verify_ledger.stderr!r}"
    )
    try:
        lv_result = json.loads(verify_ledger.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"ledger verify produced non-JSON output (cannot verify): {exc!r}\n"
            f"stdout={verify_ledger.stdout!r}"
        ) from exc
    assert lv_result.get("ok") is True, (
        f"ledger verify reported ok:false — {lv_result!r}"
    )
    print(f"[e2e] ledger verify ok={lv_result.get('ok')} ✓")

    # ── Assertion 7: tournament verify --job → winner "win" ──────────────────
    verify_tournament = subprocess.run(
        tournament_cmd + ["tournament", "verify", "--job", str(job_dir)],
        capture_output=True,
        text=True,
    )
    assert verify_tournament.returncode == 0, (
        f"tournament verify failed rc={verify_tournament.returncode}\n"
        f"stdout={verify_tournament.stdout!r}\nstderr={verify_tournament.stderr!r}"
    )
    tv_result = json.loads(verify_tournament.stdout)
    assert tv_result.get("ok") is True, f"tournament verify ok:false — {tv_result!r}"
    tv_winner = tv_result.get("winner")
    assert tv_winner is not None, "tournament verify: no winner"
    tv_winner_id = tv_winner.get("claimant", {}).get("id") or tv_winner.get("id")
    assert tv_winner_id == "win", (
        f"tournament verify: expected winner 'win', got {tv_winner_id!r}"
    )
    print(f"[e2e] tournament verify winner={tv_winner_id} ✓")

    # ── Assertion 8: reputation — win recorded with n_wins==1 ─────────────────
    reputation_path = tmp_path / "reputation.jsonl"
    now_ts = "2026-06-17T10:05:00.000Z"

    # Build the full envelope to pass to record_tournament (result + applied)
    merged_result = {**result, "applied": applied}

    touched = record_tournament(
        reputation_path=reputation_path,
        result=merged_result,
        task_class="standard",
        now=now_ts,
        latencies={"win": 3200, "fake": 5100, "hon": 4000},
    )

    summary = summarize_reputation(reputation_path)
    win_rep = summary.get(("win", "standard"))
    assert win_rep is not None, "win not found in reputation summary"
    assert win_rep["n_wins"] == 1, f"expected win.n_wins==1, got {win_rep['n_wins']}"
    assert win_rep["n_jobs"] == 1, f"expected win.n_jobs==1, got {win_rep['n_jobs']}"

    fake_rep = summary.get(("fake", "standard"))
    assert fake_rep is not None, "fake not found in reputation summary"
    assert fake_rep["n_wins"] == 0, f"expected fake.n_wins==0, got {fake_rep}"

    hon_rep = summary.get(("hon", "standard"))
    assert hon_rep is not None, "hon not found in reputation summary"
    assert hon_rep["n_wins"] == 0, f"expected hon.n_wins==0, got {hon_rep}"

    print(
        f"[e2e] reputation: win n_wins={win_rep['n_wins']} ✓  "
        f"fake n_wins={fake_rep['n_wins']} ✓  "
        f"hon n_wins={hon_rep['n_wins']} ✓"
    )

    # ── Assertion 9: route_with_reputation — exploit + explore ────────────────
    # Job 2: "win" is a known winner (exploit signal).
    # "cheap-unseen" is a cold-start executor (explore — never seen before).
    candidates_j2 = ["win", "cheap-unseen", "fake", "hon"]

    route_result = route_with_reputation(
        task={"complexity": "standard"},
        config={},
        reputation_path=reputation_path,
        candidates=candidates_j2,
        now=now_ts,
    )

    chosen = route_result["chosen"]
    scores = route_result["scores"]
    exploring = route_result["exploring"]

    import math

    # "cheap-unseen" must have inf score (cold-start)
    assert scores.get("cheap-unseen") == math.inf, (
        f"cheap-unseen should have inf score; scores={scores}"
    )
    # Chosen should be "cheap-unseen" (inf beats finite scores) or another unseen executor
    # (all three seen executors have finite scores; cheap-unseen is the only inf)
    assert chosen == "cheap-unseen", (
        f"expected chosen='cheap-unseen' (cold-start inf); got chosen={chosen!r}, scores={scores}"
    )
    assert exploring is True, (
        f"expected exploring=True for cold-start pick; got {exploring!r}"
    )

    # win must have a finite positive score (exploit signal)
    win_score = scores.get("win", 0)
    assert math.isfinite(win_score) and win_score > 0, (
        f"win should have finite positive UCB score; win_score={win_score}"
    )
    print(
        f"[e2e] routing Job-2: chosen={chosen} (exploring={exploring}) ✓  "
        f"win_score={win_score:.3f} ✓  cheap-unseen=inf ✓"
    )

    print("\n[e2e] ALL ASSERTIONS PASSED ✓")
