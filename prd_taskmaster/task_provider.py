"""Project workflow providers: canonical Atlas Kanban or explicit native files.

No worker/session lifecycle lives here. The only owner effects are materialize
(always external_session) and external status (read only). Owner database
uniqueness, not the local reference cache, makes materialisation retry-safe.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile

import prd_taskmaster
from prd_taskmaster.lib import CommandError, atomic_write, locked_update
from prd_taskmaster.plan_output import (
    build_plan, content_hash, ordered_tasks, project_path, read_object,
    rooted_path, safe_operation, validate_mapping, validate_plan,
)

CONFIG_FILE = ".atlas-workflow.json"
REFERENCES_FILE = ".atlas-ai/materializations.json"
PROVIDERS = ("atlas-kanban", "taskmaster-file")
_CARD = re.compile(r"t_[A-Za-z0-9_-]+\Z")


def _config_path(root: Path) -> Path:
    return rooted_path(root, CONFIG_FILE)


def _validate_config(root: Path, config: dict) -> dict:
    if config.get("task_provider") not in PROVIDERS:
        raise CommandError("task_provider must be atlas-kanban or taskmaster-file")
    if config.get("project_root") != str(root):
        raise CommandError("config project_root does not match the explicit root")
    if not isinstance(config.get("owner_host"), str) or not config["owner_host"]:
        raise CommandError("owner_host must be explicit")
    board = config.get("board")
    if board is not None and (not isinstance(board, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", board)):
        raise CommandError("invalid board identifier")
    return config


def load_config(project_root: str) -> dict:
    """Read only. No config never silently migrates an existing .taskmaster."""
    root = project_path(project_root)
    path = _config_path(root)
    if path.exists():
        return _validate_config(root, read_object(path))
    legacy = rooted_path(root, ".taskmaster").exists()
    return {"task_provider": "taskmaster-file" if legacy else "atlas-kanban",
            "owner_host": socket.gethostname(), "board": None, "project_root": str(root),
            "notice": "Legacy .taskmaster project: staying taskmaster-file; no silent migration."
                      if legacy else "New project defaults to atlas-kanban; configure an explicit board before materialize."}


def _identity(config: dict, project: str) -> dict:
    return {key: config[key] for key in ("task_provider", "owner_host", "board", "project_root")} | {"project": project}


def _check_reference_target(refs: dict, identity: dict) -> None:
    if any(refs.get(key) != value for key, value in identity.items()):
        raise CommandError("reference target mismatch (provider, owner_host, board, project_root or project)")
    if not isinstance(refs.get("revisions"), dict):
        raise CommandError("invalid materialization references")


@safe_operation
def run_configure(project_root: str, task_provider: str | None = None,
                  owner_host: str | None = None, board: str | None = None) -> dict:
    root = project_path(project_root)
    existing = load_config(str(root))
    config = {"task_provider": task_provider or existing["task_provider"],
              "owner_host": owner_host or existing["owner_host"],
              "board": board if board is not None else existing["board"], "project_root": str(root)}
    _validate_config(root, config)
    refs_path = rooted_path(root, REFERENCES_FILE)
    if refs_path.exists():
        refs = read_object(refs_path)
        _check_reference_target(refs, _identity(config, refs.get("project")))
    locked_update(_config_path(root), lambda _: json.dumps(config, indent=2) + "\n")
    return {"ok": True, "config": config, "config_path": str(_config_path(root))}


def _owner_target(config: dict) -> None:
    # The P02 CLI is local. Never silently send a remote host's board to this host.
    if config["owner_host"] not in {socket.gethostname(), "localhost"}:
        raise CommandError("owner_host is not this host; run the owner CLI on the configured owner host")
    if not config["board"]:
        raise CommandError("configure an explicit board before contacting the owner")


def _owner_run(root: Path, config: dict, args: list[str]):
    _owner_target(config)
    try:
        return subprocess.run(["hermes", "kanban", "--board", config["board"], *args],
                              cwd=root, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise CommandError("owner CLI is unavailable; install Hermes on owner_host") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError("owner CLI timed out; outcome uncertain, retry the same materialization key") from exc


def _materialize_card(root: Path, config: dict, plan: dict, task: dict) -> dict:
    # Body is an ephemeral request, not a second task store.
    with tempfile.TemporaryDirectory(prefix="atlas-plan-body-") as tmp:
        body_path = Path(tmp) / "body.md"
        body_path.write_text(task["description"] + "\n\nAcceptance:\n" +
                             "\n".join("- " + a for a in task["acceptance"]) +
                             "\n\nPlanning is not fresh execution or verification evidence.\n")
        args = ["materialize", "--project", plan["project"], "--plan-revision", plan["plan_revision"],
                "--proposed-id", task["proposed_task_id"], "--fingerprint", task["intent_fingerprint"],
                "--title", task["title"], "--body-file", str(body_path)]
        for parent in task["dependencies"]:
            args.extend(["--parent-proposed", parent])
        args.extend(["--execution-kind", "external_session", "--json"])
        result = _owner_run(root, config, args)
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise CommandError("owner returned invalid JSON; outcome uncertain") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("task_id"), str) or not _CARD.fullmatch(payload["task_id"]):
        raise CommandError("owner returned an invalid canonical task_id")
    if result.returncode == 3 and payload.get("state") == "conflict":
        raise CommandError("materialization_conflict: owner refused changed intent",
                           {"state": "conflict", "task_id": payload["task_id"]})
    if result.returncode != 0 or payload.get("state") not in {"created", "existing"}:
        raise CommandError("owner returned an incompatible materialization response")
    _read_card(root, config, payload["task_id"])
    return {"task_id": payload["task_id"], "intent_fingerprint": task["intent_fingerprint"]}


def _read_card(root: Path, config: dict, task_id: str) -> dict:
    result = _owner_run(root, config, ["external", "status", "--task", task_id, "--json"])
    if result.returncode != 0:
        raise CommandError("owner status failed; materialization outcome must be reconciled")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise CommandError("owner status must be an object")
    card = payload.get("task", payload)
    if not isinstance(card, dict) or card.get("task_id", card.get("id")) != task_id:
        raise CommandError("owner status did not identify the requested card")
    if card.get("execution_kind") != "external_session":
        raise CommandError("owner status did not confirm execution_kind=external_session")
    return payload


def _native_card(root: Path, plan: dict, task: dict) -> dict:
    """Explicit file-mode commit. Preserve foreign tasks, tags and historical status."""
    path = rooted_path(root, ".taskmaster/tasks/tasks.json")
    selected = {}

    def update(current):
        state_path = rooted_path(root, ".taskmaster/state.json")
        tag = read_object(state_path).get("currentTag", "master") if state_path.exists() else "master"
        raw = json.loads(current) if current else {tag: {"tasks": []}}
        if not isinstance(raw, dict):
            raise CommandError("native task store must be an object")
        if isinstance(raw.get("tasks"), list):
            tasks = raw["tasks"]
        else:
            selected_tag = raw.get(tag)
            if not isinstance(selected_tag, dict) or not isinstance(selected_tag.get("tasks"), list):
                raise CommandError("native task store has no tasks list for the current tag")
            tasks = selected_tag["tasks"]
        if any(not isinstance(task, dict) or "id" not in task for task in tasks):
            raise CommandError("native task store contains an invalid task")
        for existing in tasks:
            if existing.get("plan_project") == plan["project"] and existing.get("proposed_task_id") == task["proposed_task_id"]:
                if existing.get("intent_fingerprint") != task["intent_fingerprint"]:
                    raise CommandError("materialization_conflict: native task intent changed")
                selected.update(task_id=str(existing["id"]), intent_fingerprint=task["intent_fingerprint"])
                return current
        numeric = [int(str(t["id"])) for t in tasks if str(t.get("id", "")).isdigit()]
        task_id = max(numeric, default=0) + 1
        parent_ids = []
        for dep in task["dependencies"]:
            parent = next((t for t in tasks if t.get("plan_project") == plan["project"] and t.get("proposed_task_id") == dep), None)
            if parent is None:
                raise CommandError("native dependency has not been materialized")
            parent_ids.append(parent["id"])
        tasks.append({"id": task_id, "title": task["title"], "description": task["description"],
                      "details": task["description"], "testStrategy": "\n".join(task["acceptance"]),
                      "status": "pending", "priority": "medium", "dependencies": parent_ids,
                      "subtasks": [], "plan_project": plan["project"],
                      "proposed_task_id": task["proposed_task_id"], "intent_fingerprint": task["intent_fingerprint"]})
        selected.update(task_id=str(task_id), intent_fingerprint=task["intent_fingerprint"])
        return json.dumps(raw, indent=2) + "\n"

    locked_update(path, update)
    return selected


def _check_revisions(refs: dict, plan: dict) -> dict:
    revisions = refs["revisions"]
    prior = plan.get("prior_plan_revision")
    if prior is not None:
        if prior not in revisions:
            raise CommandError("prior plan has no local canonical references; reconcile it first")
        validate_mapping(plan["prior_mapping"], revisions[prior],
                         {t["proposed_task_id"] for t in plan["tasks"]})
    elif revisions and plan["plan_revision"] not in revisions:
        raise CommandError("a revised plan requires explicit prior logical task mapping")
    existing = revisions.get(plan["plan_revision"], {})
    if not isinstance(existing, dict):
        raise CommandError("invalid revision references")
    for task in plan["tasks"]:
        reference = existing.get(task["proposed_task_id"])
        if reference is not None and (not isinstance(reference, dict) or reference.get("intent_fingerprint") != task["intent_fingerprint"]):
            raise CommandError("materialization_conflict: local reference intent changed")
    return {old: revisions[prior][old]["task_id"] for old in plan.get("prior_mapping", {})} if prior else {}


@safe_operation
def run_materialize(project_root: str, plan_path: str) -> dict:
    root = project_path(project_root)
    config = load_config(str(root))
    plan = validate_plan(read_object(rooted_path(root, plan_path)))
    path = rooted_path(root, REFERENCES_FILE)
    identity = _identity(config, plan["project"])
    # All target/mapping guards precede any task or reference writes.
    if config["task_provider"] == "atlas-kanban":
        if not _config_path(root).is_file():
            raise CommandError("persist an explicit provider config before materialize")
        _owner_target(config)
    if path.exists():
        initial = read_object(path)
        _check_reference_target(initial, identity)
        _check_revisions(initial, plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".json.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Re-read under lock: concurrent clients cannot lose reference entries.
        refs = read_object(path) if path.exists() else {**identity, "revisions": {}}
        _check_reference_target(refs, identity)
        prior_ids = _check_revisions(refs, plan)
        entries = refs["revisions"].setdefault(plan["plan_revision"], {})
        for task in ordered_tasks(plan["tasks"]):
            if config["task_provider"] == "atlas-kanban":
                entry = _materialize_card(root, config, plan, task)
            else:
                entry = _native_card(root, plan, task)
            old = entries.get(task["proposed_task_id"])
            if old is not None and old["task_id"] != entry["task_id"]:
                raise CommandError("owner canonical task_id changed for an existing materialization key")
            entries[task["proposed_task_id"]] = entry
            # Persist each success, including partial runs. Retrying still asks the owner.
            atomic_write(path, json.dumps(refs, indent=2) + "\n")
        return {"ok": True, "task_provider": config["task_provider"], "notice": config.get("notice"),
                "plan_revision": plan["plan_revision"], "reference_path": str(path),
                "task_ids": {key: value["task_id"] for key, value in entries.items()},
                "prior_task_ids": prior_ids}


@safe_operation
def run_status(project_root: str, task_id: str) -> dict:
    root = project_path(project_root)
    config = load_config(str(root))
    if config["task_provider"] != "atlas-kanban":
        raise CommandError("workflow-status requires atlas-kanban; file-mode state uses the native task commands")
    if not isinstance(task_id, str) or not _CARD.fullmatch(task_id):
        raise CommandError("invalid canonical task_id")
    return {**_read_card(root, config, task_id), "ok": True}


@safe_operation
def run_doctor(project_root: str) -> dict:
    root = project_path(project_root)
    config = load_config(str(root))
    package = {"name": "prd-taskmaster", "version": prd_taskmaster.__version__}
    if config["task_provider"] == "taskmaster-file":
        store = rooted_path(root, ".taskmaster/tasks/tasks.json")
        reachable = store.is_file() and bool(read_object(store))
        provider = {"reachable": reachable, "contract": "taskmaster-file", "optional_runtime_required": False}
    else:
        # Help is the advertised contract, not a write/read of a made-up live task.
        checks = [( ["materialize", "--help"],
                    ["--project", "--plan-revision", "--proposed-id", "--fingerprint", "--title",
                     "--body-file", "--parent-proposed", "--execution-kind", "--json"]),
                  (["external", "status", "--help"], ["--task", "--json"])]
        advertised = True
        for args, options in checks:
            result = _owner_run(root, config, args)
            advertised = advertised and result.returncode == 0 and all(o in result.stdout.split() for o in options)
        provider = {"reachable": True, "contract": "P02" if advertised else None,
                    "advertised_contract": advertised, "optional_runtime_required": False}
    return {"ok": bool(provider["reachable"]) and bool(provider["contract"]),
            "package": package, "config": config, "provider": provider,
            "notice": config.get("notice"), "read_only": True}


def _legacy_tasks(root: Path) -> tuple[str, list[dict]]:
    raw = read_object(rooted_path(root, ".taskmaster/tasks/tasks.json"))
    state_path = rooted_path(root, ".taskmaster/state.json")
    tag = read_object(state_path).get("currentTag", "master") if state_path.exists() else "master"
    selected = raw if "tasks" in raw else raw.get(tag)
    if not isinstance(selected, dict) or not isinstance(selected.get("tasks"), list):
        raise CommandError("legacy tasks list missing for current tag")
    return tag, selected["tasks"]


@safe_operation
def run_import_preview(project_root: str, project: str) -> dict:
    root = project_path(project_root)
    tag, tasks = _legacy_tasks(root)
    if not tasks:
        return {"ok": True, "proposed_cards": [], "read_only": True,
                "history_notice": "Historical completion is not fresh verification."}
    identities = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), (str, int)) or isinstance(task["id"], bool):
            raise CommandError("legacy task has an invalid foreign id")
        foreign = str(task["id"])
        if foreign in identities:
            raise CommandError("duplicate legacy foreign id")
        identities[foreign] = "legacy-" + content_hash({"tag": tag, "id": foreign})[:24]
    proposed = []
    for task in tasks:
        deps = task.get("dependencies", [])
        if not isinstance(deps, list) or any(str(d) not in identities for d in deps):
            raise CommandError("legacy dependency has no proposed card")
        proposed.append({"proposed_task_id": identities[str(task["id"])], "title": task.get("title"),
                         "description": task.get("description") or task.get("details") or task.get("title"),
                         "acceptance": [task.get("testStrategy") or "Define fresh acceptance before execution"],
                         "dependencies": [identities[str(d)] for d in deps]})
    plan = build_plan(project, proposed)
    by_id = {t["proposed_task_id"]: t for t in plan["tasks"]}
    cards = [{**by_id[identities[str(t["id"])]], "foreign_id": f"{tag}:{t['id']}",
              "historical_status": t.get("status", "unknown"), "fresh_verification": False,
              "history_notice": "Historical completion is not fresh verification."} for t in tasks]
    return {"ok": True, "plan": plan, "proposed_cards": cards, "read_only": True}
