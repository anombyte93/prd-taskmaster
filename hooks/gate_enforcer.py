#!/usr/bin/env python3
"""
Gate enforcer hook. Blocks mcp__...__advance_phase calls without gate evidence.
Reads PreToolUse JSON from stdin, returns permissionDecision on stdout.
Never crashes — all JSON parsing wrapped in try/except.
No explicit process termination — main() returns and the process ends naturally.
"""
import json
import sys


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # never crash the hook — bad stdin is a no-op (implicit allow)
        print(json.dumps({}))
        return

    tool_name = payload.get("tool_name", "")
    if not tool_name.endswith("__advance_phase"):
        print(json.dumps({}))
        return

    tool_input = payload.get("tool_input", {})
    target = tool_input.get("target")
    evidence = tool_input.get("evidence", {})

    # Mirror the same gate logic as pipeline.check_gate (simplified for hook)
    violations = []
    if target == "SETUP":
        vs = evidence.get("validate_setup", {})
        if not vs.get("ready") or vs.get("critical_failures", 1) > 0:
            violations.append("validate_setup must report ready=true and critical_failures==0; evidence must contain validate_setup block")
    elif target == "DISCOVER":
        if not (
            evidence.get("user_approved")
            or (
                evidence.get("auto_classification") == "CLEAR"
                and evidence.get("assumptions_documented")
            )
        ):
            violations.append(
                "DISCOVER gate requires user_approved=true OR (auto_classification==CLEAR AND assumptions_documented=true); evidence missing"
            )
    elif target == "GENERATE":
        if evidence.get("validation_grade") not in ("EXCELLENT", "GOOD"):
            violations.append("validation_grade must be EXCELLENT or GOOD; evidence insufficient")
        if evidence.get("task_count", 0) == 0:
            violations.append("task_count must be > 0; evidence shows no tasks parsed")
        if evidence.get("subtask_coverage", 0) < 1.0:
            violations.append("subtask_coverage must be >= 1.0; evidence shows subtasks incomplete")
    elif target == "HANDOFF":
        if not evidence.get("user_mode_choice"):
            violations.append("user_mode_choice missing from evidence; user must select execution mode before HANDOFF")
        if not evidence.get("plan_file_exists"):
            violations.append("plan_file_exists missing from evidence; plan file must be written before HANDOFF")
    elif target == "EXECUTE":
        # EXECUTE is terminal — individual tasks track own status; no gate check needed
        pass

    if violations:
        reason = f"Gate for {target} not passed: {'; '.join(violations)}"
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    else:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
