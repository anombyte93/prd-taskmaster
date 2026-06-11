"""CLI: build_parser(), DISPATCH, main()."""

import argparse

from prd_taskmaster.lib import fail
from prd_taskmaster.preflight import cmd_preflight, cmd_detect_taskmaster
from prd_taskmaster.providers import cmd_configure_providers, cmd_detect_providers
from prd_taskmaster.capabilities import cmd_detect_capabilities
from prd_taskmaster.license_activate import cmd_license_activate
from prd_taskmaster.templates import cmd_load_template
from prd_taskmaster.validation import cmd_validate_prd, cmd_validate_tasks
from prd_taskmaster.tasks import cmd_calc_tasks, cmd_backup_prd, cmd_enrich_tasks
from prd_taskmaster.taskmaster import cmd_init_taskmaster
from prd_taskmaster.batch import cmd_engine_preflight
from prd_taskmaster import fleet, parallel


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
    p.add_argument("--no-configure", action="store_true")

    # detect-taskmaster
    sub.add_parser("detect-taskmaster", help="Find MCP or CLI taskmaster")

    # configure-providers
    sub.add_parser("configure-providers", help="Configure native TaskMaster providers and local Perplexity API Free")

    # detect-providers
    sub.add_parser("detect-providers", help="Auto-detect AI providers")

    # detect-capabilities
    sub.add_parser("detect-capabilities", help="Scan for available skills and tools")

    # license-activate
    p = sub.add_parser("license-activate", help="Activate an Atlas Pro license key")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p.add_argument("license_key", help="Atlas license key")

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

    # enrich-tasks
    p = sub.add_parser("enrich-tasks", help="Add phaseConfig metadata to tasks.json")
    p.add_argument(
        "--input",
        default=None,
        help="Path to tasks.json (default: .taskmaster/tasks/tasks.json)",
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

    # fleet-waves
    p = sub.add_parser("fleet-waves", help="Compute Atlas Fleet dependency waves")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--tag", default="")

    return parser


DISPATCH = {
    "preflight": cmd_preflight,
    "engine-preflight": cmd_engine_preflight,
    "detect-taskmaster": cmd_detect_taskmaster,
    "configure-providers": cmd_configure_providers,
    "detect-providers": cmd_detect_providers,
    "detect-capabilities": cmd_detect_capabilities,
    "license-activate": cmd_license_activate,
    "load-template": cmd_load_template,
    "validate-prd": cmd_validate_prd,
    "calc-tasks": cmd_calc_tasks,
    "backup-prd": cmd_backup_prd,
    "validate-tasks": cmd_validate_tasks,
    "enrich-tasks": cmd_enrich_tasks,
    "init-taskmaster": cmd_init_taskmaster,
    "parallel-plan": parallel.cmd_plan,
    "parallel-apply": parallel.cmd_apply,
    "parallel-extract": parallel.cmd_extract,
    "parallel-inject": parallel.cmd_inject,
    "fleet-waves": fleet.cmd_fleet_waves,
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
