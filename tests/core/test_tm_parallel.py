"""Tests for native TaskMaster expansion through isolated workdirs."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script.py"


def _write_fake_taskmaster(bin_dir: Path, mode: str = "ok", version: str = "0.43.1") -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "task-master"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            if [ "$1" = "--version" ]; then
              echo "{version}"
              exit 0
            fi
            if [ "$1" = "expand" ]; then
              if [ "{mode}" = "slow" ]; then
                /bin/sleep 2
              fi
              if [ "{mode}" = "fail" ]; then
                echo "forced failure" >&2
                exit 1
              fi
              "{sys.executable}" - "$@" <<'PY'
import json
import sys
from pathlib import Path

args = sys.argv[1:]
task_id = None
for idx, arg in enumerate(args):
    if arg == "--id" and idx + 1 < len(args):
        task_id = int(args[idx + 1])
    elif arg.startswith("--id="):
        task_id = int(arg.split("=", 1)[1])
if task_id is None:
    raise SystemExit("missing --id")

path = Path(".taskmaster/tasks/tasks.json")
raw = json.loads(path.read_text())
tag, wrapper = next(iter(raw.items()))
task = next(t for t in wrapper["tasks"] if t["id"] == task_id)
task["subtasks"] = [
    {{"id": 1, "title": f"Task {{task_id}} first", "description": "one", "details": "alpha", "dependencies": []}},
    {{"id": 2, "title": f"Task {{task_id}} second", "description": "two", "details": "beta", "dependencies": [1]}},
]
path.write_text(json.dumps(raw, indent=2))
PY
              exit $?
            fi
            echo "unexpected command: $*" >&2
            exit 2
            """
        ).lstrip()
    )
    script.chmod(0o755)


def _seed_project(tmp_path: Path, provider: str = "claude-code") -> Path:
    tm = tmp_path / ".taskmaster"
    tasks_dir = tm / "tasks"
    docs_dir = tm / "docs"
    reports_dir = tm / "reports"
    tasks_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": "master"}))
    (tm / "config.json").write_text(
        json.dumps(
            {
                "models": {
                    "main": {
                        "provider": provider,
                        "modelId": "sonnet",
                        "maxTokens": 64000,
                        "temperature": 0.2,
                    },
                    "research": {"provider": "anthropic", "modelId": "sonnet"},
                },
                "global": {"defaultTag": "master"},
            },
            indent=2,
        )
    )
    (docs_dir / "prd.md").write_text("# PRD\n")
    (reports_dir / "task-complexity-report.json").write_text(
        json.dumps(
            {
                "complexityAnalysis": [
                    {"taskId": 1, "complexityScore": 8, "recommendedSubtasks": 4, "reasoning": "complex"}
                ]
            }
        )
    )
    payload = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Build native expansion",
                    "description": "Use isolated workdirs",
                    "details": "Keep main dependencies",
                    "testStrategy": "unit",
                    "status": "pending",
                    "dependencies": [99],
                    "subtasks": [],
                },
                {
                    "id": 2,
                    "title": "Already expanded",
                    "description": "Skip by default",
                    "details": "",
                    "testStrategy": "",
                    "status": "pending",
                    "dependencies": [1],
                    "subtasks": [
                        {"id": 1, "title": "a", "description": "", "details": "", "dependencies": []},
                        {"id": 2, "title": "b", "description": "", "details": "", "dependencies": []},
                    ],
                },
            ]
        }
    }
    tasks_path = tasks_dir / "tasks.json"
    tasks_path.write_text(json.dumps(payload, indent=2))
    return tasks_path


def _read_json(path: Path):
    return json.loads(path.read_text())


def test_tm_parallel_dry_run_manifest_and_dependency_stripping(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel

    tasks_path = _seed_project(tmp_path)
    _write_fake_taskmaster(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.chdir(tmp_path)

    result = tm_parallel.run_tm_parallel(dry_run=True)

    assert result["ok"] is True
    assert result["run_id"]
    assert len(result["workdirs"]) == 1
    assert result["workdirs"][0]["task_id"] == 1
    assert result["skipped"] == [{"task_id": 2, "reason": "already_has_subtasks"}]
    workdir = Path(result["workdirs"][0]["path"])
    isolated = _read_json(workdir / ".taskmaster" / "tasks" / "tasks.json")
    assert isolated["master"]["tasks"][0]["dependencies"] == []
    assert _read_json(tasks_path)["master"]["tasks"][0]["dependencies"] == [99]


def test_tm_parallel_happy_path_merges_subtasks_and_cleans_workdirs(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel

    tasks_path = _seed_project(tmp_path)
    _write_fake_taskmaster(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.chdir(tmp_path)

    result = tm_parallel.run_tm_parallel()

    assert result["ok"] is True
    assert result["applied"] == [1]
    assert result["failed"] == []
    merged = _read_json(tasks_path)
    task1 = merged["master"]["tasks"][0]
    assert task1["dependencies"] == [99]
    assert [s["title"] for s in task1["subtasks"]] == ["Task 1 first", "Task 1 second"]
    assert not Path(".atlas-ai/tmwork").joinpath(result["run_id"]).exists()


def test_tm_run_failure_retries_with_escalated_config_and_telemetry(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel

    _seed_project(tmp_path, provider="anthropic")
    _write_fake_taskmaster(tmp_path / "bin", mode="fail")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.chdir(tmp_path)

    plan = tm_parallel.run_tm_plan()
    run = tm_parallel.run_tm_run(plan["run_id"], concurrency=1, timeout=5)

    assert run["ok"] is False
    assert run["failed"] == [1]
    assert run["results"][0]["attempts"] == 2
    workdir = Path(plan["workdirs"][0]["path"])
    config = _read_json(workdir / ".taskmaster" / "config.json")
    assert config["models"]["main"]["provider"] == "anthropic"
    assert config["models"]["main"]["modelId"] == tm_parallel.TIER_MODEL_IDS["opus"]
    rows = [json.loads(line) for line in Path(".atlas-ai/telemetry.jsonl").read_text().splitlines()]
    assert [row["task_id"] for row in rows] == [1, 1]
    assert rows[0]["exit"] == 1
    assert rows[1]["escalated"] is True


def test_tm_run_timeout_records_failure_and_retains_workdir(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel

    _seed_project(tmp_path)
    _write_fake_taskmaster(tmp_path / "bin", mode="slow")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.chdir(tmp_path)

    plan = tm_parallel.run_tm_plan()
    run = tm_parallel.run_tm_run(plan["run_id"], concurrency=1, timeout=0.1)
    harvest = tm_parallel.run_tm_harvest(plan["run_id"])

    assert run["ok"] is False
    assert run["failed"] == [1]
    assert harvest["failed"] == [1]
    assert Path(plan["workdirs"][0]["path"]).is_dir()
    rows = [json.loads(line) for line in Path(".atlas-ai/telemetry.jsonl").read_text().splitlines()]
    assert rows[-1]["exit"] == "timeout"


def test_tm_parallel_version_gate_refuses_old_taskmaster(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel

    _seed_project(tmp_path)
    _write_fake_taskmaster(tmp_path / "bin", version="0.42.0")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.chdir(tmp_path)

    result = tm_parallel.run_tm_parallel()

    assert result["ok"] is False
    assert result["minimum_version"] == "0.43.0"
    assert "parallel-plan" in result["fallback"]


def test_tm_cli_dry_run_outputs_manifest_from_tmp_project(tmp_path, monkeypatch):
    _seed_project(tmp_path)
    _write_fake_taskmaster(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "tm-parallel", "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(tmp_path / "bin")},
    )

    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["dry_run"] is True
    assert data["workdirs"][0]["task_id"] == 1
