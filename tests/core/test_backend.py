"""Backend abstraction tests for the v4.1 TaskMaster seam."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from prd_taskmaster.lib import CommandError


def _write_fake_taskmaster(bin_dir: Path, version: str = "0.43.1") -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "task-master"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import sys
            from pathlib import Path

            def current_tag():
                state = Path(".taskmaster/state.json")
                if state.is_file():
                    return json.loads(state.read_text()).get("currentTag", "master")
                return "master"

            def write_tasks(count):
                tag = current_tag()
                path = Path(".taskmaster/tasks/tasks.json")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({{tag: {{"tasks": [
                    {{"id": i, "title": f"Task {{i}}", "status": "pending"}}
                    for i in range(1, count + 1)
                ]}}}}, indent=2))

            def log_command(args):
                log = os.environ.get("FAKE_TM_LOG")
                if log:
                    with open(log, "a") as f:
                        f.write(json.dumps(args) + "\\n")

            args = sys.argv[1:]
            if args == ["--version"]:
                print("{version}")
                raise SystemExit(0)

            if args and args[0] == "parse-prd":
                log_command(args)
                count = int(args[args.index("--num-tasks") + 1])
                write_tasks(count)
                print("parse stdout ignored")
                raise SystemExit(0)

            if args and args[0] == "expand":
                log_command(args)
                print("expanded")
                raise SystemExit(0)

            if args and args[0] == "analyze-complexity":
                log_command(args)
                print('{{"complexityAnalysis":[{{"taskId":999}}]}}')
                raise SystemExit(0)

            print("unexpected command: " + " ".join(args), file=sys.stderr)
            raise SystemExit(2)
            """
        ).lstrip()
    )
    script.chmod(0o755)
    return script


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_binary: bool = True) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if with_binary:
        _write_fake_taskmaster(bin_dir)
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir


def _seed_tasks(tmp_path: Path, count: int, tag: str = "master") -> None:
    tm = tmp_path / ".taskmaster"
    (tm / "tasks").mkdir(parents=True, exist_ok=True)
    (tm / "reports").mkdir(parents=True, exist_ok=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": tag}))
    tasks = [
        {
            "id": idx,
            "title": f"Task {idx}",
            "status": "pending",
            "dependencies": [],
            "subtasks": [],
        }
        for idx in range(1, count + 1)
    ]
    (tm / "tasks" / "tasks.json").write_text(json.dumps({tag: {"tasks": tasks}}, indent=2))


def test_backend_factory_precedence_and_auto_detection(tmp_path, monkeypatch):
    from prd_taskmaster.backend import NativeBackend, TaskMasterBackend, get_backend

    _isolate(tmp_path, monkeypatch, with_binary=False)

    explicit = get_backend({"backend": "taskmaster"})
    assert isinstance(explicit, TaskMasterBackend)
    assert explicit.name == "taskmaster"
    assert explicit.detect()["available"] is False

    native = get_backend({"backend": "native"})
    assert isinstance(native, NativeBackend)
    assert native.name == "native"

    auto_fallback = get_backend({"backend": "auto"})
    assert isinstance(auto_fallback, NativeBackend)

    _write_fake_taskmaster(tmp_path / "bin")
    auto = get_backend({"backend": "auto"})
    assert isinstance(auto, TaskMasterBackend)


def test_backend_detect_shape_and_version_gate(tmp_path, monkeypatch):
    from prd_taskmaster.backend import get_backend

    bin_dir = _isolate(tmp_path, monkeypatch, with_binary=False)
    _write_fake_taskmaster(bin_dir, version="0.42.0")

    result = get_backend({"backend": "taskmaster"}).detect()

    assert set(result) == {"name", "available", "version", "ai_ops", "missing"}
    assert result["name"] == "taskmaster"
    assert result["available"] is False
    assert result["ai_ops"] is False
    assert result["version"] == "0.42.0"
    assert any("0.43.0" in item for item in result["missing"])


def test_parse_prd_runs_taskmaster_and_counts_tasks_json(tmp_path, monkeypatch):
    from prd_taskmaster.backend import get_backend

    _isolate(tmp_path, monkeypatch)
    tm = tmp_path / ".taskmaster"
    tm.mkdir()
    (tm / "state.json").write_text(json.dumps({"currentTag": "master"}))
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")

    result = get_backend({"backend": "taskmaster"}).parse_prd(prd, 5)

    assert result["ok"] is True
    assert result["task_count"] == 5


def test_expand_delegates_to_tm_parallel_for_more_than_three_pending(tmp_path, monkeypatch):
    from prd_taskmaster import tm_parallel
    from prd_taskmaster.backend import get_backend

    _isolate(tmp_path, monkeypatch)
    _seed_tasks(tmp_path, 4)
    called = {}

    def fake_run_tm_parallel(**kwargs):
        called.update(kwargs)
        return {"ok": True, "delegated": True}

    monkeypatch.setattr(tm_parallel, "run_tm_parallel", fake_run_tm_parallel)

    result = get_backend({"backend": "taskmaster"}).expand(tag="master")

    assert result == {"ok": True, "delegated": True}
    assert called["tag"] == "master"


def test_expand_serial_branch_runs_binary_and_appends_telemetry(tmp_path, monkeypatch):
    from prd_taskmaster.backend import get_backend

    _isolate(tmp_path, monkeypatch)
    _seed_tasks(tmp_path, 3)
    log_path = tmp_path / "fake-tm.jsonl"
    monkeypatch.setenv("FAKE_TM_LOG", str(log_path))

    result = get_backend({"backend": "taskmaster"}).expand(tag="master")

    assert result["ok"] is True
    assert result["expanded"] == [1, 2, 3]
    commands = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert commands == [
        ["expand", "--id", "1", "--research"],
        ["expand", "--id", "2", "--research"],
        ["expand", "--id", "3", "--research"],
    ]
    telemetry = [
        json.loads(line)
        for line in (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()
    ]
    assert [row["task_id"] for row in telemetry] == [1, 2, 3]
    assert {row["op_class"] for row in telemetry} == {"structured_gen"}
    assert {row["backend"] for row in telemetry} == {"taskmaster-api"}


def test_rate_reads_report_file_not_stdout(tmp_path, monkeypatch):
    from prd_taskmaster.backend import get_backend

    _isolate(tmp_path, monkeypatch)
    _seed_tasks(tmp_path, 1)
    report = tmp_path / ".taskmaster" / "reports" / "task-complexity-report.json"
    report.write_text(
        json.dumps(
            {
                "complexityAnalysis": [
                    {"taskId": 7, "complexityScore": 8, "recommendedSubtasks": 4}
                ]
            }
        )
    )

    result = get_backend({"backend": "taskmaster"}).rate()

    assert result["ok"] is True
    assert result["report"] == str(Path(".taskmaster/reports/task-complexity-report.json"))
    assert result["complexityAnalysis"][0]["taskId"] == 7


def test_load_fleet_config_backend_key_validates_silently(tmp_path, monkeypatch):
    from prd_taskmaster.fleet import load_fleet_config

    monkeypatch.chdir(tmp_path)
    assert load_fleet_config()["backend"] == "auto"

    cfg_dir = tmp_path / ".atlas-ai"
    cfg_dir.mkdir()
    (cfg_dir / "fleet.json").write_text(json.dumps({"backend": "native"}))
    assert load_fleet_config()["backend"] == "native"

    (cfg_dir / "fleet.json").write_text(json.dumps({"backend": "broken"}))
    assert load_fleet_config()["backend"] == "auto"
