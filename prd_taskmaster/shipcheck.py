#!/usr/bin/env python3
"""Deterministic ship-check for prd-taskmaster pipelines.

Emits SHIP_CHECK_OK to stdout ONLY when all gates pass. Called by execute-task
at termination AND by Step 9 (--dry-run) as a per-task predicate.

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

  Gate 5 (HARD) — No non-zero "Exit status N" line in any .atlas-ai/evidence/
    file. This is the convergent must-do from the 2026-06-04 forensic audit
    (T12 marked DONE while pnpm test exited 1 with 11 failing tests).
    Override only via SHIP_CHECK_OVERRIDE_ADMIN token; overrides are logged
    to .atlas-ai/state/execute-log.jsonl as an audit record.

Interface (standalone shim, created in a later step):
  python3 .atlas-ai/ship-check.py                              # standard gate
  python3 .atlas-ai/ship-check.py --dry-run                    # always exit 0; report on stderr
  python3 .atlas-ai/ship-check.py --override SHIP_CHECK_OVERRIDE_ADMIN  # bypass Gate 5
  python3 .atlas-ai/ship-check.py --cwd /path/to/project       # explicit project root

Exit codes:
  0 — SHIP_CHECK_OK (stdout: exactly "SHIP_CHECK_OK\n", with " [OVERRIDE]" suffix if applicable)
  1 — gate failures (stderr only; nothing on stdout — log watchers must not see partial matches)
  2 — script error (IO, JSON parse, bad token)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

OVERRIDE_TOKEN = "SHIP_CHECK_OVERRIDE_ADMIN"
EXIT_STATUS_RE = re.compile(r"\bExit status\s+(\d+)\b", re.IGNORECASE)


def _send_telemetry(event: str) -> None:
    try:
        from prd_taskmaster import telemetry

        telemetry.send_event(event)
    except Exception:
        pass


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
    # and flat {"tasks": [...]} (Manual Mechanics Mode / fleet samples).
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


def log_override(atlas: Path, message: str) -> None:
    log = atlas / "state" / "execute-log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "iteration": "OVERRIDE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": "SHIP_CHECK",
        "event": "override_invoked",
        "message": message,
    }
    with log.open("a") as fp:
        fp.write(json.dumps(entry) + "\n")


def run_all_gates(repo_root: Path, override_active: bool) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    atlas = repo_root / ".atlas-ai"

    _, f1 = gate_pipeline(atlas)
    failures.extend(f1)

    _, f2, tasks = gate_tasks(repo_root)
    failures.extend(f2)

    if tasks:
        _, f3 = gate_cdd(atlas, tasks)
        failures.extend(f3)

    _, f4 = gate_plan(repo_root)
    failures.extend(f4)

    ok5, f5 = gate_exit_codes(atlas)
    if not ok5:
        if override_active:
            log_override(atlas, f"Gate 5 bypassed: {'; '.join(f5[:3])}{' ...' if len(f5) > 3 else ''}")
            # Override accepts the failures; no append to global failures list
        else:
            failures.extend(f5)

    return len(failures) == 0, failures


def run_ship_check(cwd: Optional[str] = None, dry_run: bool = False,
                   override: Optional[str] = None) -> dict:
    """Importable ship-check entry point. NEVER calls sys.exit.

    Args:
      cwd: project root (defaults to current working directory).
      dry_run: when True, the returned exit_code is forced to 0 regardless of
               gate outcome (gates still run and the report is preserved).
      override: if equal to OVERRIDE_TOKEN, Gate 5 (exit codes) is bypassed.

    Returns a dict:
      passed: bool          — True when all (non-overridden) gates pass.
      failures: list[str]   — per-gate failure detail (empty when passed).
      override_active: bool — whether a valid override token was supplied.
      override_invalid: bool — an override value was supplied but did not match.
      dry_run: bool
      exit_code: int        — 0 / 1 / 2 mirroring the CLI contract.
      error: str | None     — populated on a script error (exit_code 2).
      stdout: str | None    — the exact stdout line the CLI would print, if any.
    """
    if override is not None and override != OVERRIDE_TOKEN:
        return {
            "passed": False,
            "failures": [],
            "override_active": False,
            "override_invalid": True,
            "dry_run": dry_run,
            "exit_code": 2,
            "error": "--override value does not match expected token",
            "stdout": None,
        }

    override_active = override == OVERRIDE_TOKEN
    repo_root = Path(cwd).resolve() if cwd else Path.cwd()

    try:
        ok, failures = run_all_gates(repo_root, override_active=override_active)
    except Exception as exc:  # noqa: BLE001 — top-level guard
        return {
            "passed": False,
            "failures": [],
            "override_active": override_active,
            "override_invalid": False,
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
        suffix = " [OVERRIDE]" if override_active else ""
        stdout = f"SHIP_CHECK_OK{suffix}"
        _send_telemetry("ship_check_ok")
    else:
        exit_code = 1
        stdout = None

    return {
        "passed": ok,
        "failures": failures,
        "override_active": override_active,
        "override_invalid": False,
        "dry_run": dry_run,
        "exit_code": exit_code,
        "error": None,
        "stdout": stdout,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic ship-check for prd-taskmaster pipelines.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all gates but always exit 0. Report goes to stderr. Used by execute-task Step 9 as a per-task predicate.")
    parser.add_argument("--override", type=str, default=None,
                        help=f"Bypass Gate 5 (exit codes) if value equals {OVERRIDE_TOKEN}. Logged to execute-log.jsonl.")
    parser.add_argument("--cwd", type=str, default=None,
                        help="Project root (defaults to current working directory).")
    args = parser.parse_args(argv)

    result = run_ship_check(cwd=args.cwd, dry_run=args.dry_run, override=args.override)

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
