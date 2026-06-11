#!/usr/bin/env python3
"""
Mode D blocker hook. Blocks mcp__atlas-cdd and mcp__atlas-loop tool calls.
Mode D (full CDD + atlas-phoenix) is preview-alpha and requires waitlist opt-in.
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

    # Check if tool is from blocked Mode D namespaces
    if tool_name.startswith("mcp__atlas-cdd__") or tool_name.startswith("mcp__atlas-loop__"):
        reason = (
            "Mode D (full CDD + atlas-phoenix integration) is preview-alpha and requires waitlist opt-in. "
            "Please join the waitlist at https://atlas-ai.au/waitlist/mode-d to access this feature."
        )
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
