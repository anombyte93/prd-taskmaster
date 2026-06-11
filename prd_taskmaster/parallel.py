#!/usr/bin/env python3
"""Parallel research + complexity extension for prd-taskmaster.

TaskMaster's own `expand --all --research` and `analyze-complexity --research`
run SEQUENTIALLY and write tasks.json after every call, so they cannot be
parallelized at the process level (single-writer file). This extension splits
the work into:

  1. `plan`   — emit one research-packet per task (JSON). The AGENT fans these
                out to parallel subagents (research happens concurrently).
  2. `apply`  — merge ALL results (subtasks + complexity + research notes) into
                tasks.json in ONE atomic write, and emit a TaskMaster-format
                complexity report. Single-writer safety preserved.

Also bridges the tagged tasks.json format (script.py only understands flat):
  3. `extract` — copy one tag's {tasks} to a flat temp file for script.py
                 validate-tasks / enrich-tasks.
  4. `inject`  — write the (validated/enriched) flat file back into the tag.

All commands print JSON. Tag defaults to .taskmaster/state.json currentTag.

Agent usage pattern (the parallelism lives in the agent, not this script):
    plan -> spawn N parallel subagents, each researching a slice of packets
         -> each returns results JSON -> concatenate -> apply
         -> extract -> script.py validate-tasks/enrich-tasks -> inject

Result schema expected by `apply` (list of objects):
    {"id": <task id>, "complexityScore": 1-10, "recommendedSubtasks": N,
     "reasoning": "...", "researchNotes": "...",
     "subtasks": [{"title": "...", "description": "...",
                   "details": "...", "dependencies": [<sibling subtask ids>]}]}
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASKS = Path(".taskmaster/tasks/tasks.json")
STATE = Path(".taskmaster/state.json")
REPORTS = Path(".taskmaster/reports")


def out(payload):
    print(json.dumps(payload, indent=2, default=str))


def fail(msg):
    out({"ok": False, "error": msg})
    sys.exit(1)


def _resolve_tag(tag_or_args=None):
    tag = getattr(tag_or_args, "tag", tag_or_args)
    if tag:
        return tag
    if STATE.is_file():
        return json.loads(STATE.read_text()).get("currentTag", "master")
    return "master"


def current_tag(args):
    return _resolve_tag(args)


def load_tagged(tag):
    if not TASKS.is_file():
        fail(f"{TASKS} not found")
    raw = json.loads(TASKS.read_text())
    if tag not in raw or not isinstance(raw.get(tag), dict):
        # flat (untagged) file: treat whole file as the tag when it matches
        if "tasks" in raw and isinstance(raw["tasks"], list):
            return raw, None  # flat mode
        fail(f"tag '{tag}' not found in {TASKS}")
    return raw, tag


def get_tasks(raw, tag):
    return raw["tasks"] if tag is None else raw[tag]["tasks"]


def write_atomic(path, payload):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def cmd_plan(args):
    tag = current_tag(args)
    raw, tag_key = load_tagged(tag)
    tasks = get_tasks(raw, tag_key)
    packets = []
    for t in tasks:
        if args.missing_only and len(t.get("subtasks") or []) >= 2:
            continue
        if str(t.get("status")) in ("done", "cancelled"):
            continue
        packets.append({
            "id": t["id"],
            "title": t["title"],
            "prompt": (
                "Research-then-decompose this task for the repo at the current "
                "working directory. TASK TITLE: " + t["title"] + "\n"
                "DESCRIPTION: " + str(t.get("description", "")) + "\n"
                "DETAILS: " + str(t.get("details", "")) + "\n"
                "TEST STRATEGY: " + str(t.get("testStrategy", "")) + "\n\n"
                "1) RESEARCH: verify the named files/patterns exist in the repo; "
                "check library APIs where named (use web/perplexity/context7 if "
                "available); note pitfalls. 2) COMPLEXITY: score 1-10 + recommended "
                "subtask count (3-7). 3) DECOMPOSE: TDD-ordered subtasks (each a "
                "verifiable checkpoint: failing test -> implement -> green; exact "
                "file paths; one concern per subtask). Return ONLY the JSON result "
                "object per the schema in parallel.py."
            ),
        })
    out({"ok": True, "tag": tag, "count": len(packets), "packets": packets})


def apply_results(results: list, tag: str | None = None, threshold: int = 7) -> dict:
    tag = _resolve_tag(tag)
    raw, tag_key = load_tagged(tag)
    tasks = get_tasks(raw, tag_key)
    by_id = {t["id"]: t for t in tasks}

    applied, complexity = [], []
    for r in results:
        t = by_id.get(r.get("id"))
        if t is None:
            continue
        subs = []
        for i, s in enumerate(r.get("subtasks") or [], start=1):
            subs.append({
                "id": i,
                "title": s.get("title", f"Step {i}"),
                "description": s.get("description", ""),
                "details": s.get("details", ""),
                "status": "pending",
                "dependencies": s.get("dependencies", []),
            })
        if subs:
            t["subtasks"] = subs
        notes = (r.get("researchNotes") or "").strip()
        if notes and notes not in str(t.get("details", "")):
            t["details"] = str(t.get("details", "")) + "\n\nRESEARCH NOTES (parallel pass): " + notes
        complexity.append({
            "taskId": t["id"],
            "taskTitle": t["title"],
            "complexityScore": r.get("complexityScore"),
            "recommendedSubtasks": r.get("recommendedSubtasks"),
            "expansionPrompt": "",
            "reasoning": r.get("reasoning", ""),
        })
        applied.append(t["id"])

    write_atomic(TASKS, raw)
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "tasksAnalyzed": len(complexity),
            "thresholdScore": threshold,
            "projectName": Path.cwd().name,
            "usedResearch": True,
            "generatedBy": "prd-taskmaster/parallel.py (agent-parallel research)",
            "tag": tag,
        },
        "complexityAnalysis": complexity,
    }
    suffix = "" if tag in ("master", None) else f"_{tag}"
    report_path = REPORTS / f"task-complexity-report{suffix}.json"
    write_atomic(report_path, report)
    needs_more = [c["taskId"] for c in complexity
                  if (c.get("complexityScore") or 0) >= threshold
                  and len((by_id[c["taskId"]].get("subtasks") or [])) < (c.get("recommendedSubtasks") or 0)]
    return {"ok": True, "tag": tag, "applied": applied, "report": str(report_path),
            "needs_more_subtasks": needs_more}


def cmd_apply(args):
    results = json.loads(Path(args.input).read_text())
    if isinstance(results, dict):
        results = results.get("results", [])
    out(apply_results(results, tag=getattr(args, "tag", None), threshold=args.threshold))


def cmd_extract(args):
    tag = current_tag(args)
    raw, tag_key = load_tagged(tag)
    flat = {"tasks": get_tasks(raw, tag_key)}
    Path(args.output).write_text(json.dumps(flat, indent=2, default=str))
    out({"ok": True, "tag": tag, "output": args.output, "count": len(flat["tasks"])})


def cmd_inject(args):
    tag = current_tag(args)
    raw, tag_key = load_tagged(tag)
    flat = json.loads(Path(args.input).read_text())
    tasks = flat.get("tasks", flat) if isinstance(flat, dict) else flat
    if tag_key is None:
        raw["tasks"] = tasks
    else:
        raw[tag_key]["tasks"] = tasks
        raw[tag_key].setdefault("metadata", {})["updated"] = datetime.now(timezone.utc).isoformat()
    write_atomic(TASKS, raw)
    out({"ok": True, "tag": tag, "injected": len(tasks)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("plan")
    sp.add_argument("--tag")
    sp.add_argument("--missing-only", action="store_true")
    sp.set_defaults(fn=cmd_plan)

    sa = sub.add_parser("apply")
    sa.add_argument("--tag")
    sa.add_argument("--input", required=True)
    sa.add_argument("--threshold", type=int, default=7)
    sa.set_defaults(fn=cmd_apply)

    se = sub.add_parser("extract")
    se.add_argument("--tag")
    se.add_argument("--output", required=True)
    se.set_defaults(fn=cmd_extract)

    si = sub.add_parser("inject")
    si.add_argument("--tag")
    si.add_argument("--input", required=True)
    si.set_defaults(fn=cmd_inject)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
