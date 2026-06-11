#!/usr/bin/env python3
"""
Evidence gate Stop hook. Blocks session end when the EXECUTE phase has
in-progress tasks with incomplete CDD evidence (fewer evidence_files than
subtasks).

Reads Stop JSON from stdin, returns a decision on stdout.
Never crashes — all parsing wrapped in try/except.
Short-circuits when stop_hook_active is True to avoid infinite block loops
when Claude Code re-invokes Stop hooks after a block decision.
No explicit process termination — main() returns and the process ends naturally.
"""
import json
import sys
from pathlib import Path


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # never crash the hook — bad stdin is a no-op (implicit allow)
        print(json.dumps({}))
        return

    try:
        # Short-circuit: if Claude Code is re-invoking Stop hooks after a block,
        # always allow to prevent infinite loops.
        if payload.get("stop_hook_active") is True:
            print(json.dumps({}))
            return

        pipeline_path = Path(".atlas-ai/state/pipeline.json")
        if not pipeline_path.is_file():
            print(json.dumps({}))
            return

        try:
            pipeline = json.loads(pipeline_path.read_text())
        except Exception:
            print(json.dumps({}))
            return

        if pipeline.get("current_phase") != "EXECUTE":
            print(json.dumps({}))
            return

        tasks_path = Path(".atlas-ai/taskmaster/tasks/tasks.json")
        if not tasks_path.is_file():
            print(json.dumps({}))
            return

        try:
            tasks_data = json.loads(tasks_path.read_text())
        except Exception:
            print(json.dumps({}))
            return

        tasks = tasks_data.get("master", {}).get("tasks", []) or []
        offenders = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            if t.get("status") != "in-progress":
                continue
            subtasks = t.get("subtasks") or []
            evidence_files = t.get("evidence_files") or []
            if len(subtasks) > 0 and len(evidence_files) < len(subtasks):
                offenders.append(
                    f"task {t.get('id')}: {len(evidence_files)}/{len(subtasks)} evidence"
                )

        if offenders:
            reason = (
                f"Incomplete CDD evidence — {len(offenders)} tasks have subtasks "
                f"without matching evidence: {'; '.join(offenders)}. "
                f"Run execute-task loop to completion or mark blocked."
            )
            print(json.dumps({"decision": "block", "reason": reason}))
        else:
            print(json.dumps({}))
    except Exception:
        # any unexpected failure — allow, never crash the hook
        print(json.dumps({}))
        return


if __name__ == "__main__":
    main()
