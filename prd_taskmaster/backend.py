"""Backend abstraction for Atlas task generation and rating."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol

from prd_taskmaster import fleet, parallel, taskmaster, tm_parallel
from prd_taskmaster.economy import append_telemetry
from prd_taskmaster.lib import CommandError, _detect_taskmaster_method, now_iso


class Backend(Protocol):
    name: str

    def detect(self) -> dict: ...
    def init_project(self) -> dict: ...
    def parse_prd(self, prd_path, num_tasks, tag=None) -> dict: ...
    def expand(self, task_ids=None, research=True, tag=None) -> dict: ...
    def rate(self, tag=None, research=True) -> dict: ...


_FACTORY_TOKEN = object()


def _task_id_set(task_ids: Any) -> set[str] | None:
    if task_ids is None:
        return None
    if isinstance(task_ids, (str, int)):
        return {str(task_ids)}
    return {str(task_id) for task_id in task_ids}


def _load_tasks(tag: str | None) -> tuple[str, list[dict]]:
    resolved = parallel.current_tag(tag)
    raw, tag_key = parallel.load_tagged(resolved)
    return resolved, parallel.get_tasks(raw, tag_key)


def _pending_tasks(tag: str | None, task_ids: Any = None) -> tuple[str, list[dict]]:
    resolved, tasks = _load_tasks(tag)
    wanted = _task_id_set(task_ids)
    pending = []
    for task in tasks:
        task_id = task.get("id")
        if wanted is not None and str(task_id) not in wanted:
            continue
        if str(task.get("status", "pending")) == "pending":
            pending.append(task)
    return resolved, pending


def _binary_or_raise() -> str:
    binary = taskmaster._find_binary()
    if not binary:
        raise CommandError("task-master binary not found in PATH")
    return binary


def _read_json(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def _report_candidates(tag: str | None) -> list[Path]:
    reports = Path(".taskmaster") / "reports"
    generic = reports / "task-complexity-report.json"
    tagged = reports / f"task-complexity-report_{tag}.json" if tag and tag != "master" else None
    paths = []
    if tagged is not None:
        paths.append(tagged)
    paths.append(generic)
    if reports.is_dir():
        seen = set(paths)
        for path in sorted(reports.glob("task-complexity-report*.json")):
            if path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


class TaskMasterBackend(Backend):
    name = "taskmaster"

    def __init__(self, _factory_token: object | None = None) -> None:
        if _factory_token is not _FACTORY_TOKEN:
            raise CommandError("TaskMasterBackend must be constructed through get_backend")

    def detect(self) -> dict:
        detected = _detect_taskmaster_method()
        gate = tm_parallel._version_gate()
        missing: list[str] = []

        def add_missing(message: object) -> None:
            if message and str(message) not in missing:
                missing.append(str(message))

        if detected.get("method") == "none":
            add_missing("task-master binary not found in PATH")
        if not gate.get("ok"):
            add_missing(gate.get("error"))

        available = bool(gate.get("ok"))
        return {
            "name": "taskmaster",
            "available": available,
            "version": gate.get("detected_version") or detected.get("version"),
            "ai_ops": available,
            "missing": missing,
        }

    def init_project(self) -> dict:
        return taskmaster.init_taskmaster()

    def parse_prd(self, prd_path, num_tasks, tag=None) -> dict:
        binary = _binary_or_raise()
        result = subprocess.run(
            [binary, "parse-prd", "--input", str(prd_path), "--num-tasks", str(num_tasks)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "task_count": 0,
                "exit": result.returncode,
                "stderr": result.stderr,
            }
        _resolved, tasks = _load_tasks(tag)
        return {"ok": True, "task_count": len(tasks)}

    def expand(self, task_ids=None, research=True, tag=None) -> dict:
        resolved, pending = _pending_tasks(tag, task_ids)
        if len(pending) > 3:
            return tm_parallel.run_tm_parallel(tag=tag)
        if not pending:
            return {"ok": True, "tag": resolved, "expanded": [], "failed": [], "results": []}

        binary = _binary_or_raise()
        results = []
        expanded = []
        failed = []
        for task in pending:
            task_id = task.get("id")
            cmd = [binary, "expand", "--id", str(task_id)]
            if research:
                cmd.append("--research")
            start = time.monotonic()
            result = subprocess.run(cmd, capture_output=True, text=True)
            wall_ms = int((time.monotonic() - start) * 1000)
            append_telemetry({
                "ts": now_iso(),
                "op_class": "structured_gen",
                "task_id": task_id,
                "model": "",
                "backend": "taskmaster-api",
                "exit": result.returncode,
                "wall_ms": wall_ms,
                "escalated": False,
            })
            item = {
                "task_id": task_id,
                "exit": result.returncode,
                "wall_ms": wall_ms,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            results.append(item)
            if result.returncode == 0:
                expanded.append(task_id)
            else:
                failed.append(task_id)
        return {
            "ok": not failed,
            "tag": resolved,
            "expanded": expanded,
            "failed": failed,
            "results": results,
        }

    def rate(self, tag=None, research=True) -> dict:
        binary = _binary_or_raise()
        cmd = [binary, "analyze-complexity"]
        if research:
            cmd.append("--research")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"ok": False, "exit": result.returncode, "stderr": result.stderr}

        resolved = parallel.current_tag(tag)
        for path in _report_candidates(resolved):
            raw = _read_json(path)
            if raw is not None:
                return {
                    "ok": True,
                    "tag": resolved,
                    "report": str(path),
                    "complexityAnalysis": raw.get("complexityAnalysis", []),
                    "raw": raw,
                }
        return {
            "ok": False,
            "tag": resolved,
            "report": None,
            "error": "task complexity report not found",
        }


def get_backend(cfg=None) -> Backend:
    config = fleet.load_fleet_config() if cfg is None else cfg
    backend = config.get("backend", "auto") if isinstance(config, dict) else "auto"

    if backend == "taskmaster":
        return TaskMasterBackend(_FACTORY_TOKEN)
    if backend == "native":
        raise CommandError("native backend lands in T4")

    taskmaster_backend = TaskMasterBackend(_FACTORY_TOKEN)
    if taskmaster_backend.detect().get("available"):
        return taskmaster_backend
    raise CommandError("native backend lands in T4")
