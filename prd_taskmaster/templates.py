"""PRD template loading command."""

import argparse

from prd_taskmaster.lib import (
    TEMPLATE_DIR,
    CommandError,
    emit,
    fail,
)


def run_load_template(template_type: str) -> dict:
    """Load a PRD template by type."""
    template_map = {
        "comprehensive": TEMPLATE_DIR / "taskmaster-prd-comprehensive.md",
        "minimal": TEMPLATE_DIR / "taskmaster-prd-minimal.md",
    }
    tpl_path = template_map.get(template_type)
    if not tpl_path or not tpl_path.is_file():
        raise CommandError(f"Template not found: {template_type}", {"available": list(template_map.keys())})

    content = tpl_path.read_text()
    return {
        "ok": True,
        "type": template_type,
        "path": str(tpl_path),
        "content": content,
        "line_count": content.count('\n') + 1,
    }


def cmd_load_template(args: argparse.Namespace) -> None:
    try:
        emit(run_load_template(args.type))
    except CommandError as e:
        fail(e.message, **e.extra)
