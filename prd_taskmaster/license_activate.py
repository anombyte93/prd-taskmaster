"""CLI surface for Atlas license activation."""

import argparse
import json
import sys
from typing import Any

from prd_taskmaster import license
from prd_taskmaster.lib import emit


def _activation_result(key_str: str) -> dict[str, Any]:
    parsed = license.parse_key(key_str)
    payload = parsed.get("payload") if parsed.get("ok") else None
    status = license.get_status(parsed if parsed.get("ok") else key_str)

    result: dict[str, Any] = {
        "ok": status["status"] in {"active", "grace"},
        "status": status["status"],
        "days_remaining": status["days_remaining"],
        "detail": status["detail"],
        "plan": payload.get("plan") if isinstance(payload, dict) else None,
        "license_id": payload.get("lid") if isinstance(payload, dict) else None,
    }

    if result["ok"]:
        saved = license.save_license(key_str)
        result["path"] = saved.get("path")
        if not saved.get("ok"):
            result.update({
                "ok": False,
                "status": saved.get("status", "invalid"),
                "days_remaining": saved.get("days_remaining"),
                "detail": saved.get("detail", "license could not be saved"),
            })

    return result


def _render_status_block(result: dict[str, Any]) -> str:
    activated = result.get("ok") is True
    happened = (
        "Atlas Pro license activated."
        if activated
        else "Atlas Pro license was not activated."
    )
    plan = result.get("plan") or "unknown"
    status = result.get("status") or "invalid"
    days = result.get("days_remaining")
    days_part = f" · {days} grace days remaining" if status == "grace" else ""
    detail = result.get("detail") or status
    next_step = (
        "run `prd-taskmaster detect-capabilities` to confirm premium tier."
        if activated
        else "check the key and run `prd-taskmaster license-activate <key>` again."
    )

    return "\n".join([
        "┌─ atlas ── license-activate ─┐",
        f"│ What happened: {happened}",
        f"│ Evidence: plan {plan} · status {status}{days_part}",
        f"│ Detail: {detail}",
        "└──────────────────────────────┘",
        f"Next: {next_step}",
    ])


def cmd_license_activate(args: argparse.Namespace) -> None:
    result = _activation_result(args.license_key)
    if getattr(args, "json", False):
        if result.get("ok"):
            emit(result)
        print(json.dumps(result, indent=2, default=str))
        sys.exit(1)

    print(_render_status_block(result))
    if not result.get("ok"):
        sys.exit(1)
