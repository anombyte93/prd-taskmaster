"""Oracle bridge: map a CDD card to a Graded Card verdict via the atlas oracle CLI.

Fail-closed: any ambiguity (missing verdict, unparseable output, CLI crash) yields
("FAIL", {...}) — never "PASS" and never an uncaught exception from the grading path.
OracleCardError is the one intended raise, for a missing/unreadable/invalid card.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class OracleCardError(Exception):
    """Raised when a CDD card cannot be graded (e.g. missing 'grading' block)."""


def _oracle_cmd() -> list[str]:
    """Configurable CLI invocation. Default: the 'atlas' binary on PATH.

    Override with ATLAS_ORACLE_CMD (shell-split), e.g.:
        ATLAS_ORACLE_CMD="node /path/to/atlas-protocol/apps/cli/dist/index.js"
    """
    raw = os.environ.get("ATLAS_ORACLE_CMD")
    if raw:
        import shlex
        return shlex.split(raw)
    return ["atlas"]


def grade_card(
    *,
    card_path: str | Path,
    repo_path: str | Path,
    commit_sha: str,
    held_root: str | Path,
    evidence_dir: str | Path,
    ledger_dir: str | Path,
    oracle_cmd: list[str] | None = None,
) -> tuple[str, dict]:
    """Grade a submission via the atlas oracle CLI.

    Returns (verdict, detail) where verdict is "PASS" or "FAIL".

    FAIL-CLOSED: any error (missing verdict, unparseable output, CLI crash)
    yields ("FAIL", {...}) — never raises after the card has been validated.

    Raises:
        OracleCardError: if the card file is missing, unreadable, or has no 'grading' block.
    """
    card_path = Path(card_path)

    try:
        card = json.loads(card_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise OracleCardError(f"cannot read card {card_path}: {exc}") from exc

    if "grading" not in card:
        raise OracleCardError(
            f"card {card_path} has no 'grading' block; cannot grade"
        )

    cmd = (oracle_cmd or _oracle_cmd()) + [
        "oracle", "grade",
        "--repo", str(repo_path),
        "--commit", commit_sha,
        "--card", str(card_path),
        "--held", str(held_root),
        "--evidence", str(evidence_dir),
        "--ledger", str(ledger_dir),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return ("FAIL", {"error": f"oracle CLI invocation failed: {exc}"})

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return (
            "FAIL",
            {
                "error": "oracle CLI produced no parseable JSON verdict",
                "returncode": proc.returncode,
                "stdout": proc.stdout[:500],
                "stderr": proc.stderr[:500],
            },
        )

    verdict = parsed.get("verdict")
    if verdict not in ("PASS", "FAIL"):
        return ("FAIL", {"error": "oracle CLI verdict missing/invalid", "parsed": parsed})

    return (verdict, parsed)


def grade_task(
    *,
    repo_root: str | Path,
    task_id,
    commit_sha: str,
    held_root: str | Path,
    evidence_dir: str | Path,
    ledger_dir: str | Path,
    oracle_cmd: list[str] | None = None,
) -> tuple[str, dict]:
    """Convenience: locate the CDD card for a task and grade it.

    Looks for .atlas-ai/cdd/task-<id>.json under repo_root.

    Raises:
        OracleCardError: if the card file does not exist or fails validation.
    """
    card_path = Path(repo_root) / ".atlas-ai" / "cdd" / f"task-{task_id}.json"
    if not card_path.exists():
        raise OracleCardError(f"no CDD card at {card_path}")
    return grade_card(
        card_path=card_path,
        repo_path=repo_root,
        commit_sha=commit_sha,
        held_root=held_root,
        evidence_dir=evidence_dir,
        ledger_dir=ledger_dir,
        oracle_cmd=oracle_cmd,
    )
