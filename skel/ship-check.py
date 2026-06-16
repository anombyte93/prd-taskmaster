#!/usr/bin/env python3
"""Deterministic ship-check for prd-taskmaster pipelines.

Emits SHIP_CHECK_OK to stdout ONLY when all gates pass. Called by execute-task
at termination AND by Step 9 (--dry-run) as a per-task predicate.

Standalone: this file ships into user projects as `.atlas-ai/ship-check.py`. It
imports ONLY the stdlib and MUST stay that way (no `import prd_taskmaster` — that
package is not importable in a user project). The oracle gate therefore shells
the `atlas oracle grade` CLI directly via subprocess.

Gate logic (grounded against actual pipeline.json / tasks.json schemas
observed 2026-06-04 in ai-human-tasker):

  Gate 1 — pipeline.json: current_phase == "EXECUTE".
    During execution, EXECUTE is current_phase but NOT yet in
    phases_completed (the EXECUTE→completed transition happens AFTER
    ship-check passes). Older skel checked state.state == "complete" — that
    field does not exist in live data.

  Gate 2 — tasks.json: every master.tasks[].status == "done".
    No evidence_files field exists in tasks.json — that was a phantom check
    in the older skel.

  Gate 3 — CDD evidence: for each task ID, a CDD card exists at
    .atlas-ai/cdd/task-<id>.json OR a combined card whose name contains the
    id (e.g. task-10-11-12.json covers tasks 10, 11, 12). Cards are written
    by execute-task Step 5.

  Gate 4 — Plan file exists at .taskmaster/docs/plan.md OR
    docs/superpowers/plans/*.md (matches Phase 2 path fallback). The older
    skel checked .atlas-ai/ralph-loop-prompt.md — wrong path and irrelevant
    after /goal migration.

  Gate 5 (HARD, ORACLE) — Each DONE task is RE-GRADED by the atlas oracle.
    The submitter's own .atlas-ai/evidence/ is NOT trusted; the oracle
    re-executes the CDD card's grading against HEAD and writes its own
    evidence/ledger. This replaces the fakable "no non-zero Exit status N in
    evidence" grep — which silently PASSED when no evidence existed and had a
    self-grantable bypass token. Both the silent-pass loophole and the bypass
    token are GONE. The gate is FAIL-CLOSED: a missing card, a card with no
    grading block, a CLI crash, unparseable output, or any verdict other than
    "PASS" all BLOCK the ship.

Interface:
  python3 .atlas-ai/ship-check.py                              # standard gate
  python3 .atlas-ai/ship-check.py --dry-run                    # always exit 0; report on stderr
  python3 .atlas-ai/ship-check.py --cwd /path/to/project       # explicit project root

Exit codes:
  0 — SHIP_CHECK_OK (stdout: exactly "SHIP_CHECK_OK\n")
  1 — gate failures (stderr only; nothing on stdout — log watchers must not see partial matches)
  2 — script error (IO, JSON parse)
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def gate_pipeline(atlas: Path) -> Tuple[bool, List[str]]:
    pf = atlas / "state" / "pipeline.json"
    if not pf.exists():
        return False, ["pipeline.json missing at .atlas-ai/state/pipeline.json"]
    try:
        state = json.loads(pf.read_text())
    except json.JSONDecodeError as exc:
        return False, [f"pipeline.json invalid JSON: {exc}"]
    if state.get("current_phase") != "EXECUTE":
        return False, [f"pipeline.json current_phase != EXECUTE (got {state.get('current_phase')!r})"]
    return True, []


def gate_tasks(repo_root: Path) -> Tuple[bool, List[str], list]:
    tf = repo_root / ".taskmaster" / "tasks" / "tasks.json"
    if not tf.exists():
        return False, ["tasks.json missing at .taskmaster/tasks/tasks.json"], []
    try:
        tdata = json.loads(tf.read_text())
    except json.JSONDecodeError as exc:
        return False, [f"tasks.json invalid JSON: {exc}"], []
    # Accept both canonical formats: tagged {"master": {"tasks": [...]}}
    # and flat {"tasks": [...]} (Native Mode / fleet samples).
    tasks = tdata.get("master", {}).get("tasks", [])
    if not tasks and isinstance(tdata.get("tasks"), list):
        tasks = tdata["tasks"]
    if not tasks:
        for value in tdata.values():
            if isinstance(value, dict) and isinstance(value.get("tasks"), list) and value["tasks"]:
                tasks = value["tasks"]
                break
    if not tasks:
        return False, ["tasks.json has no tasks (checked master.tasks, flat tasks, and tagged fallback)"], []
    failures: List[str] = []
    for t in tasks:
        if t.get("status") != "done":
            failures.append(f"task {t.get('id')} not done (status={t.get('status')!r})")
    return len(failures) == 0, failures, tasks


def _has_card_for(cdd_dir: Path, tid) -> bool:
    """A CDD card exists for task <tid> if task-<tid>.json exists OR any
    combined card filename's hyphen-separated id-list contains <tid>."""
    tid_str = str(tid)
    direct = cdd_dir / f"task-{tid_str}.json"
    if direct.exists():
        return True
    for card in cdd_dir.glob("task-*.json"):
        stem = card.stem
        if not stem.startswith("task-"):
            continue
        ids = stem[len("task-"):].split("-")
        if tid_str in ids:
            return True
    return False


def gate_cdd(atlas: Path, tasks: list) -> Tuple[bool, List[str]]:
    cdd_dir = atlas / "cdd"
    if not cdd_dir.exists():
        return False, [".atlas-ai/cdd/ directory missing"]
    failures: List[str] = []
    for t in tasks:
        tid = t.get("id")
        if tid is None:
            continue
        if not _has_card_for(cdd_dir, tid):
            failures.append(f"task {tid}: no CDD card at .atlas-ai/cdd/task-{tid}.json or any combined variant")
    return len(failures) == 0, failures


def gate_plan(repo_root: Path) -> Tuple[bool, List[str]]:
    if (repo_root / ".taskmaster" / "docs" / "plan.md").exists():
        return True, []
    superpowers = repo_root / "docs" / "superpowers" / "plans"
    if superpowers.exists() and any(superpowers.glob("*.md")):
        return True, []
    return False, ["no plan file at .taskmaster/docs/plan.md or docs/superpowers/plans/*.md"]


def _oracle_cmd() -> List[str]:
    """Configurable oracle CLI invocation. Default: the 'atlas' binary on PATH.

    Set ATLAS_ORACLE_CMD (shell-split) to change it, e.g.:
        ATLAS_ORACLE_CMD="node /path/to/atlas-protocol/apps/cli/dist/index.js"
    """
    raw = os.environ.get("ATLAS_ORACLE_CMD")
    if raw:
        return shlex.split(raw)
    return ["atlas"]


def _head_commit(repo_root: Path) -> str:
    """HEAD sha via `git rev-parse HEAD`. FAIL-CLOSED: any failure returns the
    sentinel "UNKNOWN" so the oracle mismatches the working tree and blocks."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    if proc.returncode != 0:
        return "UNKNOWN"
    sha = (proc.stdout or "").strip()
    return sha or "UNKNOWN"


def _card_path_for(cdd_dir: Path, tid) -> "Path | None":
    """Return the Path to the CDD card for task <tid>, or None if absent.

    Mirrors the _has_card_for existence check but returns the actual path so
    callers can read the card contents.  Prefers the direct task-<tid>.json;
    falls back to the first combined card whose hyphen-separated id-list
    contains <tid>.
    """
    tid_str = str(tid)
    direct = cdd_dir / f"task-{tid_str}.json"
    if direct.exists():
        return direct
    for card in cdd_dir.glob("task-*.json"):
        stem = card.stem
        if not stem.startswith("task-"):
            continue
        ids = stem[len("task-"):].split("-")
        if tid_str in ids:
            return card
    return None


def gate_reachability(repo_root: Path, tasks: list) -> Tuple[bool, List[str]]:
    """Gate 6 — block done wired/live tasks whose recorded reachability verdict
    is ORPHAN, ERROR, or absent.

    Reads the per-task verdict from the CDD card's 'reachability' block (written
    by execute-task step RA6). Does NOT re-execute the reachability sweep — the
    standalone skel must stay stdlib-only. FAIL-CLOSED on missing/unknown verdicts
    for wired/live done tasks.

    Tiers that require a reachability check: 'wired', 'live'.
    All other tiers (spike, domain-model, unset) are skipped.
    Non-done tasks are also skipped.
    """
    failures: List[str] = []
    cdd_dir = repo_root / ".atlas-ai" / "cdd"
    _REQUIRED_TIERS = {"wired", "live"}
    _PASS_VERDICTS = {"WIRED", "EXEMPT"}
    _FAIL_VERDICTS = {"ORPHAN", "ERROR"}

    for t in tasks:
        if t.get("status") != "done":
            continue
        tier = (
            t.get("phaseConfig", {}).get("tier")
            or t.get("tier")
            or "domain-model"
        )
        if tier not in _REQUIRED_TIERS:
            continue

        tid = t.get("id")
        card_path = _card_path_for(cdd_dir, tid)
        if card_path is None:
            failures.append(
                f"task {tid}: tier={tier} requires reachability but no CDD card found"
            )
            continue

        try:
            card = json.loads(card_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(
                f"task {tid}: tier={tier} — cannot read CDD card ({exc})"
            )
            continue

        reach = card.get("reachability")
        if not reach:
            failures.append(
                f"task {tid}: tier={tier} requires a reachability check, but its CDD card has"
                f" no 'reachability' block — run the execute-task reachability sweep, then wire"
                f" it or re-status deferred/scaffold"
            )
            continue

        verdict = reach.get("verdict") if isinstance(reach, dict) else None
        if verdict in _PASS_VERDICTS:
            continue
        elif verdict in _FAIL_VERDICTS:
            modules = reach.get("modules", []) if isinstance(reach, dict) else []
            mod_str = f" ({', '.join(modules)})" if modules else ""
            failures.append(
                f"task {tid}: reachability {verdict}{mod_str} — wire the module(s)"
                f" into the running system or re-status deferred/scaffold"
            )
        else:
            # Unknown / garbage verdict — fail-closed.
            failures.append(
                f"task {tid}: tier={tier} — unknown reachability verdict {verdict!r};"
                f" expected WIRED, EXEMPT, ORPHAN, or ERROR"
            )

    return len(failures) == 0, failures


def gate_oracle(repo_root: Path, tasks: list, head_commit: str) -> Tuple[bool, List[str]]:
    """Re-grade every DONE task via the atlas oracle CLI. FAIL-CLOSED.

    For each done task: the CDD card must exist and carry a 'grading' block,
    and the oracle must return verdict=="PASS". Anything else — missing card,
    no grading block, CLI crash, unparseable output, a non-PASS verdict —
    appends a failure. The submitter's evidence is NOT read here; the oracle
    re-executes the grading and writes its own evidence/ledger.
    """
    failures: List[str] = []
    atlas = repo_root / ".atlas-ai"
    held = atlas / "held-out"
    evidence = atlas / "evidence"
    ledger = atlas / "ledger"
    cmd_base = _oracle_cmd()

    for t in tasks:
        if t.get("status") != "done":
            continue
        tid = t.get("id")
        card_path = atlas / "cdd" / f"task-{tid}.json"
        if not card_path.exists():
            failures.append(f"task {tid}: no CDD card to grade")
            continue
        try:
            card = json.loads(card_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"task {tid}: cannot read CDD card ({exc})")
            continue
        if "grading" not in card:
            failures.append(f"task {tid}: CDD card has no grading block")
            continue

        cmd = cmd_base + [
            "oracle", "grade",
            "--repo", str(repo_root),
            "--commit", head_commit,
            "--card", str(card_path),
            "--held", str(held),
            "--evidence", str(evidence),
            "--ledger", str(ledger),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            failures.append(f"task {tid}: oracle CLI invocation failed ({exc})")
            continue

        try:
            parsed = json.loads(proc.stdout)
        except (json.JSONDecodeError, TypeError):
            failures.append(f"task {tid}: oracle produced no parseable JSON verdict (rc={proc.returncode})")
            continue

        verdict = parsed.get("verdict") if isinstance(parsed, dict) else None
        if verdict not in ("PASS", "FAIL"):
            failures.append(f"task {tid}: oracle verdict missing/invalid ({verdict!r})")
            continue
        if verdict == "FAIL":
            failures.append(f"task {tid}: oracle verdict FAIL")
            continue
        # verdict == "PASS" — the only path that does NOT append a failure.

    return len(failures) == 0, failures


def run_all_gates(repo_root: Path) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    atlas = repo_root / ".atlas-ai"

    _, f1 = gate_pipeline(atlas)
    failures.extend(f1)

    _, f2, tasks = gate_tasks(repo_root)
    failures.extend(f2)

    if tasks:
        _, f3 = gate_cdd(atlas, tasks)
        failures.extend(f3)

        head = _head_commit(repo_root)
        _, f5 = gate_oracle(repo_root, tasks, head)
        failures.extend(f5)

        _, f6 = gate_reachability(repo_root, tasks)
        failures.extend(f6)

    _, f4 = gate_plan(repo_root)
    failures.extend(f4)

    return len(failures) == 0, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic ship-check for prd-taskmaster pipelines.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all gates but always exit 0. Report goes to stderr. Used by execute-task Step 9 as a per-task predicate.")
    parser.add_argument("--cwd", type=str, default=None,
                        help="Project root (defaults to current working directory).")
    args = parser.parse_args()

    repo_root = Path(args.cwd).resolve() if args.cwd else Path.cwd()

    try:
        ok, failures = run_all_gates(repo_root)
    except Exception as exc:  # noqa: BLE001 — top-level guard
        print(f"FAIL: ship-check script error: {exc!r}", file=sys.stderr)
        return 2

    if args.dry_run:
        if ok:
            print("[DRY-RUN] all gates would pass", file=sys.stderr)
        else:
            print("[DRY-RUN] gate failures (would block):", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
        return 0

    if ok:
        print("SHIP_CHECK_OK")
        return 0

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
