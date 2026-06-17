"""CLI: build_parser(), DISPATCH, main()."""

import argparse
import json
import sys

from prd_taskmaster.backend import get_backend
from prd_taskmaster.lib import CommandError, fail
from prd_taskmaster.preflight import cmd_preflight, cmd_detect_taskmaster
from prd_taskmaster.providers import cmd_configure_providers, cmd_detect_providers
from prd_taskmaster.capabilities import cmd_detect_capabilities
from prd_taskmaster.setup_wizard import cmd_setup
from prd_taskmaster.templates import cmd_load_template
from prd_taskmaster.validation import cmd_validate_prd, cmd_validate_tasks
from prd_taskmaster.tasks import (
    cmd_calc_tasks,
    cmd_backup_prd,
    cmd_enrich_tasks,
    cmd_expand_structural,
)
from prd_taskmaster.taskmaster import cmd_init_taskmaster
from prd_taskmaster.batch import cmd_engine_preflight
from prd_taskmaster.economy import cmd_economy_report
from prd_taskmaster.feedback import HARNESS_CHOICES, cmd_feedback_add, cmd_feedback_report
from prd_taskmaster.context_pack import build_context_pack
from prd_taskmaster import fleet, parallel, task_state
from prd_taskmaster.lib import _detect_taskmaster_method
from prd_taskmaster.reachability_cmd import cmd_reachability_sweep
from prd_taskmaster.tournament.cmd import (
    cmd_tournament_run,
    cmd_tournament_status,
    cmd_watcher_run,
    cmd_watcher_status,
)


def _backend_source() -> str:
    path = fleet.FLEET_CONFIG_PATH
    if not path.is_file():
        return "auto"
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return "auto"
    if isinstance(raw, dict) and raw.get("backend") in ("taskmaster", "native"):
        return "config"
    return "auto"


def _ai_ops(native_detect: dict) -> str:
    if native_detect.get("ai_ops") == "api":
        return "native-api"
    return "agent"


def _taskmaster_file_format_detect() -> dict:
    """Informational only: whether the optional task-master binary is on PATH.

    The task-master backend was removed (spec §9.4) — native is the sole
    generator — but `.taskmaster/` file-format detection survives, so we still
    surface whether the binary exists for diagnostic transparency.
    """
    detected = _detect_taskmaster_method()
    available = detected.get("method") in ("cli", "mcp")
    return {
        "available": available,
        "version": detected.get("version"),
        "min_ok": available,
    }


def run_backend_detect() -> dict:
    """Pure core for backend-detect; safe for CLI and MCP wrappers.

    Native is the sole generator now; the `taskmaster` entry is purely an
    informational file-format/binary presence probe, never a selectable backend.
    """
    selected_backend = get_backend(fleet.load_fleet_config())
    native_detect = selected_backend.detect()
    return {
        "ok": True,
        "selected": selected_backend.name,
        "source": _backend_source(),
        "ai_ops": _ai_ops(native_detect),
        "resolved": native_detect,
        "backends": {
            "taskmaster": _taskmaster_file_format_detect(),
            "native": native_detect,
        },
    }


def _selected_backend():
    return get_backend(fleet.load_fleet_config())


def run_init_project() -> dict:
    return _selected_backend().init_project()


def run_parse_prd(input_path: str, num_tasks: int, tag: str | None = None) -> dict:
    return _selected_backend().parse_prd(input_path, num_tasks, tag=tag or None)


def run_expand(
    task_ids: list[int] | None = None,
    research: bool = True,
    tag: str | None = None,
) -> dict:
    return _selected_backend().expand(task_ids=task_ids, research=research, tag=tag or None)


def run_rate(tag: str | None = None, research: bool = True) -> dict:
    return _selected_backend().rate(tag=tag or None, research=research)


def _emit_with_status(result: dict) -> None:
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") and not result.get("hard_fail") else 1)


def _cmd_backend_call(fn, *args, **kwargs) -> None:
    try:
        _emit_with_status(fn(*args, **kwargs))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def cmd_backend_detect(args) -> None:
    _cmd_backend_call(run_backend_detect)


def cmd_init_project(args) -> None:
    _cmd_backend_call(run_init_project)


def cmd_parse_prd(args) -> None:
    _cmd_backend_call(
        run_parse_prd,
        args.input,
        args.num_tasks,
        tag=getattr(args, "tag", None),
    )


def cmd_expand(args) -> None:
    _cmd_backend_call(
        run_expand,
        task_ids=getattr(args, "id", None),
        research=not getattr(args, "no_research", False),
        tag=getattr(args, "tag", None),
    )


def cmd_rate(args) -> None:
    _cmd_backend_call(
        run_rate,
        tag=getattr(args, "tag", None),
        research=not getattr(args, "no_research", False),
    )


def cmd_context_pack(args) -> None:
    print(json.dumps(build_context_pack(args.files, include_private=args.include_private), indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prd-taskmaster",
        description="prd-taskmaster: deterministic operations for the Atlas engine (skill + plugin).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # preflight
    sub.add_parser("preflight", help="Detect environment state")

    # engine-preflight (batched Phase 1: preflight + taskmaster + providers + capabilities)
    p = sub.add_parser("engine-preflight", help="One-call Phase 1: all probes + summary")
    p.add_argument(
        "--no-configure", action="store_true",
        help="Skip auto-configuring providers; read-only probe (default configures providers on an existing .taskmaster project)",
    )

    # detect-taskmaster
    sub.add_parser("detect-taskmaster", help="Find MCP or CLI taskmaster")

    # backend-detect
    sub.add_parser("backend-detect", help="Detect resolved backend and both backend capabilities")

    # init-project
    sub.add_parser("init-project", help="Initialise the resolved backend project state")

    # parse-prd
    p = sub.add_parser("parse-prd", help="Parse a PRD through the resolved backend")
    p.add_argument("--input", required=True, help="Path to PRD file")
    p.add_argument("--num-tasks", required=True, type=int)
    p.add_argument("--tag")

    # expand
    p = sub.add_parser("expand", help="Expand pending tasks through the resolved backend")
    p.add_argument("--id", action="append", type=int, help="Task id to expand; repeatable")
    p.add_argument("--no-research", action="store_true")
    p.add_argument("--tag")

    # rate
    p = sub.add_parser("rate", help="Rate task complexity through the resolved backend")
    p.add_argument("--tag")
    p.add_argument("--no-research", action="store_true")

    # configure-providers
    sub.add_parser("configure-providers", help="Configure native TaskMaster providers and local Perplexity API Free")

    # detect-providers
    sub.add_parser("detect-providers", help="Auto-detect AI providers")

    # detect-capabilities
    sub.add_parser("detect-capabilities", help="Scan for available skills and tools")

    # setup — guided provider/setup wizard (better than task-master models --setup)
    p = sub.add_parser("setup", help="Guided provider setup wizard (detect, recommend, validate)")
    p.add_argument("--yes", action="store_true", help="Accept the recommendation non-interactively (CI/dispatch)")
    p.add_argument("--validate", action="store_true", help="Dry-run gate: validate_setup + a live one-token probe per provider")

    # load-template
    p = sub.add_parser("load-template", help="Load PRD template")
    p.add_argument("--type", required=True, choices=["comprehensive", "minimal"])

    # validate-prd
    p = sub.add_parser("validate-prd", help="Run 13 quality checks on a PRD")
    p.add_argument("--input", required=True, help="Path to PRD file")

    # init-taskmaster
    sub.add_parser(
        "init-taskmaster",
        help="Run task-master init with .mcp.json protection (raw init overwrites it)",
    )

    # calc-tasks
    p = sub.add_parser("calc-tasks", help="Calculate recommended task count")
    p.add_argument("--requirements", required=True, type=int, help="Number of functional requirements")
    p.add_argument(
        "--scale",
        choices=["solo", "team", "enterprise"],
        default=None,
        help="Discovery scale classification; clamps to its band (solo 8-12, team 12-20, enterprise 20-30)",
    )

    # backup-prd
    p = sub.add_parser("backup-prd", help="Timestamped PRD backup")
    p.add_argument("--input", required=True, help="Path to PRD file")

    # validate-tasks
    p = sub.add_parser("validate-tasks", help="Validate manually-authored tasks.json")
    p.add_argument(
        "--input",
        default=None,
        help="Path to tasks.json (default: .taskmaster/tasks/tasks.json)",
    )
    p.add_argument(
        "--allow-empty-subtasks",
        action="store_true",
        help="Allow tasks without subtasks (manual mode normally requires subtasks)",
    )
    p.add_argument(
        "--require-phase-config",
        action="store_true",
        help="Require every task to include phaseConfig metadata after enrich-tasks",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="TaskMaster tag to validate (default: state.json currentTag, else flat/master)",
    )

    # enrich-tasks
    p = sub.add_parser("enrich-tasks", help="Add phaseConfig metadata to tasks.json")
    p.add_argument(
        "--input",
        default=None,
        help="Path to tasks.json (default: .taskmaster/tasks/tasks.json)",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="TaskMaster tag to enrich (default: state.json currentTag, else flat/master)",
    )

    # expand-structural — deterministic, zero-AI subtask decomposition fallback
    p = sub.add_parser(
        "expand-structural",
        help="Decompose under-expanded tasks into subtasks with no AI/network (offline fallback)",
    )
    p.add_argument(
        "--input",
        default=None,
        help="Path to tasks.json (default: .taskmaster/tasks/tasks.json)",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="TaskMaster tag to expand (default: state.json currentTag, else flat/master)",
    )
    p.add_argument(
        "--min-subtasks",
        dest="min_subtasks",
        type=int,
        default=2,
        help="Minimum subtasks per task (default: 2)",
    )

    # ─── parallel research bridge (agent-parallel research fan-out) ───────────
    # parallel-plan
    p = sub.add_parser("parallel-plan", help="Emit per-task research packets for parallel subagents")
    p.add_argument("--tag")
    p.add_argument("--missing-only", action="store_true")

    # parallel-apply
    p = sub.add_parser("parallel-apply", help="Merge parallel research results into tasks.json atomically")
    p.add_argument("--tag")
    p.add_argument("--input", required=True)
    p.add_argument("--threshold", type=int, default=7)

    # parallel-extract
    p = sub.add_parser("parallel-extract", help="Flatten a tagged tasks.json for validate/enrich")
    p.add_argument("--tag")
    p.add_argument("--output", required=True)

    # parallel-inject
    p = sub.add_parser("parallel-inject", help="Write a validated flat tasks file back into a tag")
    p.add_argument("--tag")
    p.add_argument("--input", required=True)

    # economy-report
    p = sub.add_parser("economy-report", help="Summarize .atlas-ai/telemetry.jsonl per (op_class, model)")
    p.add_argument("--input", default=None, help="Telemetry JSONL path (default: .atlas-ai/telemetry.jsonl)")

    # context-pack
    p = sub.add_parser("context-pack", help="Extract AST-based Python signature context")
    p.add_argument("--files", nargs="+", required=True, help="Python files to parse")
    p.add_argument("--include-private", action="store_true")

    # feedback-add
    p = sub.add_parser("feedback-add", help="Append one Atlas agent feedback row")
    p.add_argument("--rating", required=True, type=int)
    p.add_argument("--agent", required=True)
    p.add_argument("--harness", required=True, choices=sorted(HARNESS_CHOICES))
    p.add_argument("--task-ref", default="")
    p.add_argument("--well", default="")
    p.add_argument("--failed", default="")
    p.add_argument("--suggest", default="")

    # feedback-report
    p = sub.add_parser("feedback-report", help="Summarize .atlas-ai/feedback.jsonl")
    p.add_argument("--path", default=None)

    # fleet-waves
    p = sub.add_parser("fleet-waves", help="Compute Atlas Fleet dependency waves")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--tag", default="")

    # next-task
    p = sub.add_parser("next-task", help="Select the next TaskMaster-compatible task")
    p.add_argument("--tag", help="Tasks.json tag context to read (default: the active/master tag)")

    # claim-task
    p = sub.add_parser("claim-task", help="Atomically select and claim the next task")
    p.add_argument("--tag", help="Tasks.json tag context to read (default: the active/master tag)")

    # set-status
    p = sub.add_parser("set-status", help="Set a task or subtask status")
    p.add_argument("--id", required=True, help="Task or subtask id (e.g. 7 or 1.2)")
    p.add_argument(
        "--status", required=True,
        help="Task status; one of: pending, in-progress, done, review, deferred, cancelled, blocked",
    )
    p.add_argument("--tag", help="Tasks.json tag context to write (default: the active/master tag)")
    p.add_argument(
        "--evidence-ref",
        default=None,
        help="Path or ref to the CDD evidence card for this task",
    )
    p.add_argument(
        "--reachability",
        default=None,
        help=(
            "Reachability verdict: bare string (WIRED|EXEMPT|ORPHAN) or a JSON dict. "
            "When omitted and marking done, the verdict is auto-read from the task's "
            "CDD card .atlas-ai/cdd/task-<id>.json if present."
        ),
    )

    # reachability-sweep
    p = sub.add_parser(
        "reachability-sweep",
        help="Run the reachability sweep for a task and write the verdict into its CDD card",
    )
    p.add_argument("--task", required=True, help="Task id (e.g. 1 or 1.2)")
    p.add_argument(
        "--start-commit",
        required=True,
        help="Git SHA recorded when work on this task began (git rev-parse HEAD at task start)",
    )
    p.add_argument(
        "--cwd",
        default=None,
        help="Explicit repo root (defaults to the current working directory)",
    )

    # tournament-run — run a full tournament job (spawn→collect→adjudicate→settle→reputation)
    p = sub.add_parser(
        "tournament-run",
        help="Run a full tournament job: spawn racers, collect commit-reveals, adjudicate, settle, record reputation",
    )
    p.add_argument("--card", required=True, help="Path to CDD card JSON")
    p.add_argument("--task", required=True, help="Task id (e.g. 7 or 1.2)")
    p.add_argument("--base-ref", required=True, help="Fork-point git SHA all worktrees branch from")
    p.add_argument("--models", required=True, help="Comma-separated model strings (e.g. claude:sonnet,claude:haiku)")
    p.add_argument("--job-id", required=True, help="Unique tournament job identifier")
    p.add_argument("--bounty", required=True, type=int, help="Bounty amount in coin units")
    p.add_argument("--job-poster", required=True, help="Identity of the bounty poster")
    p.add_argument("--window", type=float, default=120.0, help="Commit-reveal window in seconds (default 120)")
    p.add_argument("--enforce-slash", action="store_true", help="Pass --enforce-slash to the settle CLI")
    p.add_argument("--task-class", default="coding", help="Reputation bucket (default: coding)")

    # tournament-status — read reputation snapshot + active operator count
    p = sub.add_parser(
        "tournament-status",
        help="Show reputation snapshot and active operator slot count",
    )
    p.add_argument("--reputation-path", default=None, help="Path to reputation.jsonl (default: .atlas-ai/reputation.jsonl)")
    p.add_argument("--operators-path", default=None, help="Path to operators.json (default: .atlas-ai/tournament/operators.json)")

    # watcher-run — independent out-of-band re-adjudication of a settled job
    p = sub.add_parser(
        "watcher-run",
        help="Re-adjudicate a settled tournament job out-of-band; append concordance; report the real-slash permit",
    )
    p.add_argument("--job", required=True, help="Path to the settled job dir (contains submissions.json)")
    p.add_argument("--card", required=True, help="Path to the CDD card JSON")
    p.add_argument("--task", required=True, help="Task id (e.g. 7 or 1.2)")
    p.add_argument("--base-ref", required=True, help="Fork-point git SHA the diff range is measured from")
    p.add_argument("--repo-root", default=".", help="Repo containing the racer commits (default: .)")
    p.add_argument("--held-root", default=None, help="Held root for the oracle gate (default: .atlas-ai/cdd)")
    p.add_argument("--ledger-path", default=None, help="Watcher ledger path (default: .atlas-ai/tournament/watcher.jsonl)")

    # watcher-status — report watcher concordance + real-slash readiness
    p = sub.add_parser(
        "watcher-status",
        help="Show the watcher's historical concordance and whether real slashing is permitted yet",
    )
    p.add_argument("--ledger-path", default=None, help="Watcher ledger path (default: .atlas-ai/tournament/watcher.jsonl)")

    # status — render progress panels
    p = sub.add_parser("status", help="Render Atlas progress panels for the current phase")
    p.add_argument("--phase", default=None, help="Render a specific phase instead of the current one")
    p.add_argument("--format", default="boxed", choices=["boxed", "ascii", "json"])
    p.add_argument("--all", action="store_true", help="Render every panel, not just the current phase")

    return parser


def cmd_status(args) -> None:
    """Render progress panels. A view command: prints the rendered panel to
    stdout for boxed/ascii, or structured JSON for --format json."""
    from prd_taskmaster.status import run_render_status
    try:
        result = run_render_status(phase=args.phase, fmt=args.format, show_all=args.all)
    except CommandError as e:
        fail(e.message, **e.extra)
        return
    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result["rendered"])
    sys.exit(0)


DISPATCH = {
    "preflight": cmd_preflight,
    "engine-preflight": cmd_engine_preflight,
    "detect-taskmaster": cmd_detect_taskmaster,
    "backend-detect": cmd_backend_detect,
    "init-project": cmd_init_project,
    "parse-prd": cmd_parse_prd,
    "expand": cmd_expand,
    "rate": cmd_rate,
    "configure-providers": cmd_configure_providers,
    "detect-providers": cmd_detect_providers,
    "detect-capabilities": cmd_detect_capabilities,
    "setup": cmd_setup,
    "load-template": cmd_load_template,
    "validate-prd": cmd_validate_prd,
    "calc-tasks": cmd_calc_tasks,
    "backup-prd": cmd_backup_prd,
    "validate-tasks": cmd_validate_tasks,
    "enrich-tasks": cmd_enrich_tasks,
    "expand-structural": cmd_expand_structural,
    "init-taskmaster": cmd_init_taskmaster,
    "parallel-plan": parallel.cmd_plan,
    "parallel-apply": parallel.cmd_apply,
    "parallel-extract": parallel.cmd_extract,
    "parallel-inject": parallel.cmd_inject,
    "fleet-waves": fleet.cmd_fleet_waves,
    "next-task": task_state.cmd_next_task,
    "claim-task": task_state.cmd_claim_task,
    "set-status": task_state.cmd_set_status,
    "reachability-sweep": cmd_reachability_sweep,
    "tournament-run": cmd_tournament_run,
    "tournament-status": cmd_tournament_status,
    "watcher-run": cmd_watcher_run,
    "watcher-status": cmd_watcher_status,
    "economy-report": cmd_economy_report,
    "context-pack": cmd_context_pack,
    "feedback-add": cmd_feedback_add,
    "feedback-report": cmd_feedback_report,
    "status": cmd_status,
}


def main():
    parser = build_parser()
    args = parser.parse_args()
    handler = DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        fail(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
