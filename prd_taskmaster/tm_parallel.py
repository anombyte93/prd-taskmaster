"""Native TaskMaster parallel expansion through isolated workdirs.

TaskMaster writes project state during `expand`, so this module parallelizes by
creating one tiny TaskMaster project per task, running native expansion inside
those isolated directories, then harvesting only subtasks back through
parallel.apply_results().
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prd_taskmaster import parallel
from prd_taskmaster.economy import economy_profile, shift_tier
from prd_taskmaster.fleet import load_fleet_config, resolve_backend
from prd_taskmaster.lib import CommandError, atomic_write, emit, fail
from prd_taskmaster.taskmaster import _find_binary


TASKMASTER_MIN_VERSION = "0.43.0"
TM_WORK = Path(".atlas-ai") / "tmwork"
TELEMETRY = Path(".atlas-ai") / "telemetry.jsonl"

# These vendor IDs rot. Refresh this map when telemetry or MODEL-ECONOMY.md
# shows the model ladder has changed.
TIER_MODEL_IDS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
}

_CLI_PROVIDERS = {"claude-code", "codex-cli"}
_TELEMETRY_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, indent=2, default=str) + "\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{os.getpid()}"


def _parse_version(text: str | None) -> tuple[int, int, int]:
    if not text:
        return (0, 0, 0)
    match = re.search(r"\d+\.\d+\.\d+", text)
    if not match:
        return (0, 0, 0)
    parts = match.group(0).split(".")
    return tuple(int(part) for part in parts[:3])  # type: ignore[return-value]


def _detect_binary_version(binary: str) -> str | None:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    text = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"\d+\.\d+\.\d+", text)
    return match.group(0) if match else result.stdout.strip().splitlines()[-1]


def _version_gate() -> dict:
    binary = _find_binary()
    if not binary:
        return {
            "ok": False,
            "error": "task-master binary not found in PATH",
            "minimum_version": TASKMASTER_MIN_VERSION,
            "fallback": "Use python3 script.py parallel-plan --missing-only, then parallel-apply.",
        }
    detected = _detect_binary_version(binary)
    if _parse_version(detected) < _parse_version(TASKMASTER_MIN_VERSION):
        return {
            "ok": False,
            "error": f"task-master >= {TASKMASTER_MIN_VERSION} required for native parallel expansion",
            "detected_version": detected,
            "minimum_version": TASKMASTER_MIN_VERSION,
            "fallback": "Use python3 script.py parallel-plan --missing-only, then parallel-apply.",
        }
    return {"ok": True, "binary": binary, "detected_version": detected}


def _load_tasks(tag: str | None) -> tuple[str, Any, str | None, list[dict]]:
    resolved = parallel.current_tag(tag)
    raw, tag_key = parallel.load_tagged(resolved)
    return resolved, raw, tag_key, parallel.get_tasks(raw, tag_key)


def _task_id(task: dict) -> Any:
    return task.get("id")


def _purge_old_runs() -> None:
    if not TM_WORK.is_dir():
        return
    cutoff = time.time() - 24 * 60 * 60
    for child in TM_WORK.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
        except OSError:
            continue


def _copy_state(project_root: Path, workdir: Path, tag: str) -> None:
    src = project_root / ".taskmaster" / "state.json"
    state = {"currentTag": tag}
    if src.is_file():
        try:
            loaded = _read_json(src)
            if isinstance(loaded, dict):
                state = loaded
        except (json.JSONDecodeError, OSError):
            state = {"currentTag": tag}
    state["currentTag"] = tag
    _write_json(workdir / ".taskmaster" / "state.json", state)


def _copy_prd(project_root: Path, workdir: Path) -> None:
    src = project_root / ".taskmaster" / "docs" / "prd.md"
    if src.is_file():
        dst = workdir / ".taskmaster" / "docs" / "prd.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _model_config_for_tier(
    config: dict,
    fleet_config: dict,
    tier: str,
) -> tuple[dict, str, str | None, str]:
    target = resolve_backend(tier, fleet_config)
    models = config.get("models") if isinstance(config.get("models"), dict) else {}
    current = models.get("main") if isinstance(models.get("main"), dict) else {}
    current = dict(current)
    provider = str(current.get("provider", "")).lower()

    if ":" not in target:
        return current, str(current.get("modelId", "")), f"unparseable routing target preserved: {target}", target

    backend, model = target.split(":", 1)
    if backend == "claude":
        if provider in _CLI_PROVIDERS:
            current["modelId"] = model
            return current, model, None, target
        full_id = TIER_MODEL_IDS.get(model, model)
        return {
            "provider": "anthropic",
            "modelId": full_id,
            "maxTokens": current.get("maxTokens", 64000),
            "temperature": current.get("temperature", 0.2),
        }, full_id, None, target

    return (
        current,
        str(current.get("modelId", "")),
        f"non-claude routing target preserved existing provider: {target}",
        target,
    )


def _write_workdir_config(
    project_root: Path,
    workdir: Path,
    fleet_config: dict,
    tier: str,
) -> tuple[str, str | None, str]:
    src = project_root / ".taskmaster" / "config.json"
    config: dict = {}
    if src.is_file():
        try:
            loaded = _read_json(src)
            if isinstance(loaded, dict):
                config = loaded
        except (json.JSONDecodeError, OSError):
            config = {}
    models = config.setdefault("models", {})
    main, model_id, note, target = _model_config_for_tier(config, fleet_config, tier)
    models["main"] = main
    _write_json(workdir / ".taskmaster" / "config.json", config)
    return model_id, note, target


def _rewrite_workdir_model(workdir: Path, fleet_config: dict, tier: str) -> tuple[str, str | None, str]:
    config_path = workdir / ".taskmaster" / "config.json"
    config = _read_json(config_path) if config_path.is_file() else {"models": {}}
    if not isinstance(config, dict):
        config = {"models": {}}
    config.setdefault("models", {})
    main, model_id, note, target = _model_config_for_tier(config, fleet_config, tier)
    config["models"]["main"] = main
    _write_json(config_path, config)
    return model_id, note, target


def _write_workdir_task(workdir: Path, tag: str, task: dict) -> None:
    task_copy = copy.deepcopy(task)
    task_copy["dependencies"] = []
    payload = {tag: {"tasks": [task_copy]}}
    _write_json(workdir / ".taskmaster" / "tasks" / "tasks.json", payload)


def _write_manifest(run_root: Path, manifest: dict) -> None:
    _write_json(run_root / "manifest.json", manifest)


def _read_manifest(run_id: str) -> dict:
    path = TM_WORK / run_id / "manifest.json"
    if not path.is_file():
        raise CommandError(f"tm-parallel run not found: {run_id}", {"run_id": run_id})
    manifest = _read_json(path)
    if not isinstance(manifest, dict):
        raise CommandError(f"tm-parallel manifest invalid: {run_id}", {"run_id": run_id})
    return manifest


def _read_run_results(run_id: str) -> dict:
    path = TM_WORK / run_id / "results.json"
    if not path.is_file():
        raise CommandError(f"tm-parallel results not found: {run_id}", {"run_id": run_id})
    results = _read_json(path)
    if not isinstance(results, dict):
        raise CommandError(f"tm-parallel results invalid: {run_id}", {"run_id": run_id})
    return results


def _pending_reason(task: dict, missing_only: bool) -> str | None:
    status = str(task.get("status", "pending"))
    if status != "pending":
        return f"status_{status}"
    if missing_only and len(task.get("subtasks") or []) >= 2:
        return "already_has_subtasks"
    return None


def run_tm_plan(tag: str | None = None, missing_only: bool = True) -> dict:
    """Create isolated TaskMaster workdirs for native expansion."""
    project_root = Path.cwd()
    resolved_tag, _raw, _tag_key, tasks = _load_tasks(tag)
    _purge_old_runs()

    run_id = _run_id()
    run_root = TM_WORK / run_id
    fleet_config = load_fleet_config()
    profile = economy_profile(fleet_config)
    start_tier = profile.get("structured_gen_start", "standard")
    workdirs: list[dict] = []
    skipped: list[dict] = []

    for task in tasks:
        task_id = _task_id(task)
        reason = _pending_reason(task, missing_only)
        if reason:
            skipped.append({"task_id": task_id, "reason": reason})
            continue

        workdir = run_root / f"task-{task_id}"
        _write_workdir_task(workdir, resolved_tag, task)
        _copy_state(project_root, workdir, resolved_tag)
        model_id, note, target = _write_workdir_config(project_root, workdir, fleet_config, start_tier)
        _copy_prd(project_root, workdir)
        item = {
            "task_id": task_id,
            "path": str(workdir.resolve()),
            "model": model_id,
            "tier": start_tier,
            "routing_target": target,
        }
        if note:
            item["note"] = note
        workdirs.append(item)

    manifest = {
        "ok": True,
        "run_id": run_id,
        "tag": resolved_tag,
        "created_at": _now_iso(),
        "workdirs": workdirs,
        "skipped": skipped,
    }
    _write_manifest(run_root, manifest)
    return {"ok": True, "run_id": run_id, "workdirs": workdirs, "skipped": skipped}


def _default_concurrency(concurrency: int | None, workdir_count: int, fleet_config: dict, profile: dict) -> int:
    if workdir_count <= 0:
        return 0
    if concurrency is not None:
        if concurrency < 1:
            raise CommandError("concurrency must be >= 1")
        return min(concurrency, workdir_count)
    setting = profile.get("tm_concurrency", "max")
    if setting == "min2":
        return min(2, workdir_count)
    if setting == "max":
        max_config = fleet_config.get("max_concurrency", 3)
        return min(max_config if isinstance(max_config, int) and max_config >= 1 else 3, workdir_count)
    if isinstance(setting, int) and setting >= 1:
        return min(setting, workdir_count)
    return min(3, workdir_count)


def _append_telemetry(row: dict) -> None:
    TELEMETRY.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, default=str) + "\n"
    with _TELEMETRY_LOCK:
        with TELEMETRY.open("a") as f:
            f.write(line)


def _run_one_attempt(binary: str, task_id: Any, workdir: Path, timeout: float) -> tuple[Any, int, str, str]:
    start = time.monotonic()
    try:
        result = subprocess.run(
            [binary, "expand", "--id", str(task_id), "--research", "--force"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        wall_ms = int((time.monotonic() - start) * 1000)
        return result.returncode, wall_ms, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        wall_ms = int((time.monotonic() - start) * 1000)
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return "timeout", wall_ms, stdout, stderr


def _run_packet(binary: str, item: dict, timeout: float, fleet_config: dict, profile: dict) -> dict:
    task_id = item["task_id"]
    workdir = Path(item["path"])
    tier = item.get("tier", profile.get("structured_gen_start", "standard"))
    model = item.get("model", "")
    escalation = profile.get("escalation", {})
    can_escalate = escalation.get("enabled", True) and escalation.get("max_steps", 1) >= 1
    attempts = []

    for attempt in (0, 1):
        escalated = attempt > 0
        if escalated:
            tier = shift_tier(tier, 1, ceiling=escalation.get("ceiling"))
            model, note, target = _rewrite_workdir_model(workdir, fleet_config, tier)
            item["tier"] = tier
            item["model"] = model
            item["routing_target"] = target
            if note:
                item["note"] = note
        exit_code, wall_ms, stdout, stderr = _run_one_attempt(binary, task_id, workdir, timeout)
        _append_telemetry({
            "ts": _now_iso(),
            "op_class": "structured_gen",
            "task_id": task_id,
            "model": model,
            "backend": "taskmaster-api",
            "exit": exit_code,
            "wall_ms": wall_ms,
            "escalated": escalated,
        })
        attempts.append({
            "attempt": attempt,
            "exit": exit_code,
            "wall_ms": wall_ms,
            "model": model,
            "stdout": stdout,
            "stderr": stderr,
        })
        if exit_code == 0:
            return {
                "task_id": task_id,
                "exit": 0,
                "wall_ms": sum(a["wall_ms"] for a in attempts),
                "attempts": len(attempts),
                "path": str(workdir),
                "model": model,
                "success": True,
            }
        if not can_escalate or attempt == 1:
            break

    return {
        "task_id": task_id,
        "exit": attempts[-1]["exit"],
        "wall_ms": sum(a["wall_ms"] for a in attempts),
        "attempts": len(attempts),
        "path": str(workdir),
        "model": model,
        "success": False,
    }


def run_tm_run(run_id: str, concurrency: int | None = None, timeout: float = 180) -> dict:
    """Run native TaskMaster expansion for all workdirs in a run."""
    manifest = _read_manifest(run_id)
    workdirs = list(manifest.get("workdirs") or [])
    if not workdirs:
        result = {"ok": True, "run_id": run_id, "results": [], "failed": []}
        _write_json(TM_WORK / run_id / "results.json", result)
        return result

    binary = _find_binary()
    if not binary:
        raise CommandError("task-master binary not found in PATH")

    fleet_config = load_fleet_config()
    profile = economy_profile(fleet_config)
    workers = _default_concurrency(concurrency, len(workdirs), fleet_config, profile)
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_run_packet, binary, item, timeout, fleet_config, profile)
            for item in workdirs
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item["task_id"])
    failed = [item["task_id"] for item in results if not item.get("success")]
    result = {"ok": not failed, "run_id": run_id, "results": results, "failed": failed}
    manifest["workdirs"] = workdirs
    _write_manifest(TM_WORK / run_id, manifest)
    _write_json(TM_WORK / run_id / "results.json", result)
    return result


def _complexity_from_report(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = _read_json(path)
    except (json.JSONDecodeError, OSError):
        return {}
    items = raw.get("complexityAnalysis") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {}
    result = {}
    for item in items:
        if isinstance(item, dict) and "taskId" in item:
            result[item["taskId"]] = item
    return result


def _load_complexity(tag: str) -> dict:
    reports = Path(".taskmaster") / "reports"
    if not reports.is_dir():
        return {}
    merged: dict = {}
    generic = reports / "task-complexity-report.json"
    merged.update(_complexity_from_report(generic))
    if tag and tag != "master":
        merged.update(_complexity_from_report(reports / f"task-complexity-report_{tag}.json"))
    for path in sorted(reports.glob("task-complexity-report*.json")):
        if path not in {generic, reports / f"task-complexity-report_{tag}.json"}:
            for task_id, item in _complexity_from_report(path).items():
                merged.setdefault(task_id, item)
    return merged


def _extract_subtasks(workdir: Path, tag: str) -> list[dict]:
    path = workdir / ".taskmaster" / "tasks" / "tasks.json"
    raw = _read_json(path)
    if isinstance(raw, dict) and tag in raw and isinstance(raw[tag], dict):
        tasks = raw[tag].get("tasks") or []
    elif isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
        tasks = raw.get("tasks") or []
    else:
        tasks = []
    if not tasks:
        return []
    task = tasks[0]
    return task.get("subtasks") or []


def run_tm_harvest(run_id: str, tag: str | None = None, threshold: int = 7) -> dict:
    """Harvest successful isolated expansions and merge once through apply_results."""
    manifest = _read_manifest(run_id)
    run_results = _read_run_results(run_id)
    resolved_tag = tag or manifest.get("tag") or parallel.current_tag(None)
    successful = {item["task_id"]: item for item in run_results.get("results", []) if item.get("success")}
    failed = list(run_results.get("failed") or [])
    complexity = _load_complexity(resolved_tag)
    by_task = {item["task_id"]: item for item in manifest.get("workdirs") or []}
    harvested: list[dict] = []
    retained: list[str] = []

    for task_id, item in by_task.items():
        workdir = Path(item["path"])
        if task_id not in successful:
            if workdir.exists():
                retained.append(str(workdir))
            continue
        subtasks = _extract_subtasks(workdir, resolved_tag)
        c = complexity.get(task_id, {})
        harvested.append({
            "id": task_id,
            "complexityScore": c.get("complexityScore"),
            "recommendedSubtasks": c.get("recommendedSubtasks"),
            "reasoning": c.get("reasoning", ""),
            "researchNotes": "",
            "subtasks": subtasks,
        })

    if harvested:
        result = parallel.apply_results(harvested, tag=resolved_tag, threshold=threshold)
    else:
        result = {
            "ok": False,
            "tag": resolved_tag,
            "applied": [],
            "report": None,
            "needs_more_subtasks": [],
        }

    for task_id in successful:
        workdir = Path(by_task[task_id]["path"])
        if workdir.exists():
            shutil.rmtree(workdir)

    run_root = TM_WORK / run_id
    if failed:
        retained = [str(Path(by_task[task_id]["path"])) for task_id in failed if task_id in by_task and Path(by_task[task_id]["path"]).exists()]
    elif run_root.exists():
        shutil.rmtree(run_root)

    result.update({"run_id": run_id, "failed": failed, "retained_workdirs": retained})
    return result


def run_tm_parallel(
    tag: str | None = None,
    missing_only: bool = True,
    concurrency: int | None = None,
    timeout: float = 180,
    dry_run: bool = False,
) -> dict:
    """Plan, run, and harvest native TaskMaster expansion."""
    gate = _version_gate()
    if not gate.get("ok"):
        return gate
    plan = run_tm_plan(tag=tag, missing_only=missing_only)
    if dry_run:
        return {**plan, "dry_run": True}
    run = run_tm_run(plan["run_id"], concurrency=concurrency, timeout=timeout)
    harvest = run_tm_harvest(plan["run_id"], tag=tag)
    harvest["run"] = run
    return harvest


def _emit_result(result: dict) -> None:
    emit(result)


def cmd_tm_plan(args: argparse.Namespace) -> None:
    try:
        _emit_result(run_tm_plan(tag=args.tag, missing_only=args.missing_only))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def cmd_tm_run(args: argparse.Namespace) -> None:
    try:
        _emit_result(run_tm_run(args.run_id, concurrency=args.concurrency, timeout=args.timeout))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def cmd_tm_harvest(args: argparse.Namespace) -> None:
    try:
        _emit_result(run_tm_harvest(args.run_id, tag=args.tag, threshold=args.threshold))
    except CommandError as exc:
        fail(exc.message, **exc.extra)


def cmd_tm_parallel(args: argparse.Namespace) -> None:
    try:
        _emit_result(
            run_tm_parallel(
                tag=args.tag,
                missing_only=args.missing_only,
                concurrency=args.concurrency,
                timeout=args.timeout,
                dry_run=args.dry_run,
            )
        )
    except CommandError as exc:
        fail(exc.message, **exc.extra)
