"""Representative end-to-end CLI tests for the prd_taskmaster package.

Each test invokes the root script.py shim via subprocess and asserts on key
fields of the emitted JSON, proving the CLI wiring and pure cores behave.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "script.py"
TEMPLATES = REPO_ROOT / "templates"


def run_cli(*args, expect_exit=0, cwd=None, env=None):
    """Run the CLI shim and return parsed JSON stdout."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=env,
    )
    assert proc.returncode == expect_exit, (
        f"exit={proc.returncode} expected={expect_exit}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    return json.loads(proc.stdout)


def clean_cli_env(tmp_path):
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
        env.pop(key, None)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    env["PATH"] = str(bin_dir)
    env["HOME"] = str(tmp_path / "home")
    return env


def force_native_backend(tmp_path):
    config_dir = tmp_path / ".atlas-ai"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "fleet.json").write_text(json.dumps({"backend": "native"}))


def seed_tasks(tmp_path):
    tm = tmp_path / ".taskmaster"
    (tm / "tasks").mkdir(parents=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": "master"}))
    (tm / "tasks" / "tasks.json").write_text(
        json.dumps(
            {
                "master": {
                    "tasks": [
                        {
                            "id": 1,
                            "title": "Build backend CLI",
                            "description": "Surface backend operations.",
                            "details": "Use backend abstraction wrappers.",
                            "testStrategy": "python3 -m pytest tests/core/test_cli.py -q",
                            "status": "pending",
                            "priority": "medium",
                            "dependencies": [],
                            "subtasks": [],
                        }
                    ]
                }
            }
        )
    )


def test_calc_tasks_small_clamps_to_10():
    data = run_cli("calc-tasks", "--requirements", "3")
    assert data["ok"] is True
    assert data["recommended"] == 10
    assert data["raw_calculation"] == 5


def test_calc_tasks_mid_range():
    data = run_cli("calc-tasks", "--requirements", "12")
    assert data["recommended"] == 18
    assert data["requirements_count"] == 12


def test_calc_tasks_large_clamps_to_40():
    data = run_cli("calc-tasks", "--requirements", "40")
    assert data["recommended"] == 40


def test_load_template_minimal():
    data = run_cli("load-template", "--type", "minimal")
    assert data["ok"] is True
    assert data["type"] == "minimal"
    assert data["line_count"] > 0
    assert data["path"].endswith("taskmaster-prd-minimal.md")
    assert str(TEMPLATES) in data["path"]


def test_load_template_comprehensive():
    data = run_cli("load-template", "--type", "comprehensive")
    assert data["ok"] is True
    assert data["type"] == "comprehensive"
    assert "Executive Summary" in data["content"]


def test_validate_prd_returns_grade(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# Product Requirements: Widget API\n\n"
        "## Problem\nTeams lack a way to sync widgets.\n\n"
        "## Goals\n- REQ-001: The API must return widget lists in under 200ms p95.\n\n"
        "## Out of Scope\n- Billing.\n"
    )
    data = run_cli("validate-prd", "--input", str(prd))
    assert data["ok"] is True
    assert data["grade"] in {"EXCELLENT", "GOOD", "ACCEPTABLE", "NEEDS_WORK"}
    assert data["checks_total"] == 13
    assert 0 <= data["percentage"] <= 100


def test_validate_prd_missing_file_fails():
    data = run_cli("validate-prd", "--input", "does-not-exist.md", expect_exit=1)
    assert data["ok"] is False
    assert "not found" in data["error"]


def test_validate_tasks_valid_file(tmp_path):
    tasks = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Build the widget sync endpoint",
                    "description": "Implement the REST endpoint for syncing widgets",
                    "details": "Wire the route, handler, and serializer",
                    "testStrategy": "Unit and integration tests for the endpoint",
                    "priority": "high",
                    "status": "pending",
                    "dependencies": [],
                    "subtasks": [
                        {"id": 1, "title": "Define route", "description": "Add the URL route", "status": "pending", "dependencies": []},
                        {"id": 2, "title": "Write handler", "description": "Implement handler logic", "status": "pending", "dependencies": [1]},
                    ],
                }
            ]
        }
    }
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))
    data = run_cli("validate-tasks", "--input", str(tasks_file))
    assert data["ok"] is True
    assert data["task_count"] == 1
    assert data["subtask_count"] == 2


def test_enrich_tasks_adds_phase_config(tmp_path):
    tasks = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Research auth frameworks",
                    "description": "Evaluate options",
                    "priority": "high",
                    "status": "pending",
                    "subtasks": [],
                }
            ]
        }
    }
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))
    data = run_cli("enrich-tasks", "--input", str(tasks_file))
    assert data["ok"] is True
    assert data["enriched"] == 1
    written = json.loads(tasks_file.read_text())
    task = written["master"]["tasks"][0]
    assert task["phaseConfig"]["complexity"] == "RESEARCH"
    assert "acceptanceCriteria" in task["phaseConfig"]


def test_enrich_tasks_honors_current_tag_over_flat_key(tmp_path):
    """BUG2 (end-to-end via the CLI shim): with state.json currentTag set and a
    coexisting legacy flat 'tasks' key, enrich-tasks must enrich the active
    tag's tasks and leave the flat tasks untouched."""
    tm = tmp_path / ".taskmaster"
    (tm / "tasks").mkdir(parents=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": "productization"}))
    flat = [{"id": 9, "title": "legacy", "description": "d", "priority": "high",
             "status": "pending", "subtasks": []}]
    prod = [{"id": i, "title": f"prod {i}", "description": "d", "priority": "high",
             "status": "pending", "subtasks": []} for i in range(1, 4)]
    (tm / "tasks" / "tasks.json").write_text(
        json.dumps({"tasks": flat, "productization": {"tasks": prod}})
    )

    data = run_cli("enrich-tasks", cwd=tmp_path)
    assert data["ok"] is True
    assert data["tag"] == "productization"
    assert data["total_tasks"] == 3

    written = json.loads((tm / "tasks" / "tasks.json").read_text())
    assert all("phaseConfig" in t for t in written["productization"]["tasks"])
    assert all("phaseConfig" not in t for t in written["tasks"])  # flat untouched


def test_validate_tasks_explicit_tag_flag(tmp_path):
    """BUG2: the --tag flag is wired on validate-tasks and selects that tag."""
    tm = tmp_path / ".taskmaster"
    (tm / "tasks").mkdir(parents=True)
    (tm / "state.json").write_text(json.dumps({"currentTag": "master"}))

    def vtask(tid):
        return {"id": tid, "title": f"t{tid}", "description": "d", "details": "dd",
                "testStrategy": "verify", "status": "pending", "priority": "high",
                "dependencies": [],
                "subtasks": [{"id": 1, "title": "s", "description": "d",
                              "status": "pending", "dependencies": []},
                             {"id": 2, "title": "s2", "description": "d",
                              "status": "pending", "dependencies": [1]}]}

    (tm / "tasks" / "tasks.json").write_text(json.dumps({
        "master": {"tasks": [vtask(1), vtask(2)]},
        "productization": {"tasks": [vtask(i) for i in range(1, 6)]},
    }))

    data = run_cli("validate-tasks", "--tag", "productization", cwd=tmp_path)
    assert data["ok"] is True
    assert data["tag"] == "productization"
    assert data["task_count"] == 5


def test_backend_command_parser_entries():
    from prd_taskmaster.cli import build_parser

    parser = build_parser()

    assert parser.parse_args(["backend-detect"]).command == "backend-detect"
    assert parser.parse_args(["init-project"]).command == "init-project"

    parsed = parser.parse_args([
        "parse-prd",
        "--input",
        "prd.md",
        "--num-tasks",
        "7",
        "--tag",
        "alpha",
    ])
    assert parsed.command == "parse-prd"
    assert parsed.input == "prd.md"
    assert parsed.num_tasks == 7
    assert parsed.tag == "alpha"

    parsed = parser.parse_args([
        "expand",
        "--id",
        "1",
        "--id",
        "2",
        "--no-research",
        "--tag",
        "alpha",
    ])
    assert parsed.command == "expand"
    assert parsed.id == [1, 2]
    assert parsed.no_research is True
    assert parsed.tag == "alpha"

    parsed = parser.parse_args(["rate", "--tag", "alpha", "--no-research"])
    assert parsed.command == "rate"
    assert parsed.tag == "alpha"
    assert parsed.no_research is True

    parsed = parser.parse_args([
        "context-pack",
        "--files",
        "a.py",
        "b.py",
        "--include-private",
    ])
    assert parsed.command == "context-pack"
    assert parsed.files == ["a.py", "b.py"]
    assert parsed.include_private is True


def test_context_pack_cli_prints_signature_json(tmp_path):
    module = tmp_path / "module.py"
    module.write_text(
        "\n".join(
            [
                "class Thing:",
                "    def use(self, value: int = 1) -> int:",
                "        return value",
                "",
                "def _hidden(flag=False):",
                "    pass",
            ]
        )
    )

    data = run_cli("context-pack", "--files", str(module), "--include-private")

    assert data == {
        "files": [
            {
                "path": str(module),
                "classes": [
                    {
                        "name": "Thing",
                        "methods": [
                            {
                                "name": "use",
                                "signature": "(self, value: int = 1) -> int",
                                "doc_first_line": "",
                            }
                        ],
                    }
                ],
                "functions": [
                    {
                        "name": "_hidden",
                        "signature": "(flag=False)",
                        "doc_first_line": "",
                    }
                ],
            }
        ],
        "skipped": [],
    }


def test_native_parse_prd_no_key_returns_agent_action_json(tmp_path, monkeypatch):
    for _k in ("ANTHROPIC_API_KEY","OPENAI_API_KEY","GEMINI_API_KEY","GOOGLE_API_KEY","OPENAI_COMPATIBLE_API_KEY"):
        monkeypatch.delenv(_k, raising=False)
    env = clean_cli_env(tmp_path)
    force_native_backend(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")

    data = run_cli(
        "parse-prd",
        "--input",
        str(prd),
        "--num-tasks",
        "3",
        "--tag",
        "alpha",
        cwd=tmp_path,
        env=env,
        expect_exit=1,
    )

    assert data["ok"] is False
    assert data["agent_action_required"]["op"] == "parse_prd"
    assert data["agent_action_required"]["num_tasks"] == 3


def test_native_expand_and_rate_no_key_return_agent_action_json(tmp_path, monkeypatch):
    for _k in ("ANTHROPIC_API_KEY","OPENAI_API_KEY","GEMINI_API_KEY","GOOGLE_API_KEY","OPENAI_COMPATIBLE_API_KEY"):
        monkeypatch.delenv(_k, raising=False)
    env = clean_cli_env(tmp_path)
    force_native_backend(tmp_path)
    seed_tasks(tmp_path)

    expand = run_cli(
        "expand",
        "--id",
        "1",
        "--no-research",
        cwd=tmp_path,
        env=env,
        expect_exit=1,
    )
    assert expand["ok"] is False
    assert expand["agent_action_required"]["op"] == "expand"
    assert expand["agent_action_required"]["task_ids"] == [1]

    rate = run_cli(
        "rate",
        "--no-research",
        cwd=tmp_path,
        env=env,
        expect_exit=1,
    )
    assert rate["ok"] is False
    assert rate["agent_action_required"]["op"] == "rate"
