"""Hermetic P02 provider tests. The owner is a disposable SQLite CLI fake."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import types

import pytest

from tests.core.test_plan_output import candidate

REPO = Path(__file__).resolve().parents[2]

# Exact owner contract, with database-owned uniqueness across all clients.
OWNER = '''#!{python}
import argparse
import json
from pathlib import Path
import sqlite3
import sys

p = argparse.ArgumentParser()
p.add_argument("kanban")
p.add_argument("--board", required=True)
p.add_argument("operation", choices=["materialize", "external"])
p.add_argument("verb", nargs="?")
for flag in ["project", "plan-revision", "proposed-id", "fingerprint", "title", "body-file", "execution-kind", "task"]:
    p.add_argument("--" + flag)
p.add_argument("--parent-proposed", action="append", default=[])
p.add_argument("--json", action="store_true")
a = p.parse_args()
assert a.board == "fixture-board"
assert Path.cwd() == Path(__file__).parent
with sqlite3.connect(Path(__file__).with_name("owner.sqlite"), timeout=20) as db:
    db.execute("CREATE TABLE IF NOT EXISTS cards (board, project, revision, proposed, fingerprint, task_id, body, parents, UNIQUE(board, project, revision, proposed))")
    db.execute("BEGIN IMMEDIATE")
    if a.operation == "external":
        assert a.verb == "status"
        row = db.execute("SELECT task_id FROM cards WHERE task_id=?", (a.task,)).fetchone()
        print(json.dumps({{"task_id": row[0], "execution_kind": "external_session"}}))
    else:
        assert a.execution_kind == "external_session" and a.json
        key = (a.board, a.project, a.plan_revision, a.proposed_id)
        row = db.execute("SELECT fingerprint, task_id FROM cards WHERE board=? AND project=? AND revision=? AND proposed=?", key).fetchone()
        if row:
            state = "existing" if row[0] == a.fingerprint else "conflict"
            print(json.dumps({{"state": state, "task_id": row[1], "reason": "intent mismatch"}}))
            if state == "conflict":
                sys.exit(3)
        else:
            task_id = "t_" + str(db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] + 1)
            db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)", key + (a.fingerprint, task_id, Path(a.body_file).read_text(), json.dumps(a.parent_proposed)))
            print(json.dumps({{"state": "created", "task_id": task_id}}))
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    from prd_taskmaster import task_provider as tp
    owner = tmp_path / "hermes"
    owner.write_text(OWNER.format(python=sys.executable))
    owner.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    config = tp.run_configure(str(tmp_path), board="fixture-board")
    assert config["ok"] is True
    return tmp_path


def save_plan(root, tasks=None, **kwargs):
    from prd_taskmaster.plan_output import build_plan
    plan = build_plan("demo", tasks or [candidate()], **kwargs)
    (root / "plan.json").write_text(json.dumps(plan))
    return plan


def tree_hash(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def cards(root):
    with sqlite3.connect(root / "owner.sqlite") as db:
        return db.execute("SELECT * FROM cards").fetchall()


def test_default_and_legacy_selection_are_read_only(tmp_path):
    from prd_taskmaster import task_provider as tp
    assert tp.load_config(str(tmp_path))["task_provider"] == "atlas-kanban"
    assert list(tmp_path.iterdir()) == []
    (tmp_path / ".taskmaster").mkdir()
    result = tp.load_config(str(tmp_path))
    assert result["task_provider"] == "taskmaster-file"
    assert "legacy" in result["notice"].lower()
    assert not (tmp_path / ".atlas-workflow.json").exists()


@pytest.mark.parametrize("bad", ["relative", "/nonexistent/provider-split-root"])
def test_root_must_be_explicit_absolute_existing(bad):
    from prd_taskmaster import task_provider as tp
    assert tp.run_configure(bad, board="fixture-board")["ok"] is False


@pytest.mark.parametrize("config", [[], {"task_provider": "unknown"},
    {"task_provider": "atlas-kanban", "project_root": "/wrong", "board": "fixture-board", "owner_host": "localhost"}])
def test_invalid_config_fails_closed_before_any_owner(tmp_path, config, monkeypatch):
    from prd_taskmaster import task_provider as tp
    (tmp_path / ".atlas-workflow.json").write_text(json.dumps(config))
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k: pytest.fail("owner called"))
    assert tp.run_doctor(str(tmp_path))["ok"] is False


def test_materialize_is_idempotent_and_references_only(project):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project, [candidate("second", ["first"]), candidate("first")])
    first = tp.run_materialize(str(project), "plan.json")
    second = tp.run_materialize(str(project), "plan.json")
    assert first["ok"] and second["ok"]
    assert first["task_ids"] == second["task_ids"] == {"first": "t_1", "second": "t_2"}
    assert len(cards(project)) == 2
    assert json.loads(cards(project)[1][-1]) == ["first"]
    assert "Focused tests pass" in cards(project)[0][-2]
    refs = json.loads((project / ".atlas-ai/materializations.json").read_text())
    entry = refs["revisions"][plan["plan_revision"]]["first"]
    assert entry == {"task_id": "t_1", "intent_fingerprint": plan["tasks"][0]["intent_fingerprint"]}
    assert "status" not in json.dumps(refs) and "acceptance" not in json.dumps(refs)
    assert not (project / ".taskmaster").exists()
    assert tp.run_status(str(project), "t_1")["task_id"] == "t_1"


def test_two_threads_share_owner_uniqueness(project):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: tp.run_materialize(str(project), "plan.json"), range(2)))
    assert all(r["ok"] for r in results)
    assert results[0]["task_ids"] == results[1]["task_ids"]
    assert len(cards(project)) == 1


def test_owner_deduplicates_even_without_local_reference(project):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    (project / ".atlas-ai/materializations.json").unlink()
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    assert len(cards(project)) == 1


def test_owner_conflict_is_not_success(project):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    with sqlite3.connect(project / "owner.sqlite") as db:
        db.execute("UPDATE cards SET fingerprint='different-intent'")
    result = tp.run_materialize(str(project), "plan.json")
    assert result["ok"] is False
    assert result["state"] == "conflict"
    assert len(cards(project)) == 1


@pytest.mark.parametrize("change", ["board", "project_root", "owner_host"])
def test_wrong_target_refuses_before_effect(project, change, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    config_path = project / ".atlas-workflow.json"
    config = json.loads(config_path.read_text())
    config[change] = "/wrong" if change == "project_root" else "wrong-target"
    config_path.write_text(json.dumps(config))
    before = tree_hash(project)
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k: pytest.fail("owner called"))
    assert tp.run_materialize(str(project), "plan.json")["ok"] is False
    assert tree_hash(project) == before


def test_revision_needs_mapping_and_records_owner_scoped_lineage(project):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    save_plan(project, [candidate(), candidate("extra")])
    assert not tp.run_materialize(str(project), "plan.json")["ok"]
    assert len(cards(project)) == 1
    save_plan(project, [candidate(), candidate("extra")], previous_plan=old,
              prior_mapping={"build": "build"})
    result = tp.run_materialize(str(project), "plan.json")
    assert result["ok"] and result["task_ids"] == {"build": "t_2", "extra": "t_3"}
    assert len(cards(project)) == 3
    assert result["prior_task_ids"] == {"build": "t_1"}


def test_local_changed_intent_refuses_without_creating_cards(project):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    refs_path = project / ".atlas-ai/materializations.json"
    refs = json.loads(refs_path.read_text())
    refs["revisions"][plan["plan_revision"]]["build"]["intent_fingerprint"] = "different"
    refs_path.write_text(json.dumps(refs))
    result = tp.run_materialize(str(project), "plan.json")
    assert not result["ok"]
    assert "intent" in result["error"]
    assert len(cards(project)) == 1


@pytest.mark.parametrize("response,code", [("not json", 0), ("[]", 0),
    ('{"state":"created"}', 0), ('{"state":"created","task_id":"not-a-card"}', 0),
    ('{"state":"conflict","task_id":"t_1"}', 0),
    ('{"state":"created","task_id":"t_1"}', 3), ("", 1)])
def test_bad_owner_responses_fail_closed(project, monkeypatch, response, code):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a[0], code, response, "private diagnostics"))
    result = tp.run_materialize(str(project), "plan.json")
    assert not result["ok"]
    assert "private diagnostics" not in json.dumps(result)
    assert not (project / ".atlas-ai/materializations.json").exists()


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("hermes", 30)])
def test_missing_or_uncertain_owner_is_failure(project, monkeypatch, error):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(tp.subprocess, "run", fail)
    assert tp.run_materialize(str(project), "plan.json")["ok"] is False


def test_explicit_file_provider_never_calls_owner_and_preserves_existing_tasks(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    assert tp.run_configure(str(project), task_provider="taskmaster-file")["ok"]
    store = project / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({"master": {"tasks": [{"id": 7, "title": "Historical", "status": "done"}]}}))
    save_plan(project)
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k: pytest.fail("owner called"))
    first = tp.run_materialize(str(project), "plan.json")
    assert first["ok"]
    assert tp.run_materialize(str(project), "plan.json")["task_ids"] == first["task_ids"]
    tasks = json.loads(store.read_text())["master"]["tasks"]
    assert len(tasks) == 2 and tasks[0]["status"] == "done" and tasks[1]["status"] == "pending"


@pytest.mark.parametrize("tagged", [False, True])
def test_import_preview_hashes_tree_unchanged_and_marks_history(tmp_path, tagged):
    from prd_taskmaster import task_provider as tp
    store = tmp_path / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    task = {"id": 1, "title": "Historical", "description": "Old work", "status": "done",
            "testStrategy": "Historical test", "dependencies": []}
    store.write_text(json.dumps({"master": {"tasks": [task]}} if tagged else {"tasks": [task]}))
    before = tree_hash(tmp_path)
    result = tp.run_import_preview(str(tmp_path), "demo")
    assert result["ok"] and len(result["proposed_cards"]) == 1
    proposed = result["proposed_cards"][0]
    assert proposed["foreign_id"] == "master:1"
    assert proposed["historical_status"] == "done"
    assert proposed["fresh_verification"] is False
    assert "not fresh verification" in proposed["history_notice"]
    assert tree_hash(tmp_path) == before


def test_doctor_is_read_only_and_checks_advertised_contract(project):
    from prd_taskmaster import task_provider as tp
    before = tree_hash(project)
    result = tp.run_doctor(str(project))
    assert result["ok"] and result["package"]["version"]
    assert result["provider"]["reachable"] and result["provider"]["contract"] == "P02"
    assert tree_hash(project) == before
    assert not (project / "owner.sqlite").exists()


def test_doctor_rejects_incomplete_contract(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, "old CLI help", ""))
    assert tp.run_doctor(str(project))["ok"] is False


def test_cli_materialize_and_mcp_share_explicit_root(project, monkeypatch):
    save_plan(project)
    result = subprocess.run([sys.executable, str(REPO / "script.py"), "materialize",
                             "--project-root", str(project), "--plan", "plan.json"],
                            cwd=project, env={"HOME": str(project), "PATH": str(project)},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["task_ids"] == {"build": "t_1"}
    class FakeMCP:
        def __init__(self, *a):
            pass
        def tool(self, *a, **kw):
            return lambda f: f
    module = types.ModuleType("mcp.server.fastmcp")
    module.FastMCP = FakeMCP
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", module)
    spec = importlib.util.spec_from_file_location("provider_test_server", REPO / "mcp-server/server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert server.materialize(str(project), "plan.json")["task_ids"] == {"build": "t_1"}
    assert server.doctor(str(project))["ok"]
    assert server.plan(str(project), "demo")["task_provider"] == "atlas-kanban"
    assert len(cards(project)) == 1


def test_owner_write_is_read_back_before_recording_reference(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    real_run = tp.subprocess.run
    effects = []
    def spy(args, **kwargs):
        effects.append(args)
        if "external" in args:
            return subprocess.CompletedProcess(args, 0, '{"task_id":"t_wrong","execution_kind":"worker"}', "")
        return real_run(args, **kwargs)
    monkeypatch.setattr(tp.subprocess, "run", spy)
    result = tp.run_materialize(str(project), "plan.json")
    assert not result["ok"]
    assert len(cards(project)) == 1  # write happened; retry must use the same owner key
    assert any("external" in args for args in effects)
    assert not (project / ".atlas-ai/materializations.json").exists()


def test_partial_failure_preserves_prior_reference_and_retry_deduplicates(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project, [candidate("a"), candidate("b", ["a"])])
    real_run = tp.subprocess.run
    def fail_second(args, **kwargs):
        if "--proposed-id" in args and args[args.index("--proposed-id") + 1] == "b":
            raise subprocess.TimeoutExpired(args, 30)
        return real_run(args, **kwargs)
    monkeypatch.setattr(tp.subprocess, "run", fail_second)
    assert not tp.run_materialize(str(project), "plan.json")["ok"]
    refs = json.loads((project / ".atlas-ai/materializations.json").read_text())
    assert list(refs["revisions"][plan["plan_revision"]]) == ["a"]
    monkeypatch.setattr(tp.subprocess, "run", real_run)
    assert tp.run_materialize(str(project), "plan.json")["task_ids"] == {"a": "t_1", "b": "t_2"}
    assert len(cards(project)) == 2


def test_two_plugin_processes_materialize_one_owner_card(project):
    save_plan(project)
    command = [sys.executable, str(REPO / "script.py"), "materialize",
               "--project-root", str(project), "--plan", "plan.json"]
    processes = [subprocess.Popen(command, cwd=project,
                                 env={"HOME": str(project), "PATH": str(project)},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
    results = [p.communicate(timeout=30) for p in processes]
    assert [p.returncode for p in processes] == [0, 0], results
    assert [json.loads(out)["task_ids"] for out, _ in results] == [{"build": "t_1"}] * 2
    assert len(cards(project)) == 1


def test_file_materialize_respects_current_tag(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    assert tp.run_configure(str(project), task_provider="taskmaster-file")["ok"]
    store = project / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({"feature": {"tasks": []}, "master": {"tasks": []}}))
    (project / ".taskmaster/state.json").write_text('{"currentTag":"feature","migrationNoticeShown":true}')
    save_plan(project, [candidate("a"), candidate("b", ["a"])])
    monkeypatch.setattr(tp.subprocess, "run", lambda *a, **k: pytest.fail("owner called"))
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    raw = json.loads(store.read_text())
    assert raw["master"]["tasks"] == []
    assert len(raw["feature"]["tasks"]) == 2
    assert raw["feature"]["tasks"][1]["dependencies"] == [1]
    assert tp.run_doctor(str(project))["ok"]


@pytest.mark.parametrize("target", [".atlas-workflow.json", ".atlas-ai", ".taskmaster"])
def test_symlinked_storage_cannot_escape_root(tmp_path, target):
    from prd_taskmaster import task_provider as tp
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / target).symlink_to(outside, target_is_directory=True)
    before = tree_hash(outside)
    assert not tp.run_configure(str(root), board="fixture-board")["ok"]
    assert tree_hash(outside) == before


@pytest.mark.parametrize("module,old,new,test_file,selection", [
    ("task_provider.py", "if any(refs.get(key) != value for key, value in identity.items()):", "if False:",
     "test_task_provider.py", "wrong_target_refuses_before_effect and board"),
    ("task_provider.py", '"--execution-kind", "external_session"', '"--execution-kind", "worker"',
     "test_task_provider.py", "materialize_is_idempotent_and_references_only"),
    ("task_provider.py", '    _read_card(root, config, payload["task_id"])', '    pass  # removed read-back',
     "test_task_provider.py", "owner_write_is_read_back_before_recording_reference"),
    ("task_provider.py", "selected_tag = raw.get(tag)", 'selected_tag = raw.get("master")',
     "test_task_provider.py", "file_materialize_respects_current_tag"),
    ("plan_output.py", "if plan != expected:", "if False:",
     "test_plan_output.py", "plan_tampering_refuses"),
])
def test_removed_guard_turns_proof_red(tmp_path, module, old, new, test_file, selection):
    """Mutants are plain exports with no git history and no route to a live owner."""
    export = tmp_path / "export"
    export.mkdir()
    shutil.copytree(REPO / "prd_taskmaster", export / "prd_taskmaster",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(REPO / "script.py", export / "script.py")
    test_dir = export / "tests/core"
    test_dir.mkdir(parents=True)
    (export / "tests/__init__.py").write_text("")
    (test_dir / "__init__.py").write_text("")
    for name in ("test_task_provider.py", "test_plan_output.py"):
        shutil.copy2(REPO / "tests/core" / name, test_dir / name)
    source = export / "prd_taskmaster" / module
    original = source.read_text()
    assert original.count(old) == 1
    source.write_text(original.replace(old, new))
    result = subprocess.run([sys.executable, "-m", "pytest", str(test_dir / test_file),
                             "-q", "-k", f"({selection}) and not removed_guard_turns_proof_red", "--tb=short"],
                            cwd=export, env={"HOME": str(export), "PATH": "",
                            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "failed" in result.stdout and "ERROR" not in result.stdout, result.stdout
    print(f"MUTATION CAUGHT: {module}: {old.strip()}: {result.stdout.splitlines()[-1]}")


def test_stdlib_cli_plan_and_provider_commands_from_unrelated_cwd(project):
    (project / "candidates.json").write_text(json.dumps({"tasks": [candidate()]}))
    env = {"PATH": str(project), "HOME": str(project)}
    def cli(*args):
        result = subprocess.run([sys.executable, "-S", str(REPO / "script.py"), *args,
                                 "--project-root", str(project)], cwd=project.parent,
                                env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    assert cli("provider-configure", "--task-provider", "atlas-kanban", "--board", "fixture-board")["ok"]
    result = cli("plan", "--project", "demo", "--input", "candidates.json", "--output", "generated-plan.json")
    assert result["plan"]["tasks"][0]["proposed_task_id"] == "build"
    assert not (project / "owner.sqlite").exists()
    assert not (project / ".taskmaster").exists()
    assert cli("doctor")["ok"]
    assert not (project / "owner.sqlite").exists()
    assert cli("materialize", "--plan", "generated-plan.json")["task_ids"] == {"build": "t_1"}
    assert cli("workflow-status", "--task", "t_1")["execution_kind"] == "external_session"
    store = project / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    store.write_text('{"tasks":[{"id":1,"title":"Foreign","status":"done"}]}')
    before = tree_hash(project)
    assert cli("import-preview", "--project", "demo")["proposed_cards"][0]["fresh_verification"] is False
    assert tree_hash(project) == before
