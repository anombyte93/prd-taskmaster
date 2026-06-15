"""Golden-parity harness for the TaskMaster -> native+cli_agent migration.

Captures task-graph outputs from each backend on the sample PRDs in
fixtures/, normalizes them to a structural shape (dropping volatile prose),
and diffs them. Only diffs NOT in the pre-declared `intended` whitelist fail
parity.

IMPORTANT: parse_prd does NOT return the task graph in its result dict — both
NativeBackend.parse_prd (backend.py:409-419) and TaskMasterBackend.parse_prd
(backend.py:735-738) return {ok, task_count, tag, backend, ...} with no "tasks"
key; the tasks are written to .taskmaster/tasks/tasks.json. So capture reads the
graph from DISK via parallel.load_tagged + parallel.get_tasks AFTER parse_prd.
Each backend leg runs in its OWN temp cwd + tag so the two legs do not overwrite
each other's tasks.json.

This is the binary acceptance gate referenced by the migration deletion task.
Skill: AI-golden-parity-refactor. Spec: §9.3.

Usage (capture + gate, run from repo root):
    python3 -m tests.parity.golden_parity capture --backend taskmaster --out golden/tm
    python3 -m tests.parity.golden_parity capture --backend native    --out golden/native
    python3 -m tests.parity.golden_parity gate    --gold golden/tm --new golden/native
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PRDS = ["prd_cli_tool.md", "prd_web_api.md", "prd_data_pipeline.md"]

# Pre-declared intended-diff whitelist (skill: declare BEFORE running).
# Each entry is a "tasks[<i>].<field>" path that is allowed to differ between
# the TaskMaster golden and the native+cli_agent output. Start EMPTY — every
# real diff must be consciously promoted here with a one-line justification.
INTENDED_DIFFS: set[str] = set()


def extract_graph_from_disk(parse_result: dict | None = None, tag: str | None = None) -> dict:
    """Read the task graph that parse_prd wrote to .taskmaster/tasks/tasks.json.

    parse_result is accepted (and may be inspected for {ok}) but its body is NOT
    the source of tasks — parse_prd returns only {ok, task_count, tag, ...} with
    no "tasks"/"raw" key. The authoritative graph is the on-disk tasks.json for
    the current (or given) tag, read via parallel.load_tagged + parallel.get_tasks.
    Imported lazily so the pure differ tests do not drag in backend deps.
    """
    from prd_taskmaster import parallel

    resolved = tag if tag is not None else (
        parse_result.get("tag") if isinstance(parse_result, dict) and parse_result.get("tag") else None
    )
    resolved = parallel.current_tag(resolved)
    raw, tag_key = parallel.load_tagged(resolved)
    tasks = parallel.get_tasks(raw, tag_key)
    return {"tasks": tasks}


def normalize_graph(graph: dict) -> dict:
    """Reduce a parse_prd/expand task graph to its parity-relevant structure.

    Keeps: task_count, and per-task {id, title, dependencies, subtask_count,
    priority}. Drops: details/testStrategy/description (volatile prose),
    status (always 'pending' at gen time), and subtask internals (structural
    count is the parity signal, not generated subtask prose).
    """
    tasks = graph.get("tasks", []) or []
    norm_tasks = []
    for t in tasks:
        norm_tasks.append(
            {
                "id": t.get("id"),
                "title": t.get("title", ""),
                "dependencies": sorted(t.get("dependencies", []) or []),
                "subtask_count": len(t.get("subtasks", []) or []),
                "priority": t.get("priority", ""),
            }
        )
    return {"task_count": len(norm_tasks), "tasks": norm_tasks}


def diff_graphs(gold: dict, new: dict, intended: set[str] | None = None) -> dict:
    """Structural diff. Returns {parity: bool, diffs: [str], intended_applied: [str]}.

    A diff path in `intended` is recorded in intended_applied and does NOT
    count against parity (skill: only explicitly-intended diffs allowed).

    Parity requires BOTH graphs to have task_count >= 1. Empty-vs-empty is
    not a valid green gate — it means capture produced no tasks at all.
    """
    intended = intended or set()
    diffs: list[str] = []
    intended_applied: list[str] = []

    gold_count = gold.get("task_count", 0) or 0
    new_count = new.get("task_count", 0) or 0
    if gold_count < 1:
        diffs.append("empty graph — capture produced no tasks (gold)")
    if new_count < 1:
        diffs.append("empty graph — capture produced no tasks (new)")
    if diffs:
        return {"parity": False, "diffs": diffs, "intended_applied": intended_applied}

    if gold.get("task_count") != new.get("task_count"):
        diffs.append(
            f"task_count: gold={gold.get('task_count')} new={new.get('task_count')}"
        )

    g_tasks = gold.get("tasks", [])
    n_tasks = new.get("tasks", [])
    for idx in range(max(len(g_tasks), len(n_tasks))):
        g = g_tasks[idx] if idx < len(g_tasks) else None
        n = n_tasks[idx] if idx < len(n_tasks) else None
        if g is None or n is None:
            diffs.append(f"tasks[{idx}]: present in only one graph")
            continue
        for field in ("title", "dependencies", "subtask_count", "priority"):
            if g.get(field) != n.get(field):
                path = f"tasks[{idx}].{field}"
                if path in intended:
                    intended_applied.append(path)
                else:
                    diffs.append(f"{path}: gold={g.get(field)!r} new={n.get(field)!r}")

    return {
        "parity": not diffs,
        "diffs": diffs,
        "intended_applied": intended_applied,
    }


def _capture(backend_name: str, out_dir: Path) -> int:
    """Run parse_prd on each sample PRD via the named backend; write normalized
    graphs to out_dir/<prd>.json.

    Each PRD runs in its OWN isolated temp cwd + per-PRD tag so the two backend
    legs (which both write the SAME .taskmaster/tasks/tasks.json path) never
    overwrite each other. The graph is read from DISK after parse_prd via
    extract_graph_from_disk — parse_prd's result dict has no "tasks" key.

    Imported lazily so the pure differ tests do not drag in backend/model deps."""
    from prd_taskmaster.backend import NativeBackend, TaskMasterBackend, _FACTORY_TOKEN

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if backend_name == "taskmaster":
        be = TaskMasterBackend(_FACTORY_TOKEN)
    elif backend_name == "native":
        be = NativeBackend()
    else:
        print(f"unknown backend: {backend_name}", file=sys.stderr)
        return 2

    rc = 0
    cwd0 = Path.cwd()
    for prd in SAMPLE_PRDS:
        prd_path = (FIXTURES / prd).resolve()
        stem = Path(prd).stem
        tag = f"parity_{backend_name}_{stem}"
        # Isolated workdir per leg+PRD: parse_prd writes .taskmaster/tasks/tasks.json
        # relative to cwd, so distinct cwds keep the two backend legs from clobbering.
        with tempfile.TemporaryDirectory(prefix=f"parity_{backend_name}_") as work:
            os.chdir(work)
            try:
                be.init_project()
                # point state at this PRD's tag so load_tagged resolves it
                state = Path(".taskmaster") / "state.json"
                state.parent.mkdir(parents=True, exist_ok=True)
                state.write_text(json.dumps({"currentTag": tag}))
                result = be.parse_prd(str(prd_path), num_tasks=8, tag=tag)
                if not result.get("ok"):
                    print(f"CAPTURE FAIL {backend_name}/{prd}: {result}", file=sys.stderr)
                    rc = 1
                    continue
                # Read the graph from DISK (result dict has no "tasks" key).
                graph = extract_graph_from_disk(result, tag=tag)
            finally:
                os.chdir(cwd0)
        norm = normalize_graph(graph)
        (out_dir / f"{stem}.json").write_text(
            json.dumps(norm, indent=2, sort_keys=True)
        )
        print(f"captured {backend_name}/{prd}: {norm['task_count']} tasks")
    return rc


def _gate(gold_dir: Path, new_dir: Path) -> int:
    """Diff every captured PRD graph; print a report; return 0 iff full parity."""
    overall = True
    report = []
    for prd in SAMPLE_PRDS:
        stem = Path(prd).stem
        gold = json.loads((gold_dir / f"{stem}.json").read_text())
        new = json.loads((new_dir / f"{stem}.json").read_text())
        res = diff_graphs(gold, new, intended=INTENDED_DIFFS)
        report.append((stem, res))
        if not res["parity"]:
            overall = False

    print("=== GOLDEN PARITY REPORT ===")
    for stem, res in report:
        status = "PARITY_OK" if res["parity"] else "PARITY_FAIL"
        print(f"[{status}] {stem}")
        for d in res["diffs"]:
            print(f"    DIFF: {d}")
        for i in res["intended_applied"]:
            print(f"    intended (allowed): {i}")
    print("=== %s ===" % ("ALL_PARITY_OK" if overall else "PARITY_FAILED"))
    return 0 if overall else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--backend", required=True, choices=["taskmaster", "native"])
    cap.add_argument("--out", required=True, type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("--gold", required=True, type=Path)
    gate.add_argument("--new", required=True, type=Path)
    args = p.parse_args(argv)
    if args.cmd == "capture":
        return _capture(args.backend, args.out)
    return _gate(args.gold, args.new)


if __name__ == "__main__":
    raise SystemExit(main())
