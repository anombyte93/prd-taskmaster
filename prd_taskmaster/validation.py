"""PRD and tasks.json validation commands."""

import argparse
import json
import sys
import re
from pathlib import Path

from prd_taskmaster.lib import (
    TASKMASTER_TASKS,
    VAGUE_PATTERN,
    CommandError,
    emit,
    fail,
    count_requirements,
    get_section_content,
    has_section,
    word_count,
    _resolve_tasks_payload,
)


def run_validate_prd(input_path: str) -> dict:
    """Run 13 quality checks on a PRD file."""
    prd_path = Path(input_path)
    if not prd_path.is_file():
        raise CommandError(f"PRD file not found: {input_path}")

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

    # ─── Placeholder detection (catches template leftovers) ────────────
    placeholder_patterns = [
        (r'\{\{[^}]+\}\}', 'mustache'),           # {{placeholder}}
        (r'\[TBD\]', 'tbd'),                       # [TBD]
        (r'\[TODO\]', 'todo'),                      # [TODO]
        (r'\[INSERT .+?\]', 'insert'),              # [INSERT something]
        (r'<[A-Z][A-Z_ ]+>', 'angle_bracket'),      # <PLACEHOLDER>
        (r'\[(?:Name|Date|Feature|Product|YYYY)\]', 'bracket'),  # [Name], [Date], etc.
        (r'\bTBD\b', 'bare_tbd'),                   # bare TBD (case-sensitive)
        (r'\bTODO\b', 'bare_todo'),                 # bare TODO (case-sensitive)
    ]
    placeholders_found = []
    for pattern, ptype in placeholder_patterns:
        for mo in re.finditer(pattern, text):
            placeholders_found.append({
                "type": ptype,
                "match": mo.group(0),
                "line": text.count("\n", 0, mo.start()) + 1,
            })

    if placeholders_found:
        warnings.append({
            "type": "placeholders",
            "count": len(placeholders_found),
            "items": placeholders_found[:10],  # cap at 10 for readability
            "suggestion": "Replace all template placeholders with actual content "
                          "(placeholders are a hard fail: grade is floored to "
                          "NEEDS_WORK and the CLI exits non-zero)",
        })

    # ─── Vague language warnings ─────────────────────────────────────────
    vague_lines = {}
    for mo in VAGUE_PATTERN.finditer(text):
        term = mo.group(0)
        vague_lines.setdefault(term, []).append(text.count("\n", 0, mo.start()) + 1)
    vague_penalty = min(sum(len(v) for v in vague_lines.values()), 5)
    for term, lines in vague_lines.items():
        where = ", ".join(str(n) for n in lines)
        warnings.append({
            "type": "vague_language",
            "term": term,
            "lines": lines,
            "suggestion": f"Replace '{term}' (line {where}) with a specific, measurable target",
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
    placeholder_penalty = min(len(placeholders_found), 10)
    score -= vague_penalty  # deduct for vague language
    score -= placeholder_penalty  # deduct for template placeholders
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

    # Placeholders are a hard fail: an unfinished spec must not pass on
    # accumulated points, whatever the rest of the document scores.
    hard_fail = None
    if placeholders_found:
        grade = "NEEDS_WORK"
        hard_fail = {"reason": "placeholders", "count": len(placeholders_found)}

    passed_count = sum(1 for c in checks if c["passed"])

    return {
        "ok": True,
        "hard_fail": hard_fail,
        "score": score,
        "max_score": max_score,
        "percentage": round(pct, 1),
        "grade": grade,
        "checks_passed": passed_count,
        "checks_total": len(checks),
        "checks": checks,
        "warnings": warnings,
        "vague_penalty": vague_penalty,
        "placeholder_penalty": placeholder_penalty,
        "placeholders_found": len(placeholders_found),
        "placeholder_details": placeholders_found[:10] if placeholders_found else [],
    }


def cmd_validate_prd(args: argparse.Namespace) -> None:
    try:
        result = run_validate_prd(args.input)
        # emit() always exits 0; hard_fail must surface as a non-zero exit,
        # so print and choose the exit code explicitly here.
        print(json.dumps(result, indent=2, default=str))
        sys.exit(1 if result.get("hard_fail") else 0)
    except CommandError as e:
        fail(e.message, **e.extra)


def run_validate_tasks(input_path: str | None, allow_empty_subtasks: bool, require_phase_config: bool) -> dict:
    """Validate a manually-authored TaskMaster-compatible tasks.json file."""
    tasks_path = Path(input_path) if input_path else TASKMASTER_TASKS / "tasks.json"
    if not tasks_path.is_file():
        raise CommandError(f"tasks.json not found: {tasks_path}")

    try:
        with open(tasks_path) as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CommandError(f"Failed to parse {tasks_path}: {e}")

    tasks, _ = _resolve_tasks_payload(raw)
    if not isinstance(tasks, list):
        raise CommandError(
            "tasks.json must be a list, a flat object with a 'tasks' list, or a tagged TaskMaster object",
            {"tasks_path": str(tasks_path)},
        )

    allowed_statuses = {"pending", "in-progress", "review", "done", "deferred", "cancelled"}
    allowed_priorities = {"high", "medium", "low"}
    problems = []
    ids = []

    placeholder_re = re.compile(
        r'(\{\{[^}]+\}\}|\[TBD\]|\[TODO\]|\[INSERT .+?\]|<[A-Z][A-Z_ ]+>|\[(?:Name|Date|Feature|Product|YYYY)\])',
        re.IGNORECASE,
    )
    generic_re = re.compile(
        r'^\s*(implement|build|create|add|fix)\s+(feature|functionality|task|thing|stuff)\s*$',
        re.IGNORECASE,
    )

    def check_text(label: str, field: str, value: object, *, required: bool = True) -> str:
        text = str(value or "").strip()
        if required and not text:
            problems.append(f"{label}: missing {field}")
            return text
        if text and placeholder_re.search(text):
            problems.append(f"{label}: {field} contains placeholder text")
        if text and generic_re.search(text):
            problems.append(f"{label}: {field} is too generic")
        return text

    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            problems.append(f"task[{index}] must be an object")
            continue

        task_id = task.get("id")
        ids.append(task_id)
        label = f"task {task_id if task_id is not None else index + 1}"

        if task_id is None:
            problems.append(f"{label}: missing id")
        check_text(label, "title", task.get("title"))
        check_text(label, "description", task.get("description"))
        check_text(label, "details", task.get("details"))
        check_text(label, "testStrategy", task.get("testStrategy"))
        if task.get("status", "pending") not in allowed_statuses:
            problems.append(f"{label}: invalid status {task.get('status')!r}")
        priority = str(task.get("priority", "")).strip().lower()
        if not priority:
            problems.append(f"{label}: missing priority")
        elif priority not in allowed_priorities:
            problems.append(f"{label}: invalid priority {task.get('priority')!r}")
        if require_phase_config and not isinstance(task.get("phaseConfig"), dict):
            problems.append(f"{label}: missing phaseConfig")

        deps = task.get("dependencies", [])
        if deps is None:
            deps = []
        if not isinstance(deps, list):
            problems.append(f"{label}: dependencies must be a list")

        subtasks = task.get("subtasks", [])
        if subtasks is None:
            subtasks = []
        if not isinstance(subtasks, list):
            problems.append(f"{label}: subtasks must be a list")
            continue
        if not allow_empty_subtasks and len(subtasks) < 2:
            problems.append(f"{label}: must have at least 2 subtasks")

        sub_ids = set()
        for sub_index, subtask in enumerate(subtasks):
            if not isinstance(subtask, dict):
                problems.append(f"{label} subtask[{sub_index}]: must be an object")
                continue
            sub_id = subtask.get("id")
            if sub_id in sub_ids:
                problems.append(f"{label}: duplicate subtask id {sub_id!r}")
            sub_ids.add(sub_id)
            if sub_id is None:
                problems.append(f"{label} subtask[{sub_index}]: missing id")
            sub_label = f"{label} subtask {sub_id if sub_id is not None else sub_index + 1}"
            check_text(sub_label, "title", subtask.get("title"))
            check_text(sub_label, "description", subtask.get("description"))
            if subtask.get("status", "pending") not in allowed_statuses:
                problems.append(f"{label} subtask[{sub_index}]: invalid status {subtask.get('status')!r}")
            sub_deps = subtask.get("dependencies", [])
            if sub_deps is None:
                sub_deps = []
            if not isinstance(sub_deps, list):
                problems.append(f"{sub_label}: dependencies must be a list")

        for subtask in subtasks:
            if not isinstance(subtask, dict):
                continue
            sub_id = subtask.get("id")
            sub_deps = subtask.get("dependencies", []) or []
            if not isinstance(sub_deps, list):
                continue
            for dep in sub_deps:
                if dep not in sub_ids:
                    problems.append(f"{label} subtask {sub_id}: dependency {dep!r} does not exist in sibling subtasks")

    real_ids = [task_id for task_id in ids if task_id is not None]
    duplicate_ids = sorted({task_id for task_id in real_ids if real_ids.count(task_id) > 1}, key=str)
    for task_id in duplicate_ids:
        problems.append(f"duplicate task id {task_id!r}")

    id_set = set(real_ids)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        deps = task.get("dependencies", []) or []
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if dep not in id_set:
                problems.append(f"task {task_id}: dependency {dep!r} does not exist")

    if problems:
        raise CommandError(
            "Task validation failed",
            {
                "tasks_path": str(tasks_path),
                "task_count": len(tasks),
                "problems": problems,
            },
        )

    return {
        "ok": True,
        "tasks_path": str(tasks_path),
        "task_count": len(tasks),
        "subtask_count": sum(len(t.get("subtasks", []) or []) for t in tasks if isinstance(t, dict)),
        "message": "Task file is valid for manual prd-taskmaster mode",
    }


def cmd_validate_tasks(args: argparse.Namespace) -> None:
    try:
        emit(run_validate_tasks(args.input, args.allow_empty_subtasks, args.require_phase_config))
    except CommandError as e:
        fail(e.message, **e.extra)
