"""Storage-independent, content-addressed plans. Generation never writes tasks.

The driver supplies stable logical IDs, not list-position IDs. A revision maps
EVERY prior logical ID to its successor, or null to retire it. Materialisation
is a separate operation in task_provider; this module has no owner CLI effects.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
import re

from prd_taskmaster.lib import CommandError, locked_update

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def safe_operation(fn):
    """Keep IO/validation errors FR-28 safe at CLI and MCP boundaries."""
    @functools.wraps(fn)
    def guarded(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except CommandError as exc:
            return {"ok": False, "error": exc.message, **exc.extra}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return guarded


def project_path(project_root: str) -> Path:
    root = Path(project_root)
    if not root.is_absolute() or not root.is_dir():
        raise CommandError("project_root must be an explicit absolute existing directory")
    return root.resolve()


def rooted_path(root: Path, path: str) -> Path:
    supplied = Path(path)
    resolved = (root / supplied).resolve()
    if not resolved.is_relative_to(root):
        raise CommandError("path escapes project_root")
    return resolved


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise CommandError(f"expected a JSON object: {path}")
    return value


def content_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommandError(f"{label} must be non-empty text")
    return value


def _identifier(value, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CommandError(f"{label} must be a stable identifier (letters, digits, _, ., -)")
    return value


def ordered_tasks(tasks: list[dict]) -> list[dict]:
    """Topological order, deterministic among peers; refuse cycles and dangling IDs."""
    pending = {t["proposed_task_id"]: t for t in tasks}
    ordered = []
    completed = set()
    while pending:
        ready = sorted(key for key, task in pending.items()
                       if set(task["dependencies"]) <= completed)
        if not ready:
            raise CommandError("dependencies contain a cycle or an unknown proposed_task_id")
        for key in ready:
            ordered.append(pending.pop(key))
            completed.add(key)
    return ordered


def validate_mapping(mapping, previous_ids, current_ids) -> dict:
    if not isinstance(mapping, dict) or set(mapping) != set(previous_ids):
        raise CommandError("a revised plan requires an explicit mapping of every prior logical task")
    targets = [value for value in mapping.values() if value is not None]
    if any(not isinstance(v, str) or v not in current_ids for v in targets):
        raise CommandError("prior mapping names an unknown successor")
    if len(set(targets)) != len(targets):
        raise CommandError("prior mapping must be one-to-one (or null to retire)")
    if any(successor is not None and successor != prior and prior in current_ids
           for prior, successor in mapping.items()):
        raise CommandError("prior logical id remains in the plan after mapping to a different successor")
    return mapping


def _plan_body(project, tasks) -> dict:
    _identifier(project, "project")
    if not isinstance(tasks, list) or not tasks:
        raise CommandError("a plan must contain a non-empty tasks list")
    normalised = []
    ids = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise CommandError("each proposed task must be an object")
        key = _identifier(task.get("proposed_task_id"), "proposed_task_id")
        if key in ids:
            raise CommandError("duplicate proposed_task_id")
        ids.add(key)
        acceptance = task.get("acceptance")
        dependencies = task.get("dependencies", [])
        if not isinstance(acceptance, list) or not acceptance:
            raise CommandError("acceptance must be a non-empty list of checks")
        for check in acceptance:
            _text(check, "acceptance check")
        if not isinstance(dependencies, list):
            raise CommandError("dependencies must be a list")
        for dep in dependencies:
            _identifier(dep, "dependency")
        if len(set(dependencies)) != len(dependencies):
            raise CommandError("duplicate dependencies")
        intent = {"title": _text(task.get("title"), "title"),
                  "description": _text(task.get("description"), "description"),
                  "acceptance": list(acceptance), "dependencies": sorted(dependencies)}
        normalised.append({"proposed_task_id": key, **intent,
                           "intent_fingerprint": content_hash(intent)})
    ordered_tasks(normalised)
    return {"schema_version": 1, "project": project,
            "tasks": sorted(normalised, key=lambda t: t["proposed_task_id"])}


def build_plan(project: str, tasks: list[dict], *, previous_plan=None, prior_mapping=None) -> dict:
    body = _plan_body(project, tasks)
    if previous_plan is not None:
        previous = validate_plan(previous_plan)
        if previous["project"] != project:
            raise CommandError("previous plan belongs to another project")
        validate_mapping(prior_mapping, [t["proposed_task_id"] for t in previous["tasks"]],
                         {t["proposed_task_id"] for t in body["tasks"]})
        body.update(prior_plan_revision=previous["plan_revision"], prior_mapping=prior_mapping)
    elif prior_mapping is not None:
        raise CommandError("prior_mapping requires a previous_plan")
    return {**body, "plan_revision": content_hash(body)}


def validate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise CommandError("plan must be an object")
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != 1:
        raise CommandError("unsupported plan schema_version")
    body = _plan_body(plan.get("project"), plan.get("tasks"))
    if "prior_plan_revision" in plan or "prior_mapping" in plan:
        revision = plan.get("prior_plan_revision")
        mapping = plan.get("prior_mapping")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise CommandError("invalid prior_plan_revision")
        if not isinstance(mapping, dict):
            raise CommandError("prior_mapping must be an object")
        validate_mapping(mapping, mapping.keys(), {t["proposed_task_id"] for t in body["tasks"]})
        body.update(prior_plan_revision=revision, prior_mapping=mapping)
    expected = {**body, "plan_revision": content_hash(body)}
    if plan != expected:
        raise CommandError("plan content hash or intent_fingerprint mismatch; regenerate the plan")
    return expected


@safe_operation
def run_plan(project_root: str, project: str, input_path: str | None = None,
             output_path: str = ".atlas-ai/plan.json", previous_plan: str | None = None,
             prior_mapping: str | None = None, prd_path: str | None = None) -> dict:
    from prd_taskmaster.task_provider import load_config

    root = project_path(project_root)
    config = load_config(str(root))
    _identifier(project, "project")
    if input_path is not None and prd_path is not None:
        raise CommandError("input_path and prd_path are mutually exclusive")
    output = rooted_path(root, output_path)
    # A plan is an artifact, never a task store, config, or reference record.
    reserved = [root / ".taskmaster", root / ".atlas-workflow.json",
                root / ".atlas-ai/materializations.json"]
    if any(output == p or output.is_relative_to(p) for p in reserved):
        raise CommandError("plan output cannot overwrite task storage, config or references")
    if input_path is None:
        prd = rooted_path(root, prd_path) if prd_path else None
        if prd is not None and not prd.is_file():
            raise CommandError("PRD does not exist at the explicit root")
        return {"ok": True, "task_provider": config["task_provider"],
                "notice": config.get("notice"), "agent_action_required": {
                    "op": "generate_plan", "project": project,
                    "prd_path": str(prd) if prd else None, "output_path": str(output),
                    "schema_hint": {"tasks": [{"proposed_task_id": "stable-logical-id",
                        "title": "Concrete outcome", "description": "Bounded implementation",
                        "acceptance": ["Exact verification command or evidence requirement"],
                        "dependencies": []}]},
                    "then": "Use plan --input to hash plan_revision and intent_fingerprint. "
                            "Generation writes only the plan; materialize is explicit."}}
    candidate = read_object(rooted_path(root, input_path))
    previous = read_object(rooted_path(root, previous_plan)) if previous_plan else None
    mapping = read_object(rooted_path(root, prior_mapping)) if prior_mapping else None
    plan = build_plan(project, candidate.get("tasks"), previous_plan=previous, prior_mapping=mapping)
    locked_update(output, lambda _: json.dumps(plan, indent=2) + "\n")
    return {"ok": True, "task_provider": config["task_provider"],
            "notice": config.get("notice"), "plan_path": str(output), "plan": plan}
