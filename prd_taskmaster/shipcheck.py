#!/usr/bin/env python3
"""NON-BINDING status-display heuristic for prd-taskmaster pipelines.

This module is imported by status.py (dry_run=True) ONLY for display purposes.
It is NOT the binding ship gate — the binding gate is skel/ship-check.py
(oracle-backed, unfakable). Do not add an oracle call here.

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

  Gate 5 (display only) — No non-zero "Exit status N" line in any
    .atlas-ai/evidence/ file. This is a heuristic display signal only;
    the binding oracle check is in skel/ship-check.py. There is no override
    path — the gate result cannot be bypassed.

Interface (standalone shim, created in a later step):
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
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

EXIT_STATUS_RE = re.compile(r"\bExit status\s+(\d+)\b", re.IGNORECASE)


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
    by execute-task step RA6). Does NOT re-execute the reachability sweep.
    FAIL-CLOSED on missing/unknown verdicts for wired/live done tasks.

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
            raw_modules = reach.get("modules", []) if isinstance(reach, dict) else []
            # modules may be plain strings (test fixtures / legacy) or dicts written
            # by reachability.sweep_task with keys {verdict, module, importers, ...}.
            modules = [
                m["module"] if isinstance(m, dict) else str(m)
                for m in raw_modules
            ]
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


def gate_exit_codes(atlas: Path) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    evidence_dir = atlas / "evidence"
    if not evidence_dir.exists():
        # Gate 3 (CDD) catches missing evidence; this gate is silent when no evidence exists
        return True, []
    for f in evidence_dir.rglob("*"):
        if not f.is_file():
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for match in EXIT_STATUS_RE.finditer(text):
            try:
                code = int(match.group(1))
            except (ValueError, IndexError):
                continue
            if code != 0:
                rel = f.relative_to(atlas.parent) if atlas.parent in f.parents else f
                failures.append(f"non-zero exit in {rel}: Exit status {code}")
                break  # one report per file is enough
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

        _, f6 = gate_reachability(repo_root, tasks)
        failures.extend(f6)

    _, f4 = gate_plan(repo_root)
    failures.extend(f4)

    _, f5 = gate_exit_codes(atlas)
    failures.extend(f5)

    return len(failures) == 0, failures


def run_ship_check(cwd: Optional[str] = None, dry_run: bool = False) -> dict:
    """Importable ship-check entry point. NON-BINDING display heuristic only.
    NEVER calls sys.exit. There is no override path.

    Args:
      cwd: project root (defaults to current working directory).
      dry_run: when True, the returned exit_code is forced to 0 regardless of
               gate outcome (gates still run and the report is preserved).

    Returns a dict:
      passed: bool        — True when all gates pass.
      failures: list[str] — per-gate failure detail (empty when passed).
      dry_run: bool
      exit_code: int      — 0 / 1 / 2 mirroring the CLI contract.
      error: str | None   — populated on a script error (exit_code 2).
      stdout: str | None  — the exact stdout line the CLI would print, if any.
    """
    repo_root = Path(cwd).resolve() if cwd else Path.cwd()

    try:
        ok, failures = run_all_gates(repo_root)
    except Exception as exc:  # noqa: BLE001 — top-level guard
        return {
            "passed": False,
            "failures": [],
            "dry_run": dry_run,
            "exit_code": 2,
            "error": f"ship-check script error: {exc!r}",
            "stdout": None,
        }

    if dry_run:
        exit_code = 0
        stdout = None
    elif ok:
        exit_code = 0
        stdout = "SHIP_CHECK_OK"
    else:
        exit_code = 1
        stdout = None

    return {
        "passed": ok,
        "failures": failures,
        "dry_run": dry_run,
        "exit_code": exit_code,
        "error": None,
        "stdout": stdout,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NON-BINDING status-display ship-check for prd-taskmaster pipelines.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all gates but always exit 0. Report goes to stderr. Used by execute-task Step 9 as a per-task predicate.")
    parser.add_argument("--cwd", type=str, default=None,
                        help="Project root (defaults to current working directory).")
    args = parser.parse_args(argv)

    result = run_ship_check(cwd=args.cwd, dry_run=args.dry_run)

    # Script error (bad token or IO/JSON failure) — exit 2, message on stderr.
    if result["exit_code"] == 2:
        print(f"FAIL: {result['error']}", file=sys.stderr)
        return 2

    if args.dry_run:
        if result["passed"]:
            print("[DRY-RUN] all gates would pass", file=sys.stderr)
        else:
            print("[DRY-RUN] gate failures (would block):", file=sys.stderr)
            for f in result["failures"]:
                print(f"  - {f}", file=sys.stderr)
        return 0

    if result["passed"]:
        print(result["stdout"])
        return 0

    for f in result["failures"]:
        print(f"FAIL: {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
