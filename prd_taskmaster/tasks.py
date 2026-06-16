"""Task calculation, PRD backup, and tasks.json enrichment commands."""

import argparse
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path

from prd_taskmaster.lib import (
    TASKMASTER_TASKS,
    CommandError,
    emit,
    fail,
    _resolve_tasks_payload,
)


# Scale bands from discovery's Solo/Team/Enterprise classification
# (PRODUCT-SPEC US-T1: Solo 8-12 / Team 12-20 / Enterprise 20-30).
SCALE_BANDS = {
    "solo": (8, 12),
    "team": (12, 20),
    "enterprise": (20, 30),
}


def run_calc_tasks(requirements: int, scale: str | None = None) -> dict:
    """Calculate recommended task count: requirements * 1.5, clamped to the
    scale band when discovery classified one, else the generic [10, 40]."""
    raw = math.ceil(requirements * 1.5)
    if scale:
        key = scale.lower()
        if key not in SCALE_BANDS:
            raise CommandError(
                f"unknown scale: {scale}",
                {"valid_scales": sorted(SCALE_BANDS)},
            )
        lo, hi = SCALE_BANDS[key]
        formula = f"ceil(requirements * 1.5), clamped to {key} band [{lo}, {hi}]"
    else:
        lo, hi = 10, 40
        formula = "ceil(requirements * 1.5), clamped [10, 40]"
    recommended = max(lo, min(hi, raw))
    result = {
        "ok": True,
        "requirements_count": requirements,
        "raw_calculation": raw,
        "recommended": recommended,
        "formula": formula,
    }
    if scale:
        result["scale"] = scale.lower()
    return result


def cmd_calc_tasks(args: argparse.Namespace) -> None:
    try:
        emit(run_calc_tasks(args.requirements, getattr(args, "scale", None)))
    except CommandError as e:
        fail(e.message, **e.extra)


def run_backup_prd(input_path: str) -> dict:
    """Create timestamped backup of PRD."""
    src = Path(input_path)
    if not src.is_file():
        raise CommandError(f"PRD file not found: {input_path}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"prd-backup-{ts}.md"
    backup_dir = src.parent
    backup_path = backup_dir / backup_name

    shutil.copy2(str(src), str(backup_path))
    return {
        "ok": True,
        "original": str(src),
        "backup_path": str(backup_path),
        "timestamp": ts,
    }


def cmd_backup_prd(args: argparse.Namespace) -> None:
    try:
        emit(run_backup_prd(args.input))
    except CommandError as e:
        fail(e.message, **e.extra)


# ─── Complexity classification ────────────────────────────────────────────────
#
# Design note: keyword-based TYPE classification is intentional and correct here.
# Unlike domain clustering (which requires semantic understanding of system context),
# task TYPE is signaled by the task author through deliberate word choice.
# "Research", "spike", "auth", "deploy" are load-bearing words — authors use them
# precisely because they mean something specific about the work shape.
#
# Priority order matters: RESEARCH is checked before COMPLEX because a task that
# asks you to "research the best auth framework" has an immediate deliverable of a
# decision document, not an implementation. RESEARCH lifecycle is the right scaffold.
#
# AI judgment is NOT used here because enrichment is a mechanical post-parse step
# that must be deterministic, fast, and runnable without model access.
# See script module docstring: "AI handles judgment; this script handles mechanics."

# Keywords that signal high complexity or architectural work
_COMPLEX_KEYWORDS = re.compile(
    r'\b(architect|integrat|authenticat|authoriz|encrypt|migration|'
    r'schema|database|performance|scalab|security|infrastructure|'
    r'pipeline|orchestrat|distributed|concurrent|async|webhook|'
    r'deploy|docker|kubernetes|ci/cd|refactor)\b',
    re.IGNORECASE,
)

# Keywords that signal research-oriented work
_RESEARCH_KEYWORDS = re.compile(
    r'\b(research|investigat|analyz|explore|evaluat|assess|discover|'
    r'benchmark|audit|review|spike|poc|proof.of.concept)\b',
    re.IGNORECASE,
)

# Tier-specific regexes — stem-matching (prefix \b, no trailing \b) so that
# "integrate", "investigate", "evaluate" etc. are caught by their root stems.
# These are intentionally separate from _RESEARCH_KEYWORDS / _COMPLEX_KEYWORDS
# (which use \b…\b exact-word matching and must not be changed).
#
# _TIER_RESEARCH_RE: overlaps with _RESEARCH_KEYWORDS but uses prefix \b so
# "investigate", "evaluate", "analyze" are reliably caught.
_TIER_RESEARCH_RE = re.compile(
    r'\b(research|investigat|analyz|explor|evaluat|discover|'
    r'benchmark|audit|spike|poc|proof.of.concept)',
    re.IGNORECASE,
)

# _WIRED_KEYWORDS: integration / API / CLI signals that require reachability.
# Anchored carefully to avoid false-positives:
#   cli     — \bcli(?!ent|mat|nic) excludes client/climate/clinic/clinical
#   auth    — authenticat|authoriz|\bauth\b excludes author/authority/authentic
#   wire    — wire(?!frame|less) excludes wireframe/wireless
# Other stems (integrat, webhook, deploy, pipeline, api, endpoint, route,
# connect, mcp, database, migration) retain prefix \b; no trailing collisions
# identified for these.
_WIRED_KEYWORDS = re.compile(
    r'(\bintegrat|\bauthenticat|\bauthoriz|\bauth\b|\bwebhook|\bdeploy|'
    r'\bpipeline|\bapi\b|\bendpoint|\broute|\bwire(?!frame|less)|\bconnect|'
    r'\bcli(?!ent|mat|nic)|\bmcp\b|\bdatabase|\bmigration)',
    re.IGNORECASE,
)

# Lifecycle phase assignments by complexity
_LIFECYCLE_MAP = {
    "SIMPLE": ["implementation", "testing"],
    "MEDIUM": ["planning", "implementation", "testing"],
    "COMPLEX": ["planning", "implementation", "testing", "review"],
    "RESEARCH": ["research", "planning", "review"],
    "VALIDATION": ["testing", "review"],
}


def _classify_tier(task: dict) -> str:
    """Deterministically assign an altitude tier from keyword signals.

    Mapping (in priority order):
      VALIDATION / "user-test" / "user validation checkpoint" → live
      RESEARCH keywords                                       → spike
      WIRED keywords (integration signals)                   → wired
      else                                                   → domain-model  (safe default)

    The default (domain-model) means existing task graphs that have no
    integration/research/validation signal will NOT require reachability
    evidence when the reachability gate is enforced later.
    """
    title = task.get("title", "") or task.get("name", "") or ""
    description = task.get("description", "") or ""
    details = task.get("details", "") or ""
    # Strip RESEARCH NOTES appended by the parallel enrichment pass — those
    # notes should not influence tier any more than they influence complexity.
    classification_details = re.split(
        r'\n\s*RESEARCH NOTES\s*\(parallel pass\):',
        details,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    combined = f"{title} {description} {classification_details}".lower()

    # Priority 1: user-visible / validation work → live
    if "user-test" in combined or "user validation checkpoint" in title.lower():
        return "live"
    # Priority 2: research/spike work → spike
    if _TIER_RESEARCH_RE.search(combined):
        return "spike"
    # Priority 3: integration/wiring signals → wired
    if _WIRED_KEYWORDS.search(combined):
        return "wired"
    # Default: pure logic / domain work → domain-model
    return "domain-model"


def _classify_task(task: dict) -> dict:
    """Derive phaseConfig for a single task dict."""
    title = task.get("title", "") or task.get("name", "")
    description = task.get("description", "") or ""
    details = task.get("details", "") or ""
    classification_details = re.split(
        r'\n\s*RESEARCH NOTES\s*\(parallel pass\):',
        details,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    task_type = task.get("type", "") or ""

    combined = f"{title} {description} {classification_details}".lower()

    # VALIDATION: USER-TEST tasks
    if "user-test" in combined or "user validation checkpoint" in title.lower():
        complexity = "VALIDATION"
    # RESEARCH: research/investigation tasks
    elif _RESEARCH_KEYWORDS.search(combined):
        complexity = "RESEARCH"
    # COMPLEX: architectural/integration/security tasks or many subtasks
    elif _COMPLEX_KEYWORDS.search(combined) or len(task.get("subtasks", [])) >= 5:
        complexity = "COMPLEX"
    # MEDIUM: moderate — multiple subtasks or moderate description
    elif len(task.get("subtasks", [])) >= 2 or len(combined.split()) >= 30:
        complexity = "MEDIUM"
    else:
        complexity = "SIMPLE"

    requires_cdd = complexity in ("MEDIUM", "COMPLEX", "RESEARCH")
    requires_research = complexity in ("RESEARCH", "COMPLEX")

    acceptance_criteria = _generate_acceptance_criteria(task, complexity)

    return {
        "complexity": complexity,
        "tier": _classify_tier(task),
        "requiresCDD": requires_cdd,
        "requiresResearch": requires_research,
        "lifecycle": _LIFECYCLE_MAP[complexity],
        "cddCardId": None,  # Set later when CDD card is created
        "acceptanceCriteria": acceptance_criteria,
    }


def _generate_acceptance_criteria(task: dict, complexity: str) -> list:
    """Generate sensible acceptance criteria based on task content and complexity."""
    title = task.get("title", "") or task.get("name", "")
    description = task.get("description", "") or ""
    criteria = []

    # Universal criteria for all tasks
    criteria.append(f"Implementation matches requirements described in task: {title}")
    criteria.append("All automated tests pass with no regressions")

    # Complexity-specific criteria
    if complexity == "VALIDATION":
        criteria = [
            "All listed functionality manually tested and confirmed working",
            "No critical or high-severity bugs present",
            "Performance meets defined targets",
            "User experience meets acceptance standards",
        ]
    elif complexity == "RESEARCH":
        criteria.extend([
            "Research findings documented with sources",
            "Recommendation or decision recorded in task notes",
            "Trade-offs clearly articulated",
        ])
    elif complexity == "COMPLEX":
        criteria.extend([
            "Architecture decision documented (ADR or task notes)",
            "Integration points tested end-to-end",
            "Security considerations addressed",
            "Performance benchmarked against targets",
            "Code reviewed before merge",
        ])
    elif complexity == "MEDIUM":
        criteria.extend([
            "Unit tests cover primary code paths",
            "Edge cases handled and documented",
            "Code reviewed or self-reviewed",
        ])
    # SIMPLE gets only the universal criteria

    # Extract subtask-derived criteria
    for subtask in task.get("subtasks", []):
        st_title = subtask.get("title", "") or subtask.get("name", "")
        if st_title:
            criteria.append(f"Subtask completed: {st_title}")

    return criteria


def run_enrich_tasks(input_path: str | None) -> dict:
    """Enrich tasks.json with phaseConfig metadata.

    Classifies each task's complexity (SIMPLE/MEDIUM/COMPLEX/RESEARCH/VALIDATION),
    sets requiresCDD/requiresResearch flags, generates acceptanceCriteria, and
    assigns lifecycle phases. Writes phaseConfig directly into tasks.json.

    This is intentionally a direct write — TaskMaster CLI cannot inject structured
    JSON metadata, so we own the enrichment as a post-parse step.
    """
    tasks_path = Path(input_path) if input_path else TASKMASTER_TASKS / "tasks.json"
    if not tasks_path.is_file():
        raise CommandError(f"tasks.json not found: {tasks_path}")

    try:
        with open(tasks_path) as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CommandError(f"Failed to parse {tasks_path}: {e}")

    # Support {tasks: [...]}, tagged {"master": {"tasks": [...]}}, and bare list formats.
    tasks, wrapper = _resolve_tasks_payload(raw)
    if not isinstance(tasks, list):
        raise CommandError(
            "tasks.json must be a list, a flat object with a 'tasks' list, or a tagged TaskMaster object",
            {"tasks_path": str(tasks_path)},
        )

    enriched_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue

        if "phaseConfig" in task:
            # Idempotent back-fill: if an older enrich run wrote phaseConfig but
            # did not include tier (pre-tier-feature), add it now rather than
            # skipping the whole task.  An explicit non-empty tier already present
            # is left untouched (honours LLM-set or manually-set values).
            pc = task["phaseConfig"]
            if not pc.get("tier"):
                pc["tier"] = _classify_tier(task)
                enriched_count += 1
            continue

        phase_config = _classify_task(task)
        task["phaseConfig"] = phase_config
        enriched_count += 1

    # Write back atomically
    tmp_path = tasks_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(wrapper, indent=2, default=str))
        tmp_path.replace(tasks_path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise CommandError(f"Failed to write {tasks_path}: {e}")

    return {
        "ok": True,
        "tasks_path": str(tasks_path),
        "total_tasks": len(tasks),
        "enriched": enriched_count,
        "already_enriched": len(tasks) - enriched_count,
    }


def cmd_enrich_tasks(args: argparse.Namespace) -> None:
    try:
        emit(run_enrich_tasks(args.input))
    except CommandError as e:
        fail(e.message, **e.extra)
