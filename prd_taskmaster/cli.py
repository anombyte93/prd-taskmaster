"""CLI: build_parser(), DISPATCH, main()."""

import argparse

from prd_taskmaster.lib import fail
from prd_taskmaster.preflight import cmd_preflight, cmd_detect_taskmaster
from prd_taskmaster.providers import cmd_configure_providers, cmd_detect_providers
from prd_taskmaster.capabilities import cmd_detect_capabilities
from prd_taskmaster.templates import cmd_load_template
from prd_taskmaster.validation import cmd_validate_prd, cmd_validate_tasks
from prd_taskmaster.tasks import cmd_calc_tasks, cmd_backup_prd, cmd_enrich_tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prd-taskmaster-v2",
        description="PRD-TaskMaster v2 automation: deterministic operations for the prd-taskmaster-v2 skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # preflight
    sub.add_parser("preflight", help="Detect environment state")

    # detect-taskmaster
    sub.add_parser("detect-taskmaster", help="Find MCP or CLI taskmaster")

    # configure-providers
    sub.add_parser("configure-providers", help="Configure native TaskMaster providers and local Perplexity API Free")

    # detect-providers
    sub.add_parser("detect-providers", help="Auto-detect AI providers")

    # detect-capabilities
    sub.add_parser("detect-capabilities", help="Scan for available skills and tools")

    # load-template
    p = sub.add_parser("load-template", help="Load PRD template")
    p.add_argument("--type", required=True, choices=["comprehensive", "minimal"])

    # validate-prd
    p = sub.add_parser("validate-prd", help="Run 13 quality checks on a PRD")
    p.add_argument("--input", required=True, help="Path to PRD file")

    # calc-tasks
    p = sub.add_parser("calc-tasks", help="Calculate recommended task count")
    p.add_argument("--requirements", required=True, type=int, help="Number of functional requirements")

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

    return parser


DISPATCH = {
    "preflight": cmd_preflight,
    "detect-taskmaster": cmd_detect_taskmaster,
    "configure-providers": cmd_configure_providers,
    "detect-providers": cmd_detect_providers,
    "detect-capabilities": cmd_detect_capabilities,
    "load-template": cmd_load_template,
    "validate-prd": cmd_validate_prd,
    "calc-tasks": cmd_calc_tasks,
    "backup-prd": cmd_backup_prd,
    "validate-tasks": cmd_validate_tasks,
    "enrich-tasks": cmd_enrich_tasks,
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
