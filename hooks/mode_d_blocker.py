#!/usr/bin/env python3
"""
Atlas Fleet blocker hook. Blocks mcp__atlas-cdd and mcp__atlas-loop tool calls.
Atlas Fleet is part of Atlas Pro and requires a licensed launcher.
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

    # Check if tool is from blocked Atlas Fleet namespaces
    if tool_name.startswith("mcp__atlas-cdd__") or tool_name.startswith("mcp__atlas-loop__"):
        reason = (
            "Atlas Fleet is part of Atlas Pro ($29/mo). "
            "Unlock: https://atlas-ai.au/pro"
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
