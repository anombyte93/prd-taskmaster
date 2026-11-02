"""Project workflow providers: canonical Atlas Kanban or explicit native files.

No worker/session lifecycle lives here. The only owner effects are materialize
(always external_session) and external status (read only). Owner database
uniqueness, not the local reference cache, makes materialisation retry-safe.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
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
    legacy = rooted_path(root, ".taskmaster/tasks/tasks.json").is_file()
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


def _owner_executable() -> str:
    # Resolve in the caller, before subprocess cwd changes. Empty/dot PATH
    # entries must never turn a project's own `hermes` file into the owner.
    directories = [str(Path(entry).resolve()) for entry in os.get_exec_path()
                   if entry and Path(entry) != Path(".")]
    executable = shutil.which("hermes", path=os.pathsep.join(directories)) if directories else None
    if executable is None:
        raise CommandError("owner CLI is unavailable; install Hermes on owner_host")
    return str(Path(executable).resolve())


def _owner_run(root: Path, config: dict, args: list[str]):
    _owner_target(config)
    executable = _owner_executable()
    try:
        return subprocess.run([executable, "kanban", "--board", config["board"], *args],
                              cwd=root, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise CommandError("owner CLI is unavailable; install Hermes on owner_host") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError("owner CLI timed out; outcome uncertain, retry the same materialization key") from exc


def _owner_payload(result, config: dict) -> dict:
    # Refusals need not identify a card. Decode them before validating success IDs.
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        board = config["board"]
        missing_board = (f"kanban: board {board!r} does not exist. "
                         f"Create it with `hermes kanban boards create {board}`.")
        if result.returncode == 1 and result.stderr.strip() == missing_board:
            raise CommandError(missing_board, {"state": "refused", "reason": "board_not_found"}) from exc
        if result.returncode == 2:
            raise CommandError("owner CLI rejected the arguments", {"state": "refused", "reason": "owner_cli_usage_error"}) from exc
        # Arbitrary stderr can contain secrets. Only the exact safe board refusal
        # above is surfaced; malformed/unknown write responses still need reconciliation.
        raise CommandError("owner returned invalid JSON; outcome uncertain") from exc
    if not isinstance(payload, dict):
        raise CommandError("owner response must be an object")
    state = payload.get("state")
    if ((result.returncode == 3 and state == "conflict") or
            (result.returncode != 0 and state == "refused")):
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason:
            raise CommandError("owner refusal has no reason")
        extra = {"state": state, "reason": reason}
        task_id = payload.get("task_id")
        if isinstance(task_id, str) and _CARD.fullmatch(task_id):
            extra["task_id"] = task_id
        raise CommandError(reason, extra)
    if result.returncode != 0:
        raise CommandError("owner returned an incompatible materialization response")
    return payload


def _task_request(plan: dict, task: dict) -> dict:
    return {"proposed_task_id": task["proposed_task_id"],
            "intent_fingerprint": task["intent_fingerprint"], "title": task["title"],
            "body": task["description"] + "\n\nAcceptance:\n" +
                    "\n".join("- " + a for a in task["acceptance"]) +
                    "\n\nPlanning is not fresh execution or verification evidence.\n",
            "parent_proposed": task["dependencies"], "execution_kind": "external_session",
            "maps_from": next((plan["prior_plan_revision"] + ":" + prior_id
                               for prior_id, successor in plan.get("prior_mapping", {}).items()
                               if successor == task["proposed_task_id"]), None)}


def _check_plan(root: Path, config: dict, plan: dict) -> None:
    """Ruling 13 owner seam. No fallback to creates if this check is unavailable.

    Assumed owner command: materialize-check --plan-file PATH --json. The batch
    contains the exact requests we will send, in dependency order. The owner must
    evaluate the whole projected revision, including not-yet-created parents,
    without persisting cards, materializations, mapping events or retirements.
    """
    request = {"project": plan["project"], "plan_revision": plan["plan_revision"],
               "tasks": [_task_request(plan, task) for task in ordered_tasks(plan["tasks"])]}
    with tempfile.TemporaryDirectory(prefix="atlas-plan-check-") as tmp:
        path = Path(tmp) / "plan.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        result = _owner_run(root, config, ["materialize-check", "--plan-file", str(path), "--json"])
    payload = _owner_payload(result, config)
    if payload.get("state") != "checked":
        raise CommandError("owner did not confirm a side-effect-free plan check")


def _materialize_card(root: Path, config: dict, plan: dict, task: dict) -> dict:
    request = _task_request(plan, task)
    # Body is an ephemeral request, not a second task store.
    with tempfile.TemporaryDirectory(prefix="atlas-plan-body-") as tmp:
        body_path = Path(tmp) / "body.md"
        body_path.write_text(request["body"], encoding="utf-8")
        args = ["materialize", "--project", plan["project"], "--plan-revision", plan["plan_revision"],
                "--proposed-id", task["proposed_task_id"], "--fingerprint", task["intent_fingerprint"],
                "--title=" + task["title"], "--body-file", str(body_path)]
        for parent in request["parent_proposed"]:
            args.extend(["--parent-proposed", parent])
        for prior_id, successor in plan.get("prior_mapping", {}).items():
            if successor == task["proposed_task_id"]:
                args.extend(["--maps-from", plan["prior_plan_revision"] + ":" + prior_id])
        args.extend(["--execution-kind", "external_session", "--json"])
        result = _owner_run(root, config, args)
    payload = _owner_payload(result, config)
    if not isinstance(payload.get("task_id"), str) or not _CARD.fullmatch(payload["task_id"]):
        raise CommandError("owner returned an invalid canonical task_id")
    if payload.get("state") not in {"created", "existing", "mapped"}:
        raise CommandError("owner returned an incompatible materialization response")
    try:
        _read_card(root, config, payload["task_id"])
    except (CommandError, OSError, ValueError, TypeError, KeyError) as exc:
        raise CommandError(str(exc), {"created_task_ids":
            {task["proposed_task_id"]: payload["task_id"]} if payload["state"] == "created" else {},
            "owner_task_id": payload["task_id"]}) from exc
    return {"task_id": payload["task_id"], "intent_fingerprint": task["intent_fingerprint"],
            "owner_state": payload["state"]}


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


def _check_revisions(refs: dict, plan: dict, owner_authoritative: bool = False) -> dict:
    revisions = refs["revisions"]
    prior = plan.get("prior_plan_revision")
    if owner_authoritative:
        # Cached lineage is optional. Only the owner may decide intent conflicts
        # and cross-revision identity, even when every local reference is lost.
        entries = revisions.get(prior, {})
        return {old: entries[old]["task_id"] for old in plan.get("prior_mapping", {}) if old in entries}
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
        _check_revisions(initial, plan, config["task_provider"] == "atlas-kanban")
    if config["task_provider"] == "atlas-kanban":
        _check_plan(root, config, plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".json.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Re-read under lock: concurrent clients cannot lose reference entries.
        refs = read_object(path) if path.exists() else {**identity, "revisions": {}}
        _check_reference_target(refs, identity)
        prior_ids = _check_revisions(refs, plan, config["task_provider"] == "atlas-kanban")
        entries = refs["revisions"].setdefault(plan["plan_revision"], {})
        created = {}
        verified = {}
        for task in ordered_tasks(plan["tasks"]):
            try:
                if config["task_provider"] == "atlas-kanban":
                    entry = _materialize_card(root, config, plan, task)
                    if entry.pop("owner_state") == "created":
                        created[task["proposed_task_id"]] = entry["task_id"]
                else:
                    entry = _native_card(root, plan, task)
                verified[task["proposed_task_id"]] = entry["task_id"]
                old = entries.get(task["proposed_task_id"])
                if old is not None and old["task_id"] != entry["task_id"]:
                    raise CommandError("owner canonical task_id changed for an existing materialization key")
                entries[task["proposed_task_id"]] = entry
                # Persist each verified success. Retrying still asks the owner.
                atomic_write(path, json.dumps(refs, indent=2) + "\n")
            except (CommandError, OSError, ValueError, TypeError, KeyError) as exc:
                extra = exc.extra if isinstance(exc, CommandError) else {}
                created.update(extra.get("created_task_ids", {}))
                raise CommandError(str(exc), {**extra, "state": "partial",
                    "created_task_ids": created, "task_ids": verified,
                    "failed_proposed_task_id": task["proposed_task_id"]}) from exc
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
    # Keep independent observations even when a later diagnostic cannot run.
    provider = {"reachable": "UNKNOWN", "contract": "UNKNOWN",
                "advertised_contract": "UNKNOWN", "optional_runtime_required": False}
    report = {"ok": False, "package": {"name": "prd-taskmaster", "version": prd_taskmaster.__version__},
              "config": "UNKNOWN", "provider": provider, "read_only": True, "diagnostics": []}
    errors = (CommandError, OSError, ValueError, TypeError, KeyError)
    try:
        root = project_path(project_root)
        config = load_config(str(root))
    except errors:
        report["diagnostics"].append("config unread; check the explicit project root and provider config")
        return report
    report.update(config=config, notice=config.get("notice"))
    if config["task_provider"] == "taskmaster-file":
        provider.update(contract="taskmaster-file", advertised_contract=True)
        try:
            provider["reachable"] = bool(read_object(rooted_path(root, ".taskmaster/tasks/tasks.json")))
        except errors:
            report["diagnostics"].append("native task store unread")
    else:
        try:
            _owner_target(config)
            _owner_executable()
        except errors:
            report["diagnostics"].append("owner target or CLI unavailable; reachability and contract unread")
            return report
        # Help advertises syntax only. It never proves board/card reachability.
        checks = [(["materialize-check", "--help"], ["--plan-file", "--json"]),
                  (["materialize", "--help"],
                   ["--project", "--plan-revision", "--proposed-id", "--fingerprint", "--title",
                    "--body-file", "--parent-proposed", "--maps-from", "--execution-kind", "--json"]),
                  (["external", "status", "--help"], ["--task", "--json"])]
        try:
            advertised = True
            for args, options in checks:
                result = _owner_run(root, config, args)
                advertised = advertised and result.returncode == 0 and all(o in result.stdout.split() for o in options)
            provider.update(advertised_contract=advertised, contract="P02" if advertised else "UNKNOWN")
        except errors:
            report["diagnostics"].append("advertised owner contract unread")
        # The contracted read requires a real task ID. Never invent a probe card,
        # create a task, or equate help output with a healthy configured board.
        task_id = None
        try:
            path = rooted_path(root, REFERENCES_FILE)
            if path.exists():
                refs = read_object(path)
                project = refs.get("project")
                if not isinstance(project, str):
                    raise CommandError("invalid reference project")
                _check_reference_target(refs, _identity(config, project))
                revisions = list(refs["revisions"].values())
                if any(not isinstance(revision, dict) for revision in revisions):
                    raise CommandError("invalid revision references")
                entries = [entry for revision in revisions for entry in revision.values()]
                if any(not isinstance(entry, dict) for entry in entries):
                    raise CommandError("invalid card references")
                task_id = next((entry["task_id"] for entry in entries), None)
                if task_id is not None and (not isinstance(task_id, str) or not _CARD.fullmatch(task_id)):
                    raise CommandError("invalid reference task_id")
        except errors:
            report["diagnostics"].append("canonical references unread")
            task_id = None
        if task_id is None:
            report["diagnostics"].append("reachability UNKNOWN: no readable canonical task reference for external status")
        else:
            try:
                _read_card(root, config, task_id)
                provider["reachable"] = True
            except errors:
                provider["reachable"] = False
                report["diagnostics"].append("owner external status did not confirm the referenced card and kind")
    report["ok"] = provider["reachable"] is True and provider["advertised_contract"] is True
    return report


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
