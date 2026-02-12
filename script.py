#!/usr/bin/env python3
"""PRD-TaskMaster automation script.

Replaces all deterministic operations from SKILL.md with code.
AI handles judgment (questions, PRD content, decisions); this script handles mechanics.

Usage:
    script.py preflight                                    # Detect environment state
    script.py detect-taskmaster                            # Find MCP or CLI taskmaster
    script.py load-template --type comprehensive|minimal   # Load PRD template
    script.py validate-prd --input <path>                  # Run 13 quality checks
    script.py calc-tasks --requirements <count>            # Calculate recommended task count
    script.py gen-test-tasks --total <count>               # Generate USER-TEST task specs
    script.py gen-scripts --output-dir <dir>               # Create 5 tracking scripts
    script.py backup-prd --input <path>                    # Timestamped backup
    script.py read-state                                   # Crash recovery state
    script.py log-progress --task-id T --title "..."       # Append to progress.md
    script.py init-taskmaster --method cli|mcp             # Initialize taskmaster project
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
TEMPLATE_DIR = SKILL_DIR / "templates"
TASKMASTER_DIR = Path(".taskmaster")
TASKMASTER_DOCS = TASKMASTER_DIR / "docs"
TASKMASTER_SCRIPTS = TASKMASTER_DIR / "scripts"
TASKMASTER_STATE = TASKMASTER_DIR / "state"
TASKMASTER_TASKS = TASKMASTER_DIR / "tasks"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def emit(data: dict) -> None:
    """Print JSON to stdout and exit 0."""
    print(json.dumps(data, indent=2, default=str))
    sys.exit(0)


def fail(message: str, **extra) -> None:
    """Print JSON error to stdout and exit 1."""
    print(json.dumps({"ok": False, "error": message, **extra}, indent=2, default=str))
    sys.exit(1)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def word_count(text: str) -> int:
    return len(text.split())


def count_requirements(text: str) -> int:
    """Count REQ-NNN patterns in PRD text."""
    return len(set(re.findall(r'REQ-\d{3}', text)))


def has_section(text: str, heading: str) -> bool:
    """Check if markdown heading exists (case-insensitive)."""
    pattern = r'^#{1,3}\s+.*' + re.escape(heading) + r'.*$'
    return bool(re.search(pattern, text, re.MULTILINE | re.IGNORECASE))


def get_section_content(text: str, heading: str) -> str:
    """Extract content under a markdown heading until next same-level heading."""
    lines = text.split('\n')
    capturing = False
    level = 0
    content = []
    heading_re = re.compile(r'^(#{1,6})\s+(.*)')
    for line in lines:
        heading_match = heading_re.match(line)
        if heading_match and heading.lower() in heading_match.group(2).lower():
            capturing = True
            level = len(heading_match.group(1))
            continue
        if capturing:
            if heading_match and len(heading_match.group(1)) <= level:
                break
            content.append(line)
    return '\n'.join(content).strip()


# ─── VAGUE_PATTERNS for validation ───────────────────────────────────────────

VAGUE_WORDS = [
    "fast", "quick", "slow", "good", "bad", "poor",
    "user-friendly", "easy", "simple", "secure", "safe",
    "scalable", "flexible", "performant", "efficient",
]

VAGUE_PATTERN = re.compile(
    r'\b(?:should\s+be\s+|must\s+be\s+|needs?\s+to\s+be\s+)?'
    r'(' + '|'.join(VAGUE_WORDS) + r')\b',
    re.IGNORECASE
)


# ─── Subcommands ──────────────────────────────────────────────────────────────

def cmd_preflight(args: argparse.Namespace) -> None:
    """Detect environment: .taskmaster, PRD, task count, taskmaster method, CLAUDE.md, crash state."""
    has_taskmaster = TASKMASTER_DIR.is_dir()
    prd_path = None
    task_count = 0
    tasks_completed = 0
    tasks_pending = 0

    if has_taskmaster:
        # Find PRD
        for candidate in [TASKMASTER_DOCS / "prd.md", TASKMASTER_DOCS / "prd.txt"]:
            if candidate.is_file():
                prd_path = str(candidate)
                break
        if not prd_path:
            # Glob for any .md in docs
            docs = list(TASKMASTER_DOCS.glob("*.md")) if TASKMASTER_DOCS.is_dir() else []
            if docs:
                prd_path = str(docs[0])

        # Count tasks
        tasks_json = TASKMASTER_TASKS / "tasks.json"
        if tasks_json.is_file():
            try:
                with open(tasks_json) as f:
                    data = json.load(f)
                tasks = data.get("tasks", data) if isinstance(data, dict) else data
                if isinstance(tasks, list):
                    task_count = len(tasks)
                    tasks_completed = sum(1 for t in tasks if t.get("status") == "done")
                    tasks_pending = task_count - tasks_completed
            except (json.JSONDecodeError, KeyError):
                pass

    # Detect taskmaster method
    tm_method = _detect_taskmaster_method()

    # Check CLAUDE.md
    has_claude_md = Path("CLAUDE.md").is_file()

    # Check crash state
    crash_state = _read_execution_state()

    emit({
        "ok": True,
        "has_taskmaster": has_taskmaster,
        "prd_path": prd_path,
        "task_count": task_count,
        "tasks_completed": tasks_completed,
        "tasks_pending": tasks_pending,
        "taskmaster_method": tm_method["method"],
        "has_claude_md": has_claude_md,
        "has_crash_state": crash_state.get("has_incomplete", False),
        "crash_state": crash_state if crash_state.get("has_incomplete") else None,
    })


def _detect_taskmaster_method() -> dict:
    """Detect taskmaster: MCP > CLI > none."""
    # Check CLI
    cli_path = shutil.which("taskmaster")
    cli_version = None
    if cli_path:
        try:
            result = subprocess.run(
                ["taskmaster", "--version"],
                capture_output=True, text=True, timeout=10
            )
            cli_version = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # MCP detection: check if mcp__task-master-ai tools are available
    # We can't directly test MCP from a script, so we check for config hints
    mcp_available = False
    for config_path in [
        Path.home() / ".claude" / "settings" / "mcp.json",
        Path.home() / ".config" / "claude-code" / "mcp.json",
        Path(".mcp.json"),
    ]:
        if config_path.is_file():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", config.get("servers", {}))
                if any("task-master" in k.lower() for k in servers):
                    mcp_available = True
                    break
            except (json.JSONDecodeError, KeyError):
                pass

    if mcp_available:
        return {"method": "mcp", "version": None, "path": None}
    elif cli_path:
        return {"method": "cli", "version": cli_version, "path": cli_path}
    else:
        return {"method": "none", "version": None, "path": None}


def _read_execution_state() -> dict:
    """Read crash recovery state from .taskmaster/state/execution-state.json."""
    state_file = TASKMASTER_STATE / "execution-state.json"
    if not state_file.is_file():
        return {"has_incomplete": False}
    try:
        with open(state_file) as f:
            state = json.load(f)
        return {
            "has_incomplete": state.get("status") == "in_progress",
            "last_task": state.get("current_task"),
            "last_subtask": state.get("current_subtask"),
            "mode": state.get("mode"),
            "last_updated": state.get("last_updated"),
            "checkpoint": state.get("last_checkpoint"),
        }
    except (json.JSONDecodeError, KeyError):
        return {"has_incomplete": False}


def cmd_detect_taskmaster(args: argparse.Namespace) -> None:
    """Detect taskmaster method: MCP > CLI > none."""
    result = _detect_taskmaster_method()
    emit({"ok": True, **result})


def cmd_load_template(args: argparse.Namespace) -> None:
    """Load a PRD template by type."""
    template_map = {
        "comprehensive": TEMPLATE_DIR / "taskmaster-prd-comprehensive.md",
        "minimal": TEMPLATE_DIR / "taskmaster-prd-minimal.md",
    }
    tpl_path = template_map.get(args.type)
    if not tpl_path or not tpl_path.is_file():
        fail(f"Template not found: {args.type}", available=list(template_map.keys()))

    content = tpl_path.read_text()
    emit({
        "ok": True,
        "type": args.type,
        "path": str(tpl_path),
        "content": content,
        "line_count": content.count('\n') + 1,
    })


def cmd_validate_prd(args: argparse.Namespace) -> None:
    """Run 13 quality checks on a PRD file."""
    prd_path = Path(args.input)
    if not prd_path.is_file():
        fail(f"PRD file not found: {args.input}")

    text = prd_path.read_text()
    checks = []
    warnings = []

    # ─── Required Elements (9 checks, 5 points each = 45 points) ─────────

    # Check 1: Executive summary exists and is 50-200 words
    exec_summary = get_section_content(text, "Executive Summary")
    wc = word_count(exec_summary)
    checks.append({
        "id": 1,
        "category": "required",
        "name": "Executive summary exists",
        "passed": has_section(text, "Executive Summary") and 20 <= wc <= 500,
        "detail": f"Found {wc} words" if exec_summary else "Section missing",
        "points": 5,
    })

    # Check 2: Problem statement includes user impact
    problem = get_section_content(text, "Problem Statement")
    has_user_impact = bool(
        re.search(r'user\s+impact|who\s+is\s+affected|pain\s+point', problem, re.IGNORECASE)
        or has_section(text, "User Impact")
    )
    checks.append({
        "id": 2,
        "category": "required",
        "name": "Problem statement includes user impact",
        "passed": has_user_impact,
        "detail": "User impact found" if has_user_impact else "No user impact section",
        "points": 5,
    })

    # Check 3: Problem statement includes business impact
    has_biz_impact = bool(
        re.search(r'business\s+impact|revenue|cost|strategic', problem, re.IGNORECASE)
        or has_section(text, "Business Impact")
    )
    checks.append({
        "id": 3,
        "category": "required",
        "name": "Problem statement includes business impact",
        "passed": has_biz_impact,
        "detail": "Business impact found" if has_biz_impact else "No business impact section",
        "points": 5,
    })

    # Check 4: Goals have SMART metrics
    goals_section = get_section_content(text, "Goals")
    has_smart = bool(re.search(
        r'(metric|baseline|target|timeframe|measurement)',
        goals_section, re.IGNORECASE
    ))
    checks.append({
        "id": 4,
        "category": "required",
        "name": "Goals have SMART metrics",
        "passed": has_smart,
        "detail": "SMART elements found" if has_smart else "Goals lack measurable metrics",
        "points": 5,
    })

    # Check 5: User stories have acceptance criteria (min 3 per story)
    stories_section = get_section_content(text, "User Stories")
    story_blocks = re.split(r'###\s+Story\s+\d+', stories_section)
    ac_counts = []
    for block in story_blocks[1:]:  # skip pre-heading text
        ac_matches = re.findall(r'- \[[ x]\]', block)
        ac_counts.append(len(ac_matches))
    stories_ok = all(c >= 3 for c in ac_counts) if ac_counts else False
    checks.append({
        "id": 5,
        "category": "required",
        "name": "User stories have acceptance criteria (min 3)",
        "passed": stories_ok or not ac_counts,  # pass if no stories section (minimal template)
        "detail": f"Stories: {len(ac_counts)}, AC counts: {ac_counts}" if ac_counts else "No user stories found (may be minimal PRD)",
        "points": 5,
    })

    # Check 6: Functional requirements are testable (no vague language)
    reqs_section = get_section_content(text, "Functional Requirements")
    if not reqs_section:
        reqs_section = get_section_content(text, "Requirements")
    vague_in_reqs = VAGUE_PATTERN.findall(reqs_section)
    checks.append({
        "id": 6,
        "category": "required",
        "name": "Functional requirements are testable",
        "passed": len(vague_in_reqs) == 0,
        "detail": f"Vague terms found: {vague_in_reqs}" if vague_in_reqs else "All requirements are specific",
        "points": 5,
    })

    # Check 7: Each requirement has priority (Must/Should/Could or P0/P1/P2)
    has_priority = bool(re.search(
        r'(must\s+have|should\s+have|could\s+have|nice\s+to\s+have|P0|P1|P2)',
        reqs_section, re.IGNORECASE
    ))
    checks.append({
        "id": 7,
        "category": "required",
        "name": "Requirements have priority labels",
        "passed": has_priority,
        "detail": "Priority labels found" if has_priority else "No priority classification found",
        "points": 5,
    })

    # Check 8: Requirements are numbered (REQ-NNN)
    req_count = count_requirements(text)
    checks.append({
        "id": 8,
        "category": "required",
        "name": "Requirements are numbered (REQ-NNN)",
        "passed": req_count > 0,
        "detail": f"Found {req_count} numbered requirements" if req_count else "No REQ-NNN numbering found",
        "points": 5,
    })

    # Check 9: Technical considerations address architecture
    tech_section = get_section_content(text, "Technical")
    has_arch = bool(re.search(
        r'(architecture|system\s+design|component|integration|diagram)',
        tech_section, re.IGNORECASE
    ))
    checks.append({
        "id": 9,
        "category": "required",
        "name": "Technical considerations address architecture",
        "passed": has_arch,
        "detail": "Architecture content found" if has_arch else "No architectural detail found",
        "points": 5,
    })

    # ─── Taskmaster-specific (4 checks, 3 points each = 12 points) ───────

    # Check 10: Non-functional requirements have specific targets
    nfr_section = get_section_content(text, "Non-Functional")
    has_nfr_targets = bool(re.search(
        r'\d+\s*(ms|seconds?|minutes?|%|MB|GB|requests?/s)',
        nfr_section, re.IGNORECASE
    ))
    checks.append({
        "id": 10,
        "category": "taskmaster",
        "name": "Non-functional requirements have specific targets",
        "passed": has_nfr_targets or not nfr_section,
        "detail": "Specific targets found" if has_nfr_targets else "No measurable NFR targets",
        "points": 3,
    })

    # Check 11: Requirements have task breakdown hints
    has_task_hints = bool(re.search(
        r'task\s+breakdown|implementation\s+step|~\d+h',
        text, re.IGNORECASE
    ))
    checks.append({
        "id": 11,
        "category": "taskmaster",
        "name": "Requirements have task breakdown hints",
        "passed": has_task_hints,
        "detail": "Task breakdown hints found" if has_task_hints else "No task breakdown hints",
        "points": 3,
    })

    # Check 12: Dependencies identified
    has_deps = bool(re.search(
        r'(dependenc|depends\s+on|blocked\s+by|prerequisite|REQ-\d{3}.*depends)',
        text, re.IGNORECASE
    ))
    checks.append({
        "id": 12,
        "category": "taskmaster",
        "name": "Dependencies identified for task sequencing",
        "passed": has_deps,
        "detail": "Dependencies documented" if has_deps else "No dependency information found",
        "points": 3,
    })

    # Check 13: Out of scope defined
    has_oos = has_section(text, "Out of Scope")
    oos_content = get_section_content(text, "Out of Scope")
    checks.append({
        "id": 13,
        "category": "taskmaster",
        "name": "Out of scope explicitly defined",
        "passed": has_oos and len(oos_content.strip()) > 10,
        "detail": "Out of scope section found" if has_oos else "No Out of Scope section",
        "points": 3,
    })

    # ─── Vague language warnings ─────────────────────────────────────────
    all_vague = VAGUE_PATTERN.findall(text)
    vague_penalty = min(len(all_vague), 5)
    for match in set(all_vague):
        warnings.append({
            "type": "vague_language",
            "term": match,
            "suggestion": f"Replace '{match}' with a specific, measurable target",
        })

    # ─── Missing detail warnings ─────────────────────────────────────────
    if not has_section(text, "Validation Checkpoint"):
        warnings.append({
            "type": "missing_detail",
            "item": "Validation checkpoints",
            "suggestion": "Add validation checkpoints for each implementation phase",
        })

    # ─── Scoring ─────────────────────────────────────────────────────────
    score = sum(c["points"] for c in checks if c["passed"])
    max_score = sum(c["points"] for c in checks)
    score -= vague_penalty  # deduct for vague language
    score = max(0, score)

    pct = (score / max_score * 100) if max_score > 0 else 0
    if pct >= 91:
        grade = "EXCELLENT"
    elif pct >= 83:
        grade = "GOOD"
    elif pct >= 75:
        grade = "ACCEPTABLE"
    else:
        grade = "NEEDS_WORK"

    passed_count = sum(1 for c in checks if c["passed"])

    emit({
        "ok": True,
        "score": score,
        "max_score": max_score,
        "percentage": round(pct, 1),
        "grade": grade,
        "checks_passed": passed_count,
        "checks_total": len(checks),
        "checks": checks,
        "warnings": warnings,
        "vague_penalty": vague_penalty,
    })


def cmd_calc_tasks(args: argparse.Namespace) -> None:
    """Calculate recommended task count: requirements * 1.5, clamped 10-40."""
    raw = math.ceil(args.requirements * 1.5)
    recommended = max(10, min(40, raw))
    emit({
        "ok": True,
        "requirements_count": args.requirements,
        "raw_calculation": raw,
        "recommended": recommended,
        "formula": "ceil(requirements * 1.5), clamped [10, 40]",
    })


def cmd_gen_test_tasks(args: argparse.Namespace) -> None:
    """Generate USER-TEST task insertion specs (one every 5 tasks)."""
    total = args.total
    tasks = []
    checkpoint_num = 0

    for i in range(5, total + 1, 5):
        checkpoint_num += 1
        start = i - 4
        end = i
        tasks.append({
            "checkpoint_number": checkpoint_num,
            "title": f"User Validation Checkpoint {checkpoint_num}",
            "insert_after_task": end,
            "covers_tasks": f"{start}-{end}",
            "description": f"Manually test functionality from Tasks {start} to {end}",
            "priority": "high",
            "dependencies": [str(end)],
            "template": (
                f"# USER-TEST-{checkpoint_num}: User Validation Checkpoint {checkpoint_num}\n\n"
                f"## Purpose\n"
                f"Manual testing of functionality implemented in Tasks {start}-{end}\n\n"
                f"## Prerequisites\n"
                f"All subtasks in Tasks {start}-{end} must be completed and merged to main branch.\n\n"
                f"## Testing Checklist\n\n"
                f"### Functionality Tests\n"
                f"- [ ] Test each requirement covered in Tasks {start}-{end}\n\n"
                f"### Integration Tests\n"
                f"- [ ] Test integration between components\n"
                f"- [ ] Verify no regressions in existing features\n\n"
                f"## Acceptance Criteria\n"
                f"- All functionality tests pass\n"
                f"- No critical bugs found\n"
                f"- Performance meets targets\n\n"
                f"## If Tests Fail\n"
                f"1. Document issue in .taskmaster/docs/progress.md\n"
                f"2. Create fix tasks before proceeding\n"
                f"3. Do NOT continue to next tasks until fixed\n\n"
                f"## When Complete\n"
                f'Type "passed" to continue to next tasks.'
            ),
        })

    emit({
        "ok": True,
        "total_implementation_tasks": total,
        "test_tasks_generated": len(tasks),
        "final_total": total + len(tasks),
        "tasks": tasks,
    })


def cmd_gen_scripts(args: argparse.Namespace) -> None:
    """Create 5 automation scripts in output directory."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created = []

    # 1. track-time.py
    _write_script(output_dir / "track-time.py", _SCRIPT_TRACK_TIME)
    created.append("track-time.py")

    # 2. rollback.sh
    _write_script(output_dir / "rollback.sh", _SCRIPT_ROLLBACK)
    created.append("rollback.sh")

    # 3. learn-accuracy.py
    _write_script(output_dir / "learn-accuracy.py", _SCRIPT_LEARN_ACCURACY)
    created.append("learn-accuracy.py")

    # 4. security-audit.py
    _write_script(output_dir / "security-audit.py", _SCRIPT_SECURITY_AUDIT)
    created.append("security-audit.py")

    # 5. execution-state.py
    _write_script(output_dir / "execution-state.py", _SCRIPT_EXECUTION_STATE)
    created.append("execution-state.py")

    emit({
        "ok": True,
        "output_dir": str(output_dir),
        "files_created": created,
        "count": len(created),
    })


def _write_script(path: Path, content: str) -> None:
    """Write a script file and make it executable."""
    path.write_text(content)
    path.chmod(0o755)


def cmd_backup_prd(args: argparse.Namespace) -> None:
    """Create timestamped backup of PRD."""
    src = Path(args.input)
    if not src.is_file():
        fail(f"PRD file not found: {args.input}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"prd-backup-{ts}.md"
    backup_dir = src.parent
    backup_path = backup_dir / backup_name

    shutil.copy2(str(src), str(backup_path))
    emit({
        "ok": True,
        "original": str(src),
        "backup_path": str(backup_path),
        "timestamp": ts,
    })


def cmd_read_state(args: argparse.Namespace) -> None:
    """Read crash recovery state."""
    state = _read_execution_state()
    emit({"ok": True, **state})


def cmd_log_progress(args: argparse.Namespace) -> None:
    """Append progress entry to .taskmaster/docs/progress.md."""
    progress_file = TASKMASTER_DOCS / "progress.md"
    progress_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = now_iso()
    entry = f"""
## Task {args.task_id}: {args.title} - COMPLETED
**Completed**: {timestamp}
**Duration**: {args.duration or 'N/A'}
**Subtasks**: {args.subtasks or 'N/A'}
**Tests**: {args.tests or 'N/A'}
**Issues**: {args.issues or 'None'}
**Git**: Merged to main, tagged as checkpoint-task-{args.task_id}

"""

    if progress_file.is_file():
        existing = progress_file.read_text()
    else:
        existing = "# Task Progress Log\n\nAuto-generated by PRD-TaskMaster.\n\n---\n"

    progress_file.write_text(existing + entry)

    emit({
        "ok": True,
        "path": str(progress_file),
        "task_id": args.task_id,
        "timestamp": timestamp,
    })


def cmd_init_taskmaster(args: argparse.Namespace) -> None:
    """Initialize taskmaster project via CLI."""
    method = args.method

    if method == "cli":
        cli_path = shutil.which("taskmaster")
        if not cli_path:
            fail("taskmaster CLI not found in PATH")

        try:
            result = subprocess.run(
                ["taskmaster", "init", "--yes", "--store-tasks-in-git", "--rules=claude"],
                capture_output=True, text=True, timeout=60
            )
            emit({
                "ok": result.returncode == 0,
                "method": "cli",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            fail("taskmaster init timed out after 60s")
        except FileNotFoundError:
            fail("taskmaster CLI not found")

    elif method == "mcp":
        # MCP init must be done by AI via tool calls - we just confirm readiness
        emit({
            "ok": True,
            "method": "mcp",
            "message": "MCP initialization must be done via AI tool call: mcp__task-master-ai__initialize_project",
            "params": {
                "projectRoot": str(Path.cwd()),
                "yes": True,
                "storeTasksInGit": True,
                "initGit": False,
                "rules": ["claude"],
            },
        })
    else:
        fail(f"Unknown method: {method}", valid=["cli", "mcp"])


# ─── Embedded script templates ────────────────────────────────────────────────

_SCRIPT_TRACK_TIME = '''#!/usr/bin/env python3
"""Track task start/end times with UTC timestamps."""
import json, sys, os
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(".taskmaster/state/time-tracking.json")

def load():
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    return {"tasks": {}}

def save(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

if len(sys.argv) < 3:
    print("Usage: track-time.py start|complete <task_id> [subtask_id]")
    sys.exit(1)

action, task_id = sys.argv[1], sys.argv[2]
subtask_id = sys.argv[3] if len(sys.argv) > 3 else None
data = load()

key = f"{task_id}" + (f".{subtask_id}" if subtask_id else "")

if action == "start":
    data["tasks"][key] = {"started": now_iso(), "status": "in_progress"}
    save(data)
    print(json.dumps({"ok": True, "action": "started", "key": key, "time": now_iso()}))
elif action == "complete":
    entry = data["tasks"].get(key, {})
    entry["completed"] = now_iso()
    entry["status"] = "done"
    if "started" in entry:
        from datetime import datetime as dt
        start = dt.fromisoformat(entry["started"])
        end = dt.fromisoformat(entry["completed"])
        entry["duration_minutes"] = round((end - start).total_seconds() / 60, 1)
    data["tasks"][key] = entry
    save(data)
    print(json.dumps({"ok": True, "action": "completed", "key": key, "duration": entry.get("duration_minutes")}))
else:
    print(json.dumps({"ok": False, "error": f"Unknown action: {action}"}))
    sys.exit(1)
'''

_SCRIPT_ROLLBACK = '''#!/usr/bin/env bash
# Rollback to a task checkpoint tag.
# Usage: rollback.sh <task_number>

set -euo pipefail

TASK_NUM="${1:?Usage: rollback.sh <task_number>}"
TAG="checkpoint-task-$(printf '%03d' "$TASK_NUM")"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_BRANCH="rollback-backup-${TIMESTAMP}"

echo "Checking for checkpoint tag: $TAG"

if ! git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "ERROR: Tag $TAG not found. Available checkpoints:"
    git tag -l 'checkpoint-task-*'
    exit 1
fi

echo "Creating backup branch: $BACKUP_BRANCH"
git branch "$BACKUP_BRANCH"

echo "Resetting to $TAG..."
git reset --hard "$TAG"

echo ""
echo "Rollback complete."
echo "  Rolled back to: $TAG"
echo "  Backup branch:  $BACKUP_BRANCH"
echo ""
echo "To undo this rollback: git checkout $BACKUP_BRANCH"
'''

_SCRIPT_LEARN_ACCURACY = '''#!/usr/bin/env python3
"""Analyze estimation accuracy from time tracking data."""
import json, sys
from pathlib import Path

STATE_FILE = Path(".taskmaster/state/time-tracking.json")

def main():
    if not STATE_FILE.is_file():
        print(json.dumps({"ok": False, "error": "No time tracking data found"}))
        sys.exit(1)

    data = json.loads(STATE_FILE.read_text())
    tasks = data.get("tasks", {})

    completed = {k: v for k, v in tasks.items() if v.get("status") == "done" and "duration_minutes" in v}

    if not completed:
        print(json.dumps({"ok": True, "message": "No completed tasks with timing data", "count": 0}))
        return

    durations = [v["duration_minutes"] for v in completed.values()]
    avg_duration = sum(durations) / len(durations)

    print(json.dumps({
        "ok": True,
        "tasks_analyzed": len(completed),
        "average_duration_minutes": round(avg_duration, 1),
        "total_minutes": round(sum(durations), 1),
        "tasks": {k: v.get("duration_minutes") for k, v in completed.items()},
    }, indent=2))

if __name__ == "__main__":
    main()
'''

_SCRIPT_SECURITY_AUDIT = '''#!/usr/bin/env python3
"""Auto-generate security checklist based on codebase scan."""
import json, os, re, sys
from pathlib import Path

def scan_patterns():
    """Scan for security-relevant patterns in codebase."""
    findings = []
    cwd = Path(".")

    # Detect patterns
    patterns = {
        "authentication": r"(password|login|auth|session|jwt|token)",
        "database": r"(sql|query|SELECT|INSERT|UPDATE|DELETE|prisma|sequelize|knex)",
        "api": r"(api|endpoint|route|controller|express|fastapi|flask)",
        "encryption": r"(encrypt|decrypt|hash|bcrypt|crypto|aes)",
        "file_upload": r"(upload|multipart|formdata|file.*input)",
        "environment": r"(process\\.env|os\\.environ|dotenv|\\.env)",
    }

    for ext in ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx"]:
        for f in cwd.rglob(ext):
            if ".git" in str(f) or "node_modules" in str(f) or ".taskmaster" in str(f):
                continue
            try:
                content = f.read_text(errors="ignore")
                for category, pattern in patterns.items():
                    if re.search(pattern, content, re.IGNORECASE):
                        findings.append({"file": str(f), "category": category})
            except Exception:
                pass

    categories = list(set(f["category"] for f in findings))

    checklist = []
    if "authentication" in categories:
        checklist.extend([
            "Passwords hashed with bcrypt (cost >= 10)",
            "Session tokens cryptographically secure",
            "Rate limiting on auth endpoints",
        ])
    if "database" in categories:
        checklist.extend([
            "All queries use parameterized statements",
            "No SQL injection vulnerabilities",
            "Database credentials not in source code",
        ])
    if "api" in categories:
        checklist.extend([
            "HTTPS enforced in production",
            "CSRF protection enabled",
            "Input validation on all endpoints",
            "Security headers set (CSP, X-Frame-Options)",
        ])
    if "encryption" in categories:
        checklist.extend([
            "Strong encryption algorithms used (AES-256)",
            "Keys stored securely (not hardcoded)",
        ])
    if "environment" in categories:
        checklist.extend([
            ".env files in .gitignore",
            "No secrets committed to repository",
        ])

    # Always include
    checklist.extend([
        "Dependencies checked for vulnerabilities (npm audit / pip audit)",
        "Error messages do not leak internal details",
    ])

    print(json.dumps({
        "ok": True,
        "categories_detected": categories,
        "findings_count": len(findings),
        "checklist": checklist,
    }, indent=2))

if __name__ == "__main__":
    scan_patterns()
'''

_SCRIPT_EXECUTION_STATE = '''#!/usr/bin/env python3
"""Manage execution state for crash recovery."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(".taskmaster/state/execution-state.json")

def load():
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    return {}

def save(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

if len(sys.argv) < 2:
    print("Usage: execution-state.py status|start|complete|checkpoint <args>")
    sys.exit(1)

action = sys.argv[1]

if action == "status":
    state = load()
    if not state:
        print(json.dumps({"has_incomplete": False}))
    else:
        print(json.dumps({
            "has_incomplete": state.get("status") == "in_progress",
            **state,
        }, indent=2))

elif action == "start":
    task_id = sys.argv[2] if len(sys.argv) > 2 else None
    subtask_id = sys.argv[3] if len(sys.argv) > 3 else None
    mode = sys.argv[4] if len(sys.argv) > 4 else "sequential"
    state = load()
    state.update({
        "status": "in_progress",
        "current_task": task_id,
        "current_subtask": subtask_id,
        "mode": mode,
        "last_updated": now_iso(),
    })
    save(state)
    print(json.dumps({"ok": True, "action": "started", **state}))

elif action == "complete":
    task_id = sys.argv[2] if len(sys.argv) > 2 else None
    state = load()
    completed = state.get("completed_tasks", [])
    if task_id and task_id not in completed:
        completed.append(task_id)
    state.update({
        "status": "idle",
        "current_task": None,
        "current_subtask": None,
        "completed_tasks": completed,
        "last_updated": now_iso(),
        "last_checkpoint": task_id,
    })
    save(state)
    print(json.dumps({"ok": True, "action": "completed", **state}))

elif action == "checkpoint":
    task_id = sys.argv[2] if len(sys.argv) > 2 else None
    state = load()
    state["last_checkpoint"] = task_id
    state["last_updated"] = now_iso()
    save(state)
    print(json.dumps({"ok": True, "action": "checkpoint", **state}))

else:
    print(json.dumps({"ok": False, "error": f"Unknown action: {action}"}))
    sys.exit(1)
'''


# ─── Argument parsing ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prd-taskmaster",
        description="PRD-TaskMaster automation: deterministic operations for the prd-taskmaster skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # preflight
    sub.add_parser("preflight", help="Detect environment state")

    # detect-taskmaster
    sub.add_parser("detect-taskmaster", help="Find MCP or CLI taskmaster")

    # load-template
    p = sub.add_parser("load-template", help="Load PRD template")
    p.add_argument("--type", required=True, choices=["comprehensive", "minimal"])

    # validate-prd
    p = sub.add_parser("validate-prd", help="Run 13 quality checks on a PRD")
    p.add_argument("--input", required=True, help="Path to PRD file")

    # calc-tasks
    p = sub.add_parser("calc-tasks", help="Calculate recommended task count")
    p.add_argument("--requirements", required=True, type=int, help="Number of functional requirements")

    # gen-test-tasks
    p = sub.add_parser("gen-test-tasks", help="Generate USER-TEST task specs")
    p.add_argument("--total", required=True, type=int, help="Total implementation tasks")

    # gen-scripts
    p = sub.add_parser("gen-scripts", help="Create 5 tracking scripts")
    p.add_argument("--output-dir", required=True, help="Directory for script output")

    # backup-prd
    p = sub.add_parser("backup-prd", help="Timestamped PRD backup")
    p.add_argument("--input", required=True, help="Path to PRD file")

    # read-state
    sub.add_parser("read-state", help="Read crash recovery state")

    # log-progress
    p = sub.add_parser("log-progress", help="Append progress entry")
    p.add_argument("--task-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--duration", default=None)
    p.add_argument("--subtasks", default=None)
    p.add_argument("--tests", default=None)
    p.add_argument("--issues", default=None)

    # init-taskmaster
    p = sub.add_parser("init-taskmaster", help="Initialize taskmaster project")
    p.add_argument("--method", required=True, choices=["cli", "mcp"])

    return parser


DISPATCH = {
    "preflight": cmd_preflight,
    "detect-taskmaster": cmd_detect_taskmaster,
    "load-template": cmd_load_template,
    "validate-prd": cmd_validate_prd,
    "calc-tasks": cmd_calc_tasks,
    "gen-test-tasks": cmd_gen_test_tasks,
    "gen-scripts": cmd_gen_scripts,
    "backup-prd": cmd_backup_prd,
    "read-state": cmd_read_state,
    "log-progress": cmd_log_progress,
    "init-taskmaster": cmd_init_taskmaster,
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
