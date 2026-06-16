"""Backend abstraction for Atlas task generation and rating."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import prd_taskmaster
from prd_taskmaster import fleet, llm_client, parallel, taskmaster, tm_parallel
from prd_taskmaster.economy import append_telemetry, economy_profile, shift_tier
from prd_taskmaster.lib import CommandError, _detect_taskmaster_method, now_iso
from prd_taskmaster.validation import run_validate_tasks


class Backend(Protocol):
    name: str

    def detect(self) -> dict: ...
    def init_project(self) -> dict: ...
    def parse_prd(self, prd_path, num_tasks, tag=None) -> dict: ...
    def expand(self, task_ids=None, research=True, tag=None) -> dict: ...
    def rate(self, tag=None, research=True) -> dict: ...


_FACTORY_TOKEN = object()


TASKS_SCHEMA_HINT = """{
  "tasks": [
    {
      "id": 1,
      "title": "Concrete task title",
      "description": "One-sentence outcome",
      "details": "Implementation notes, files, constraints, and acceptance expectations.",
      "testStrategy": "Exact verification command or evidence requirement.",
      "status": "pending",
      "dependencies": [],
      "priority": "high",
      "tier": "domain-model",
      "subtasks": [
        {
          "id": 1,
          "title": "Concrete checkpoint",
          "description": "Verifiable subtask outcome",
          "status": "pending",
          "dependencies": []
        },
        {
          "id": 2,
          "title": "Second concrete checkpoint",
          "description": "Another verifiable subtask outcome",
          "status": "pending",
          "dependencies": [1]
        }
      ]
    }
  ]
}

Rules: generate exactly the requested task count unless the PRD is smaller; every
task must include id, title, description, details, testStrategy, status,
dependencies, priority, and at least 2 subtasks; dependencies must reference
existing task or sibling subtask IDs; use only priority high, medium, or low;
do not include placeholders, generic tasks, or empty testStrategy fields;
tier ∈ {spike|domain-model|wired|live}: the altitude of the claim — spike=research,
domain-model=pure logic, wired=integration, live=user-visible; wired/live require
reachability evidence (the deterministic enrich step will set this if omitted)."""


PARALLEL_RESULT_SCHEMA_HINT = """{
  "id": "<task id>",
  "complexityScore": 1,
  "recommendedSubtasks": 3,
  "reasoning": "Why this score and decomposition fit the task.",
  "researchNotes": "Concise research findings or empty string.",
  "subtasks": [
    {
      "title": "Concrete checkpoint",
      "description": "Verifiable subtask outcome",
      "details": "Implementation and verification notes.",
      "dependencies": []
    }
  ]
}

Rules: return one JSON object for the packet task; complexityScore must be 1-10;
recommendedSubtasks should be 3-7; subtasks must be TDD-ordered checkpoints."""


COMPLEXITY_REPORT_SCHEMA_HINT = """{
  "complexityAnalysis": [
    {
      "taskId": 1,
      "taskTitle": "Task title",
      "complexityScore": 5,
      "recommendedSubtasks": 3,
      "expansionPrompt": "Prompt to expand this task.",
      "reasoning": "Why the score and recommended subtask count fit."
    }
  ]
}

Rules: return a TaskMaster-compatible complexity report object; score every task
from 1-10 and include one item per provided task summary."""


NATIVE_PARSE_STEPS = [
    "write .taskmaster/tasks/tasks.json in the Native Mode shape",
    "ensure every task has at least 2 subtasks",
    "run validate-tasks with empty subtasks disallowed",
    "write the validated tasks into the requested tag",
]


COMPLEXITY_SCORING_RUBRIC = (
    "Score 1-4 for straightforward implementation, 5-7 for multi-file or "
    "integration work, 8-10 for architecture, migration, security, concurrency, "
    "or high-risk work. Recommend 3-7 subtasks, with higher counts for higher scores."
)


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


def _candidate_tasks(candidate: Any) -> list[dict]:
    if isinstance(candidate, list):
        return candidate
    if isinstance(candidate, dict):
        tasks = candidate.get("tasks")
        if isinstance(tasks, list):
            return tasks
        for value in candidate.values():
            if isinstance(value, dict) and isinstance(value.get("tasks"), list):
                return value["tasks"]
    raise CommandError("generated tasks payload must contain a tasks list")


def _validate_task_candidate(candidate: Any) -> tuple[list[dict], dict]:
    tasks = _candidate_tasks(candidate)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tasks.json"
        path.write_text(json.dumps({"tasks": tasks}, indent=2, default=str))
        validation = run_validate_tasks(
            str(path),
            allow_empty_subtasks=False,
            require_phase_config=False,
        )
    return tasks, validation


def _load_existing_tagged() -> dict:
    if not parallel.TASKS.is_file():
        return {}
    try:
        raw = json.loads(parallel.TASKS.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict) or isinstance(raw.get("tasks"), list):
        return {}
    return raw


def _write_tasks_into_tag(tasks: list[dict], tag: str | None) -> str:
    resolved = parallel.current_tag(tag)
    raw = _load_existing_tagged()
    raw[resolved] = {"tasks": tasks}
    parallel.TASKS.parent.mkdir(parents=True, exist_ok=True)
    parallel.write_atomic(parallel.TASKS, raw)
    return resolved


def _native_concurrency(work_count: int, fleet_config: dict, profile: dict) -> int:
    if work_count <= 0:
        return 0
    setting = profile.get("tm_concurrency", "max")
    if setting == "min2":
        return min(2, work_count)
    if setting == "max":
        max_config = fleet_config.get("max_concurrency", 3)
        return min(max_config if isinstance(max_config, int) and max_config >= 1 else 3, work_count)
    if isinstance(setting, int) and setting >= 1:
        return min(setting, work_count)
    return min(3, work_count)


def _task_summaries(tasks: list[dict]) -> list[dict]:
    summaries = []
    for task in tasks:
        summaries.append({
            "id": task.get("id"),
            "title": task.get("title", ""),
            "description": task.get("description", ""),
            "details": task.get("details", ""),
            "testStrategy": task.get("testStrategy", ""),
            "priority": task.get("priority", ""),
            "dependencies": task.get("dependencies") or [],
            "status": task.get("status", "pending"),
            "subtask_count": len(task.get("subtasks") or []),
        })
    return summaries


def _complexity_report_path(tag: str) -> Path:
    suffix = "" if tag in ("master", None) else f"_{tag}"
    return Path(".taskmaster") / "reports" / f"task-complexity-report{suffix}.json"


def _agent_parse_action(prd_path: Any, num_tasks: int, tag: str | None) -> dict:
    return {
        "op": "parse_prd",
        "prd_path": str(prd_path),
        "num_tasks": num_tasks,
        "tag": tag,
        "schema_hint": TASKS_SCHEMA_HINT,
        "then": NATIVE_PARSE_STEPS,
    }


def _agent_expand_action(
    tag: str | None,
    task_ids: Any,
    packets: list[dict],
) -> dict:
    return {
        "op": "expand",
        "tag": tag,
        "task_ids": task_ids,
        "packets": packets,
        "schema_hint": PARALLEL_RESULT_SCHEMA_HINT,
        "hint": "run context-pack on the files a task touches before generating code",
        "then": ["spawn research subagents", "parallel-apply --input results.json"],
    }


def _agent_rate_action(tag: str | None, summaries: list[dict]) -> dict:
    return {
        "op": "rate",
        "tag": tag,
        "task_summaries": summaries,
        "schema_hint": COMPLEXITY_REPORT_SCHEMA_HINT,
        "scoring_rubric": COMPLEXITY_SCORING_RUBRIC,
        "then": ["write the TaskMaster-format complexity report"],
    }


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


class NativeBackend(Backend):
    name = "native"

    def detect(self) -> dict:
        creds = llm_client.discover_key()
        return {
            "name": "native",
            "available": True,
            "version": prd_taskmaster.__version__,
            "ai_ops": "api" if creds else "agent",
            "api_provider": creds.get("provider") if creds else None,
        }

    def init_project(self) -> dict:
        root = Path(".taskmaster")
        for child in ("docs", "tasks", "reports"):
            (root / child).mkdir(parents=True, exist_ok=True)

        state = root / "state.json"
        config = root / "config.json"
        tasks = root / "tasks" / "tasks.json"
        created = []

        if not state.exists():
            parallel.write_atomic(state, {"currentTag": "master"})
            created.append(str(state))
        if not config.exists():
            parallel.write_atomic(config, {"models": {}, "global": {"defaultTag": "master"}})
            created.append(str(config))
        if not tasks.exists():
            parallel.write_atomic(tasks, {"master": {"tasks": []}})
            created.append(str(tasks))

        return {
            "ok": True,
            "backend": "native",
            "root": str(root),
            "created": created,
        }

    def parse_prd(self, prd_path, num_tasks, tag=None) -> dict:
        if not llm_client.discover_key():
            return {
                "ok": False,
                "agent_action_required": _agent_parse_action(prd_path, num_tasks, tag),
            }

        path = Path(prd_path)
        try:
            prd_text = path.read_text()
        except OSError as exc:
            return {"ok": False, "error": f"failed to read PRD: {exc}", "prd_path": str(path)}

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        tier = profile.get("structured_gen_start", "standard")
        prompt = (
            f"Parse this PRD into exactly {num_tasks} TaskMaster-compatible tasks.\n"
            f"Target tag: {tag or parallel.current_tag(None)}.\n"
            "Return only the tasks JSON object.\n\n"
            f"PRD PATH: {path}\n"
            f"PRD:\n{prd_text}"
        )
        system = (
            "You are the prd-taskmaster native backend. Generate strict JSON for "
            "the Native Mode tasks.json path."
        )

        try:
            generated = llm_client.generate_json(
                prompt,
                system=system,
                schema_hint=TASKS_SCHEMA_HINT,
                tier=tier,
                op_class="structured_gen",
                return_telemetry_ref=True,
            )
        except llm_client.LLMError as exc:
            if exc.kind == "no_key":
                return {
                    "ok": False,
                    "agent_action_required": _agent_parse_action(prd_path, num_tasks, tag),
                }
            return {"ok": False, "error": str(exc), "kind": exc.kind, "backend": "native"}

        telemetry_ref = None
        if isinstance(generated, tuple) and len(generated) == 2:
            candidate, telemetry_ref = generated
        else:
            candidate = generated

        try:
            tasks, validation = _validate_task_candidate(candidate)
        except CommandError as exc:
            result = {"ok": False, "error": exc.message, "backend": "native"}
            result.update(exc.extra)
            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        try:
            resolved = _write_tasks_into_tag(tasks, tag)
        except Exception as exc:
            return {"ok": False, "error": f"failed to write tasks: {exc}", "backend": "native"}

        result = {
            "ok": True,
            "task_count": len(tasks),
            "tag": resolved,
            "backend": "native",
            "ai": "api",
            "validation": validation,
        }
        if telemetry_ref is not None:
            result["telemetry_ref"] = telemetry_ref
        return result

    def expand(self, task_ids=None, research=True, tag=None) -> dict:
        try:
            resolved, pending = _pending_tasks(tag, task_ids)
            packets = parallel.build_packets(pending, missing_only=True)
        except SystemExit as exc:
            return {"ok": False, "error": f"failed to load tasks: {exc}", "backend": "native"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        if not llm_client.discover_key():
            return {
                "ok": False,
                "tag": resolved,
                "agent_action_required": _agent_expand_action(resolved, task_ids, packets),
            }
        if not packets:
            return {"ok": True, "tag": resolved, "applied": [], "failed": [], "results": []}

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        workers = _native_concurrency(len(packets), config, profile)
        outcomes = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._expand_packet, packet, profile, research)
                for packet in packets
            ]
            for future in as_completed(futures):
                outcomes.append(future.result())

        outcomes.sort(key=lambda item: str(item.get("task_id")))
        results = [item["result"] for item in outcomes if item.get("ok")]
        failed = [item["task_id"] for item in outcomes if not item.get("ok")]

        if results:
            try:
                applied = parallel.apply_results(results, tag=resolved)
            except SystemExit as exc:
                return {"ok": False, "error": f"failed to apply results: {exc}", "backend": "native"}
            except Exception as exc:
                return {"ok": False, "error": str(exc), "backend": "native"}
        else:
            applied = {
                "ok": False,
                "tag": resolved,
                "applied": [],
                "report": None,
                "needs_more_subtasks": [],
            }

        return {
            **applied,
            "ok": bool(applied.get("ok")) and not failed,
            "failed": failed,
            "results": outcomes,
            "backend": "native",
            "ai": "api",
        }

    def _expand_packet(self, packet: dict, profile: dict, research: bool) -> dict:
        task_id = packet.get("id")
        start_tier = profile.get("structured_gen_start", "standard")
        prompt = packet.get("prompt", "")
        if not research:
            prompt += "\n\nDo not perform external research; decompose structurally from the task text."
        system = (
            "You are the prd-taskmaster native backend expansion engine. Return "
            "one strict JSON result object for parallel.apply_results."
        )

        try:
            result = llm_client.generate_json(
                prompt,
                system=system,
                schema_hint=PARALLEL_RESULT_SCHEMA_HINT,
                tier=start_tier,
                op_class="structured_gen",
                task_id=task_id,
            )
            return self._packet_success(packet, result, escalated=False)
        except llm_client.LLMError as exc:
            if exc.kind != "invalid_json":
                return {
                    "ok": False,
                    "task_id": task_id,
                    "error": str(exc),
                    "kind": exc.kind,
                    "escalated": False,
                }

        escalation = profile.get("escalation", {})
        if not escalation.get("enabled", True) or escalation.get("max_steps", 1) < 1:
            return {
                "ok": False,
                "task_id": task_id,
                "error": "invalid_json after retry",
                "kind": "invalid_json",
                "escalated": False,
            }

        tier = shift_tier(start_tier, 1, ceiling=escalation.get("ceiling"))
        start = time.monotonic()
        exit_code = 1
        error = None
        try:
            result = llm_client.generate_json(
                prompt,
                system=system,
                schema_hint=PARALLEL_RESULT_SCHEMA_HINT,
                tier=tier,
                op_class="structured_gen",
                task_id=task_id,
            )
            exit_code = 0
            return self._packet_success(packet, result, escalated=True)
        except llm_client.LLMError as exc:
            error = exc
            return {
                "ok": False,
                "task_id": task_id,
                "error": str(exc),
                "kind": exc.kind,
                "escalated": True,
            }
        finally:
            row = {
                "ts": now_iso(),
                "op_class": "structured_gen",
                "task_id": task_id,
                "model": tier,
                "backend": "native-api",
                "exit": exit_code,
                "wall_ms": int((time.monotonic() - start) * 1000),
                "escalated": True,
            }
            if error is not None:
                row["kind"] = error.kind
            append_telemetry(row)

    @staticmethod
    def _packet_success(packet: dict, result: Any, escalated: bool) -> dict:
        task_id = packet.get("id")
        if not isinstance(result, dict):
            return {
                "ok": False,
                "task_id": task_id,
                "error": "generated packet result must be an object",
                "kind": "invalid_result",
                "escalated": escalated,
            }
        result.setdefault("id", task_id)
        return {
            "ok": True,
            "task_id": result.get("id"),
            "result": result,
            "escalated": escalated,
        }

    def rate(self, tag=None, research=True) -> dict:
        try:
            resolved, tasks = _load_tasks(tag)
        except SystemExit as exc:
            return {"ok": False, "error": f"failed to load tasks: {exc}", "backend": "native"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        summaries = _task_summaries(tasks)
        if not llm_client.discover_key():
            return {
                "ok": False,
                "tag": resolved,
                "agent_action_required": _agent_rate_action(resolved, summaries),
            }

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        tier = profile.get("structured_gen_start", "standard")
        prompt = (
            "Score these TaskMaster tasks and return a TaskMaster-compatible "
            "complexity report.\n"
            f"Research enabled: {bool(research)}\n"
            f"Scoring rubric: {COMPLEXITY_SCORING_RUBRIC}\n\n"
            f"TASK SUMMARIES:\n{json.dumps(summaries, indent=2, default=str)}"
        )
        system = (
            "You are the prd-taskmaster native backend complexity engine. Return "
            "strict JSON in TaskMaster complexity report format."
        )
        try:
            candidate = llm_client.generate_json(
                prompt,
                system=system,
                schema_hint=COMPLEXITY_REPORT_SCHEMA_HINT,
                tier=tier,
                op_class="structured_gen",
            )
        except llm_client.LLMError as exc:
            if exc.kind == "no_key":
                return {
                    "ok": False,
                    "tag": resolved,
                    "agent_action_required": _agent_rate_action(resolved, summaries),
                }
            return {"ok": False, "error": str(exc), "kind": exc.kind, "backend": "native"}

        if isinstance(candidate, dict):
            analysis = candidate.get("complexityAnalysis")
        else:
            analysis = candidate
        if not isinstance(analysis, list):
            return {
                "ok": False,
                "error": "complexity report must contain complexityAnalysis list",
                "backend": "native",
            }

        report = {
            "meta": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "tasksAnalyzed": len(analysis),
                "thresholdScore": 7,
                "projectName": Path.cwd().name,
                "usedResearch": bool(research),
                "generatedBy": "prd-taskmaster/native-backend",
                "tag": resolved,
            },
            "complexityAnalysis": analysis,
        }
        report_path = _complexity_report_path(resolved)
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            parallel.write_atomic(report_path, report)
        except Exception as exc:
            return {"ok": False, "error": f"failed to write report: {exc}", "backend": "native"}

        return {
            "ok": True,
            "tag": resolved,
            "report": str(report_path),
            "complexityAnalysis": analysis,
            "raw": report,
            "backend": "native",
            "ai": "api",
        }


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
            d = {
                "ok": False,
                "task_count": 0,
                "exit": result.returncode,
                "stderr": result.stderr,
            }
            d.setdefault("backend", "taskmaster")
            d.setdefault("ai", "taskmaster-cli")
            return d
        _resolved, tasks = _load_tasks(tag)
        if not tasks:
            # P1-1: a 0-exit parse that produced no tasks is NOT success — it is the
            # silent failure that lets the pipeline treat an empty graph as "done".
            d = {
                "ok": False,
                "task_count": 0,
                "exit": result.returncode,
                "error": (
                    "parse-prd exited 0 but produced 0 tasks — the model returned no "
                    "tasks. Check provider credentials (run: python3 script.py "
                    "configure-providers) and the PRD content."
                ),
            }
            d.setdefault("backend", "taskmaster")
            d.setdefault("ai", "taskmaster-cli")
            return d
        d = {"ok": True, "task_count": len(tasks)}
        d.setdefault("backend", "taskmaster")
        d.setdefault("ai", "taskmaster-cli")
        return d

    def expand(self, task_ids=None, research=True, tag=None) -> dict:
        resolved, pending = _pending_tasks(tag, task_ids)
        if len(pending) > 3:
            res = tm_parallel.run_tm_parallel(tag=tag)
            d = dict(res)
            d.setdefault("backend", "taskmaster")
            d.setdefault("ai", "taskmaster-cli")
            return d
        if not pending:
            d = {"ok": True, "tag": resolved, "expanded": [], "failed": [], "results": []}
            d.setdefault("backend", "taskmaster")
            d.setdefault("ai", "taskmaster-cli")
            return d

        binary = _binary_or_raise()
        results = []
        expanded = []
        failed = []
        any_degraded = False
        for task in pending:
            task_id = task.get("id")
            cmd = [binary, "expand", "--id", str(task_id)]
            if research:
                cmd.append("--research")
            start = time.monotonic()
            result = subprocess.run(cmd, capture_output=True, text=True)
            wall_ms = int((time.monotonic() - start) * 1000)
            degraded = False
            if result.returncode != 0 and research:
                # P0-3: research provider down (quota/auth). Degrade to a structural
                # expand (no --research) — always available, still verifiable —
                # rather than hard-failing this task to 0 subtasks.
                s_start = time.monotonic()
                result = subprocess.run(
                    [binary, "expand", "--id", str(task_id)],
                    capture_output=True,
                    text=True,
                )
                wall_ms += int((time.monotonic() - s_start) * 1000)
                degraded = True
                any_degraded = True
            append_telemetry({
                "ts": now_iso(),
                "op_class": "structured_gen",
                "task_id": task_id,
                "model": "",
                "backend": "taskmaster-api",
                "exit": result.returncode,
                "wall_ms": wall_ms,
                "escalated": False,
                "degraded": degraded,
            })
            item = {
                "task_id": task_id,
                "exit": result.returncode,
                "wall_ms": wall_ms,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "degraded": degraded,
            }
            results.append(item)
            if result.returncode == 0:
                expanded.append(task_id)
            else:
                failed.append(task_id)
        d = {
            "ok": not failed,
            "tag": resolved,
            "expanded": expanded,
            "failed": failed,
            "results": results,
        }
        if any_degraded:
            d["degraded"] = True
        d.setdefault("backend", "taskmaster")
        d.setdefault("ai", "taskmaster-cli")
        return d

    def rate(self, tag=None, research=True) -> dict:
        binary = _binary_or_raise()
        cmd = [binary, "analyze-complexity"]
        if research:
            cmd.append("--research")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            d = {"ok": False, "exit": result.returncode, "stderr": result.stderr}
            d.setdefault("backend", "taskmaster")
            d.setdefault("ai", "taskmaster-cli")
            return d

        resolved = parallel.current_tag(tag)
        for path in _report_candidates(resolved):
            raw = _read_json(path)
            if raw is not None:
                d = {
                    "ok": True,
                    "tag": resolved,
                    "report": str(path),
                    "complexityAnalysis": raw.get("complexityAnalysis", []),
                    "raw": raw,
                }
                d.setdefault("backend", "taskmaster")
                d.setdefault("ai", "taskmaster-cli")
                return d
        d = {
            "ok": False,
            "tag": resolved,
            "report": None,
            "error": "task complexity report not found",
        }
        d.setdefault("backend", "taskmaster")
        d.setdefault("ai", "taskmaster-cli")
        return d


def get_backend(cfg=None) -> Backend:
    config = fleet.load_fleet_config() if cfg is None else cfg
    backend = config.get("backend", "auto") if isinstance(config, dict) else "auto"

    if backend == "taskmaster":
        return TaskMasterBackend(_FACTORY_TOKEN)
    if backend == "native":
        return NativeBackend()

    taskmaster_backend = TaskMasterBackend(_FACTORY_TOKEN)
    if taskmaster_backend.detect().get("available"):
        return taskmaster_backend
    return NativeBackend()
