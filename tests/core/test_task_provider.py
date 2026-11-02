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
import os
import sqlite3
import sys
import time

p = argparse.ArgumentParser()
p.add_argument("kanban")
p.add_argument("--board", required=True)
p.add_argument("operation", choices=["materialize", "materialize-check", "external"])
p.add_argument("verb", nargs="?")
for flag in ["project", "plan-revision", "proposed-id", "fingerprint", "title", "body-file", "prior-rows-file", "execution-kind", "task", "maps-from"]:
    p.add_argument("--" + flag)
p.add_argument("--pending-parent-proposed", action="append", default=[])
p.add_argument("--parent-proposed", action="append", default=[])
p.add_argument("--json", action="store_true")
a = p.parse_args()
assert a.board == "fixture-board"
assert Path.cwd() == Path(__file__).parent
store = Path(__file__).with_name("owner.sqlite")
check = a.operation == "materialize-check"
if a.operation == "external":
    assert a.verb == "status"
    with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT task_id,title,body FROM cards WHERE board=? AND task_id=?", (a.board, a.task)).fetchone()
        assert row is not None
        print(json.dumps({{"task_id": row[0], "execution_kind": "external_session", "title": row[1], "body": row[2]}}))
    sys.exit(0)
assert a.execution_kind == "external_session" and a.json
# Both clients must reach the owner before either enters its transaction.
if not check and os.environ.get("OWNER_RACE_DIR"):
    gate = Path(os.environ["OWNER_RACE_DIR"])
    (gate / str(os.getpid())).write_text("arrived")
    deadline = time.monotonic() + 5
    while len(list(gate.iterdir())) < 2:
        assert time.monotonic() < deadline, "clients serialised before owner"
        time.sleep(0.01)
connection = sqlite3.connect(":memory:" if check else store, timeout=20)
if check and store.exists():
    with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as source:
        source.backup(connection)
with connection as db:
    db.execute("BEGIN IMMEDIATE")
    db.execute("CREATE TABLE IF NOT EXISTS cards (board, project, revision, proposed, fingerprint, task_id UNIQUE, title, body, parents)")
    db.execute("CREATE TABLE IF NOT EXISTS materializations (board, project, revision, proposed, fingerprint, task_id, UNIQUE(board, project, revision, proposed))")
    db.execute("CREATE TABLE IF NOT EXISTS events (task_id, maps_from)")
    key = (a.board, a.project, a.plan_revision, a.proposed_id)
    row = db.execute("SELECT fingerprint, task_id FROM materializations WHERE board=? AND project=? AND revision=? AND proposed=?", key).fetchone()
    prior = db.execute("SELECT fingerprint, task_id FROM materializations WHERE board=? AND project=? AND proposed=? ORDER BY rowid DESC", (a.board, a.project, a.proposed_id)).fetchall()
    reason = None
    if row:
        state = "existing" if row[0] == a.fingerprint else "conflict"
        task_id = row[1]
        reason = "materialization_conflict"
    elif any(r[0] == a.fingerprint for r in prior):
        state = "existing"
        task_id = next(r[1] for r in prior if r[0] == a.fingerprint)
    elif a.maps_from:
        revision, proposed = a.maps_from.split(":", 1)
        mapped = db.execute("SELECT task_id FROM materializations WHERE board=? AND project=? AND revision=? AND proposed=?", (a.board, a.project, revision, proposed)).fetchone()
        state = "mapped" if mapped and revision != a.plan_revision else "conflict"
        task_id = mapped[0] if mapped else (prior[0][1] if prior else "t_unknown")
        reason = "revision_requires_mapping"
        if state == "mapped":
            db.execute("INSERT INTO events VALUES (?,?)", (task_id, a.maps_from))
    elif prior:
        state, task_id, reason = "conflict", prior[0][1], "revision_requires_mapping"
    else:
        state = "created"
        task_id = "t_" + str(db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] + 1)
        db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?)", key + (a.fingerprint, task_id, a.title, Path(a.body_file).read_text(), json.dumps(a.parent_proposed)))
    if state == "mapped":
        db.execute("UPDATE cards SET title=?,body=?,parents=? WHERE task_id=?",
                   (a.title, Path(a.body_file).read_text(), json.dumps(a.parent_proposed), task_id))
    if state != "conflict" and not row:
        db.execute("INSERT INTO materializations VALUES (?,?,?,?,?,?)", key + (a.fingerprint, task_id))
    print(json.dumps({{"state": state, "task_id": None if check and state == "created" else task_id, **({{"reason": reason}} if state == "conflict" else {{}})}}))
    if state == "conflict":
        sys.exit(3)
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
    store = tmp_path / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    store.write_text('{"tasks": []}')
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


def test_two_threads_share_owner_uniqueness(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    gate = project / "race"
    gate.mkdir()
    monkeypatch.setenv("OWNER_RACE_DIR", str(gate))
    monkeypatch.setattr(tp.fcntl, "flock", lambda *args: None)
    replies = []
    real = tp._owner_run
    def record(root, config, args):
        reply = real(root, config, args)
        replies.append((args[0], reply.returncode, reply.stdout, reply.stderr))
        return reply
    monkeypatch.setattr(tp, '_owner_run', record)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: tp.run_materialize(str(project), "plan.json"), range(2)))
    if not all(r["ok"] for r in results):
        print('THREAD OWNER REPLIES', json.dumps(replies), 'RESULTS', json.dumps(results))
    assert all(r["ok"] for r in results), (results, replies)
    assert results[0]["task_ids"] == results[1]["task_ids"]
    assert len(cards(project)) == 1


def test_owner_deduplicates_even_without_local_reference(project):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    (project / ".atlas-ai/materializations.json").unlink()
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    assert len(cards(project)) == 1


def test_changed_intent_without_local_reference_is_refused_by_owner(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["task_ids"] == {"build": "t_1"}
    (project / ".atlas-ai/materializations.json").unlink()
    changed = save_plan(project, [{**candidate(), "acceptance": ["New acceptance must pass"]}])
    assert changed["plan_revision"] != old["plan_revision"]
    assert changed["tasks"][0]["intent_fingerprint"] != old["tasks"][0]["intent_fingerprint"]
    real_run = tp.subprocess.run
    replies = []
    def spy(*args, **kwargs):
        response = real_run(*args, **kwargs)
        replies.append((response.returncode, json.loads(response.stdout)))
        return response
    monkeypatch.setattr(tp.subprocess, "run", spy)
    result = tp.run_materialize(str(project), "plan.json")
    assert result["ok"] is False
    assert result["state"] == "conflict"
    assert replies == [(3, {"state": "conflict", "task_id": "t_1", "reason": "revision_requires_mapping"})]
    assert len(cards(project)) == 1
    assert not (project / ".atlas-ai/materializations.json").exists()


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


def test_unchanged_task_in_new_revision_reuses_card(project):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    revised = save_plan(project, [candidate(), candidate("extra")])
    result = tp.run_materialize(str(project), "plan.json")
    assert result["ok"] and result["task_ids"] == {"build": "t_1", "extra": "t_2"}
    assert len(cards(project)) == 2
    with sqlite3.connect(project / "owner.sqlite") as db:
        assert db.execute("SELECT revision, task_id FROM materializations WHERE proposed='build' ORDER BY rowid").fetchall() == [
            (old["plan_revision"], "t_1"), (revised["plan_revision"], "t_1")]


@pytest.mark.parametrize("renamed", [False, True])
@pytest.mark.parametrize("lost_references", [False, True])
def test_mapping_reuses_card_and_replay_is_existing(project, renamed, lost_references, monkeypatch):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["task_ids"] == {"build": "t_1"}
    if lost_references:
        (project / ".atlas-ai/materializations.json").unlink()
    successor = "renamed" if renamed else "build"
    save_plan(project, [{**candidate(successor), "acceptance": ["Changed acceptance passes"]}],
              previous_plan=old, prior_mapping={"build": successor})
    real_run = tp.subprocess.run
    replies = []
    def spy(*args, **kwargs):
        response = real_run(*args, **kwargs)
        if "materialize" in args[0]:
            replies.append(json.loads(response.stdout)["state"])
        return response
    monkeypatch.setattr(tp.subprocess, "run", spy)
    first = tp.run_materialize(str(project), "plan.json")
    replay = tp.run_materialize(str(project), "plan.json")
    assert first["ok"] and replay["ok"]
    assert first["task_ids"] == replay["task_ids"] == {successor: "t_1"}
    assert replies == ["mapped", "existing"]
    assert len(cards(project)) == 1
    with sqlite3.connect(project / "owner.sqlite") as db:
        assert db.execute("SELECT * FROM events").fetchall() == [("t_1", old["plan_revision"] + ":build")]


def test_changed_plan_with_local_references_is_still_refused_by_owner(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    changed = save_plan(project, [{**candidate(), "description": "Actually changed intent"}])
    assert old["tasks"][0]["intent_fingerprint"] != changed["tasks"][0]["intent_fingerprint"]
    real_run = tp.subprocess.run
    effects = []
    def spy(args, **kwargs):
        effects.append(args)
        return real_run(args, **kwargs)
    monkeypatch.setattr(tp.subprocess, "run", spy)
    result = tp.run_materialize(str(project), "plan.json")
    assert not result["ok"] and result["state"] == "conflict"
    assert len(effects) == 1 and "materialize-check" in effects[0]
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


def test_doctor_is_read_only_and_checks_advertised_contract(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    before = tree_hash(project)
    real_run = tp.subprocess.run
    effects = []
    def spy(args, **kwargs):
        effects.append(args)
        return real_run(args, **kwargs)
    monkeypatch.setattr(tp.subprocess, "run", spy)
    result = tp.run_doctor(str(project))
    assert result["ok"] and result["package"]["version"]
    assert result["provider"]["reachable"] is True
    assert result["provider"]["contract"] == "P02"
    assert any(args[-5:] == ["external", "status", "--task", "t_1", "--json"] for args in effects)
    assert all("--help" in args or "external" in args for args in effects)
    assert tree_hash(project) == before
    assert len(cards(project)) == 1


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
        if "materialize" in args and "--proposed-id" in args and args[args.index("--proposed-id") + 1] == "b":
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
    gate = project / "race"
    gate.mkdir()
    runner = project / "without_client_lock.py"
    runner.write_text("import fcntl, runpy, sys\nfcntl.flock = lambda *args: None\nsys.path.insert(0, str(__import__('pathlib').Path(sys.argv[1]).parent))\nrunpy.run_path(sys.argv.pop(1), run_name='__main__')\n")
    command = [sys.executable, str(runner), str(REPO / "script.py"), "materialize",
               "--project-root", str(project), "--plan", "plan.json"]
    processes = [subprocess.Popen(command, cwd=project,
                                 env={"HOME": str(project), "PATH": str(project), "OWNER_RACE_DIR": str(gate)},
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
    ("task_provider.py", '    _read_card(root, config, payload["task_id"], request)', '    pass  # removed read-back',
     "test_task_provider.py", "owner_write_is_read_back_before_recording_reference"),
    ("task_provider.py", "selected_tag = raw.get(tag)", 'selected_tag = raw.get("master")',
     "test_task_provider.py", "file_materialize_respects_current_tag"),
    ("plan_output.py", "if plan != expected:", "if False:",
     "test_plan_output.py", "plan_tampering_refuses"),
    ("task_provider.py", 'args.extend(["--maps-from", plan["prior_plan_revision"] + ":" + prior_id])',
     'pass  # removed mapping argument', "test_task_provider.py", "mapping_reuses_card_and_replay_is_existing"),
    ("task_provider.py", '{"created", "existing", "mapped"}', '{"created", "existing"}',
     "test_task_provider.py", "mapping_reuses_card_and_replay_is_existing"),
    ("task_provider.py", '                _read_card(root, config, task_id)',
     '                pass  # removed doctor read', "test_task_provider.py", "doctor_reachability_requires_successful_real_read"),
    ("task_provider.py", '[executable, "kanban", "--board", config["board"], *args]',
     '["hermes", "kanban", "--board", config["board"], *args]',
     "test_task_provider.py", "relative_path_entry_is_resolved_before_subprocess_cwd"),
    ("test_task_provider.py", '    elif prior:', '    elif False:',
     "test_task_provider.py", "changed_intent_without_local_reference_is_refused_by_owner"),
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
    source = (test_dir if module.startswith("test_") else export / "prd_taskmaster") / module
    original = source.read_text()
    mutable, separator, rest = original.partition("@pytest.fixture") if module.startswith("test_") else (original, "", "")
    assert mutable.count(old) == 1
    source.write_text(mutable.replace(old, new) + separator + rest)
    result = subprocess.run([sys.executable, "-m", "pytest", str(test_dir / test_file),
                             "-q", "--basetemp", str(export / "nested-tmp"),
                             "-k", f"({selection}) and not removed_guard_turns_proof_red", "--tb=short"],
                            cwd=export, env={"HOME": str(export), "PATH": "",
                            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "failed" in result.stdout and "ERROR" not in result.stdout, result.stdout
    print(f"MUTATION CAUGHT: {module}: {old.strip()}: {result.stdout.splitlines()[-1]}")


def test_stdlib_cli_plan_and_provider_commands_from_unrelated_cwd(project):
    (project / "candidates.json").write_text(json.dumps({"tasks": [candidate()]}))
    env = {"PATH": str(project), "HOME": str(project)}
    def cli(*args, expected_code=0):
        result = subprocess.run([sys.executable, "-S", str(REPO / "script.py"), *args,
                                 "--project-root", str(project)], cwd=project.parent,
                                env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected_code, result.stdout + result.stderr
        return json.loads(result.stdout)
    assert cli("provider-configure", "--task-provider", "atlas-kanban", "--board", "fixture-board")["ok"]
    result = cli("plan", "--project", "demo", "--input", "candidates.json", "--output", "generated-plan.json")
    assert result["plan"]["tasks"][0]["proposed_task_id"] == "build"
    assert not (project / "owner.sqlite").exists()
    assert not (project / ".taskmaster").exists()
    assert cli("doctor", expected_code=1)["provider"]["reachable"] == "UNKNOWN"
    assert not (project / "owner.sqlite").exists()
    assert cli("materialize", "--plan", "generated-plan.json")["task_ids"] == {"build": "t_1"}
    assert cli("workflow-status", "--task", "t_1")["execution_kind"] == "external_session"
    store = project / ".taskmaster/tasks/tasks.json"
    store.parent.mkdir(parents=True)
    store.write_text('{"tasks":[{"id":1,"title":"Foreign","status":"done"}]}')
    before = tree_hash(project)
    assert cli("import-preview", "--project", "demo")["proposed_cards"][0]["fresh_verification"] is False
    assert tree_hash(project) == before


def test_fake_owner_implements_all_five_ruling_six_cases(project):
    from prd_taskmaster import task_provider as tp
    config = tp.load_config(str(project))
    body = project / "request.md"
    body.write_text("Fixture acceptance")
    def call(revision, fingerprint, proposed="build", maps_from=None):
        args = ["materialize", "--project", "demo", "--plan-revision", revision,
                "--proposed-id", proposed, "--fingerprint", fingerprint,
                "--title", "Fixture", "--body-file", str(body),
                "--execution-kind", "external_session", "--json"]
        if maps_from:
            args.extend(["--maps-from", maps_from])
        reply = tp._owner_run(project, config, args)
        return reply.returncode, json.loads(reply.stdout)
    assert call("r1", "f1") == (0, {"state": "created", "task_id": "t_1"})
    assert call("r1", "f1") == (0, {"state": "existing", "task_id": "t_1"})
    assert call("r1", "f2") == (3, {"state": "conflict", "task_id": "t_1", "reason": "materialization_conflict"})
    assert call("r2", "f1") == (0, {"state": "existing", "task_id": "t_1"})
    assert call("r3", "f2") == (3, {"state": "conflict", "task_id": "t_1", "reason": "revision_requires_mapping"})
    assert call("r3", "f2", maps_from="missing:build")[0] == 3
    assert call("r3", "f2", maps_from="r2:build") == (0, {"state": "mapped", "task_id": "t_1"})
    assert call("r3", "f2", maps_from="r2:build") == (0, {"state": "existing", "task_id": "t_1"})
    assert call("r4", "f3", proposed="renamed", maps_from="r3:build") == (0, {"state": "mapped", "task_id": "t_1"})
    assert call("r4", "f3", proposed="renamed", maps_from="r3:build")[1]["state"] == "existing"
    assert len(cards(project)) == 1
    with sqlite3.connect(project / "owner.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM materializations").fetchone()[0] == 4
        assert db.execute("SELECT * FROM events").fetchall() == [("t_1", "r2:build"), ("t_1", "r3:build")]


@pytest.mark.parametrize("path", ["", ":", "."])
def test_owner_executable_never_resolves_from_project_root(project, monkeypatch, path):
    from prd_taskmaster import task_provider as tp
    # The fixture executable is a trap: if executed it will create the owner DB.
    save_plan(project)
    monkeypatch.chdir(project)
    monkeypatch.setenv("PATH", path)
    result = tp.run_materialize(str(project), "plan.json")
    assert not result["ok"] and "unavailable" in result["error"]
    assert not (project / "owner.sqlite").exists()


def test_relative_path_entry_is_resolved_before_subprocess_cwd(project, tmp_path, monkeypatch):
    from prd_taskmaster import task_provider as tp
    # Relative PATH is relative to the caller, never to the target project's cwd.
    caller = project / "caller"
    caller.mkdir()
    bin_dir = caller / "bin"
    bin_dir.mkdir()
    (bin_dir / "hermes").write_text(f"#!{sys.executable}\nprint('caller executable')\n")
    (bin_dir / "hermes").chmod(0o700)
    monkeypatch.chdir(caller)
    monkeypatch.setenv("PATH", "bin")
    reply = tp._owner_run(project, tp.load_config(str(project)), ["materialize", "--help"])
    assert reply.stdout.strip() == "caller executable"
    assert not (project / "owner.sqlite").exists()


@pytest.mark.parametrize("failure", ["no-board", "no-cli", "invalid-config", "bad-root", "no-reference"])
def test_doctor_preserves_partial_diagnostics_when_unread(project, monkeypatch, failure):
    from prd_taskmaster import task_provider as tp
    root = str(project)
    if failure == "no-board":
        config_path = project / ".atlas-workflow.json"
        config = json.loads(config_path.read_text())
        config["board"] = None
        config_path.write_text(json.dumps(config))
    elif failure == "no-cli":
        monkeypatch.setenv("PATH", "")
    elif failure == "invalid-config":
        (project / ".atlas-workflow.json").write_text("[]")
    elif failure == "bad-root":
        root = str(project / "absent")
    before = tree_hash(project)
    result = tp.run_doctor(root)
    assert result["ok"] is False
    assert result["package"]["name"] == "prd-taskmaster" and result["package"]["version"]
    assert result["read_only"] is True
    assert result["provider"]["reachable"] == "UNKNOWN"
    if failure in {"bad-root", "invalid-config"}:
        assert result["config"] == "UNKNOWN"
    else:
        assert result["config"]["task_provider"] == "atlas-kanban"
    assert result["provider"]["advertised_contract"] == (True if failure == "no-reference" else "UNKNOWN")
    assert tree_hash(project) == before
    assert not (project / "owner.sqlite").exists()


@pytest.mark.parametrize("status", ["failed", "invalid-json", "wrong-card", "wrong-kind", "timeout"])
def test_doctor_reachability_requires_successful_real_read(project, monkeypatch, status):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    real_run = tp.subprocess.run
    def spy(args, **kwargs):
        if "--help" not in args:
            assert args[-5:] == ["external", "status", "--task", "t_1", "--json"]
            if status == "timeout":
                raise subprocess.TimeoutExpired(args, 30)
            body = {"invalid-json": "not-json", "wrong-card": '{"task_id":"t_other","execution_kind":"external_session"}',
                    "wrong-kind": '{"task_id":"t_1","execution_kind":"worker"}'}.get(status, "")
            return subprocess.CompletedProcess(args, 1 if status == "failed" else 0, body, "private diagnostics")
        return real_run(args, **kwargs)
    monkeypatch.setattr(tp.subprocess, "run", spy)
    before = tree_hash(project)
    result = tp.run_doctor(str(project))
    assert not result["ok"]
    assert result["provider"]["reachable"] is False
    assert result["provider"]["advertised_contract"] is True
    assert result["provider"]["contract"] == "P02"
    assert "private diagnostics" not in json.dumps(result)
    assert tree_hash(project) == before


@pytest.mark.parametrize("renamed", [False, True])
def test_explicit_mapping_of_unchanged_intent_returns_same_card(project, renamed):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), "plan.json")["ok"]
    successor = "renamed" if renamed else "build"
    # Stable intent, including title: only the logical ID and revision mapping change.
    save_plan(project, [{**candidate(), "proposed_task_id": successor}],
              previous_plan=old, prior_mapping={"build": successor})
    first = tp.run_materialize(str(project), "plan.json")
    second = tp.run_materialize(str(project), "plan.json")
    assert first["ok"] and second["ok"]
    assert first["task_ids"] == second["task_ids"] == {successor: "t_1"}
    assert first["prior_task_ids"] == {"build": "t_1"}
    assert len(cards(project)) == 1


@pytest.mark.parametrize("failure", ["no-store", "bad-store"])
def test_file_doctor_reports_unread_store_without_losing_config(project, monkeypatch, failure):
    from prd_taskmaster import task_provider as tp
    assert tp.run_configure(str(project), task_provider="taskmaster-file")["ok"]
    if failure == "bad-store":
        store = project / ".taskmaster/tasks/tasks.json"
        store.parent.mkdir(parents=True)
        store.write_text("invalid JSON")
    monkeypatch.setattr(tp.subprocess, "run", lambda *args, **kw: pytest.fail("owner called"))
    before = tree_hash(project)
    result = tp.run_doctor(str(project))
    assert not result["ok"] and result["read_only"]
    assert result["package"]["version"]
    assert result["config"]["task_provider"] == "taskmaster-file"
    assert result["provider"]["reachable"] == "UNKNOWN"
    assert result["provider"]["contract"] == "taskmaster-file"
    assert tree_hash(project) == before
