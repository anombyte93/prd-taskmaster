"""Storage-independent planning, including the pre-split baseline observation."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_legacy_baseline_without_optional_runtime(tmp_path):
    """The existing plan floor names a local file, not a canonical card."""
    (tmp_path / "prd.md").write_text("# PRD\nREQ-001: Produce a plan.")
    result = subprocess.run(
        [sys.executable, str(REPO / "script.py"), "parse-prd", "--input",
         str(tmp_path / "prd.md"), "--num-tasks", "1"],
        cwd=tmp_path,
        env={"PATH": "", "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=30,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["agent_action_required"]["op"] == "parse_prd"
    assert ".taskmaster/tasks/tasks.json" in json.dumps(payload)
    assert "task_id" not in payload
    assert not (tmp_path / ".taskmaster").exists()
    print("BASELINE: PATH empty; parse-prd exits 1, asks for local tasks.json, no canonical task_id")


def candidate(task_id="build", dependencies=None):
    return {"proposed_task_id": task_id, "title": "Build " + task_id,
            "description": "Implement the bounded change",
            "acceptance": ["Focused tests pass"], "dependencies": dependencies or []}


def test_plan_hashes_content_and_preserves_logical_ids():
    from prd_taskmaster.plan_output import build_plan, validate_plan
    first = build_plan("demo", [candidate("b", ["a"]), candidate("a")])
    second = build_plan("demo", [candidate("a"), candidate("b", ["a"])])
    assert first == second
    assert validate_plan(first) == first
    assert len(first["plan_revision"]) == 64
    assert [t["proposed_task_id"] for t in first["tasks"]] == ["a", "b"]
    changed = candidate("a")
    changed["acceptance"] = ["A different acceptance test passes"]
    revision = build_plan("demo", [changed, candidate("b", ["a"])])
    assert revision["plan_revision"] != first["plan_revision"]
    assert revision["tasks"][0]["intent_fingerprint"] != first["tasks"][0]["intent_fingerprint"]


@pytest.mark.parametrize("tasks", [[], [candidate(), candidate()],
    [candidate("a", ["missing"])], [candidate("a", ["a"])],
    [candidate("a", ["b"]), candidate("b", ["a"])],
    [{**candidate(), "acceptance": []}], [{**candidate(), "title": ""}],
    [{**candidate(), "proposed_task_id": "../bad"}],
    [{**candidate(), "dependencies": "bad"}],
    [{**candidate(), "acceptance": "not a list"}]])
def test_invalid_plans_refuse(tasks):
    from prd_taskmaster.plan_output import build_plan
    from prd_taskmaster.lib import CommandError
    with pytest.raises(CommandError):
        build_plan("demo", tasks)


@pytest.mark.parametrize("field", ["plan_revision", "intent_fingerprint", "title"])
def test_plan_tampering_refuses(field):
    from prd_taskmaster.plan_output import build_plan, validate_plan
    from prd_taskmaster.lib import CommandError
    plan = build_plan("demo", [candidate()])
    if field == "plan_revision":
        plan[field] = "0" * 64
    else:
        plan["tasks"][0][field] = "tampered"
    with pytest.raises(CommandError):
        validate_plan(plan)


def test_revision_requires_complete_explicit_mapping():
    from prd_taskmaster.plan_output import build_plan
    from prd_taskmaster.lib import CommandError
    old = build_plan("demo", [candidate()])
    for mapping in (None, {}, {"unknown": "build"}, {"build": "missing"}):
        with pytest.raises(CommandError):
            build_plan("demo", [candidate()], previous_plan=old, prior_mapping=mapping)
    revised = build_plan("demo", [candidate(), candidate("extra")],
                         previous_plan=old, prior_mapping={"build": "build"})
    assert revised["prior_plan_revision"] == old["plan_revision"]
    assert revised["prior_mapping"] == {"build": "build"}


def test_generation_only_writes_plan_at_explicit_root(tmp_path, monkeypatch):
    from prd_taskmaster.plan_output import run_plan
    root = tmp_path / "project"
    root.mkdir()
    (root / "candidate.json").write_text(json.dumps({"tasks": [candidate()]}))
    monkeypatch.chdir(tmp_path)
    before_cwd = Path.cwd()
    result = run_plan(str(root), "demo", input_path="candidate.json", output_path="plan.json")
    assert result["ok"] is True
    assert result["plan"]["tasks"][0]["proposed_task_id"] == "build"
    assert json.loads((root / "plan.json").read_text()) == result["plan"]
    assert not (root / ".taskmaster").exists()
    assert not (root / ".atlas-ai").exists()
    assert Path.cwd() == before_cwd


def test_default_plan_request_works_with_empty_path_and_home(tmp_path):
    result = subprocess.run(
        [sys.executable, str(REPO / "script.py"), "plan", "--project-root", str(tmp_path),
         "--project", "demo", "--prd", "prd.md"],
        cwd=tmp_path, env={"PATH": "", "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=30,
    )
    # A missing PRD must fail instead of silently requesting work on a phantom file.
    assert result.returncode == 1
    (tmp_path / "prd.md").write_text("# A bounded PRD")
    result = subprocess.run(result.args, cwd=tmp_path,
                            env={"PATH": "", "HOME": str(tmp_path)},
                            capture_output=True, text=True, timeout=30)
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["task_provider"] == "atlas-kanban"
    assert payload["agent_action_required"]["op"] == "generate_plan"
    assert "intent_fingerprint" in json.dumps(payload)
    assert not (tmp_path / ".taskmaster").exists()
    assert not (tmp_path / ".atlas-ai").exists()


@pytest.mark.parametrize("path", ["../escape.json", "/tmp/outside-project-plan.json"])
def test_plan_path_cannot_escape_root(tmp_path, path):
    from prd_taskmaster.plan_output import run_plan
    result = run_plan(str(tmp_path), "demo", input_path=path, output_path="plan.json")
    assert result["ok"] is False
    assert not (tmp_path / "plan.json").exists()


@pytest.mark.parametrize("output", [".taskmaster/tasks/tasks.json", ".atlas-workflow.json",
                                   ".atlas-ai/materializations.json"])
def test_plan_request_cannot_target_runtime_storage(tmp_path, output):
    from prd_taskmaster.plan_output import run_plan
    result = run_plan(str(tmp_path), "demo", output_path=output)
    assert result["ok"] is False
    assert list(tmp_path.iterdir()) == []


def test_boolean_schema_version_is_not_a_content_hash_match():
    from prd_taskmaster.plan_output import build_plan, validate_plan
    from prd_taskmaster.lib import CommandError
    plan = build_plan("demo", [candidate()])
    plan["schema_version"] = True
    with pytest.raises(CommandError):
        validate_plan(plan)


@pytest.mark.parametrize('prior,successor,new_id', [('k', 'z', 'a-orphan'), ('zk', 'ay', '0-new')])
def test_mapping_cannot_keep_a_renamed_prior_id(prior, successor, new_id):
    from prd_taskmaster.plan_output import build_plan, content_hash, validate_plan
    from prd_taskmaster.lib import CommandError
    old = build_plan('demo', [candidate(prior)])
    rows = [candidate(new_id), candidate(prior), candidate(successor)]
    with pytest.raises(CommandError, match='prior logical id remains'):
        build_plan('demo', rows, previous_plan=old, prior_mapping={prior: successor})
    # Revalidation must reject a correctly hashed hand-authored invalid mapping too.
    body = build_plan('demo', rows)
    body.pop('plan_revision')
    body.update(prior_plan_revision=old['plan_revision'], prior_mapping={prior: successor})
    with pytest.raises(CommandError, match='prior logical id remains'):
        validate_plan({**body, 'plan_revision': content_hash(body)})
    assert build_plan('demo', [candidate(prior)], previous_plan=old,
                      prior_mapping={prior: prior})['prior_mapping'] == {prior: prior}


def test_plan_core_matches_cli_exclusive_source_arguments(tmp_path):
    from prd_taskmaster.plan_output import run_plan
    (tmp_path / "candidate.json").write_text(json.dumps({"tasks": [candidate()]}))
    result = run_plan(str(tmp_path), "demo", input_path="candidate.json", prd_path="prd.md")
    assert result["ok"] is False
    assert not (tmp_path / ".atlas-ai").exists()


@pytest.mark.parametrize('field,value,canonical', [
    ('title', '  padded title  ', 'padded title'),
    ('title', 'one\r\ntwo', 'one\ntwo'),
    ('title', 'one\rtwo', 'one\ntwo'),
    ('description', 'line one\r\nline two\rline three', 'line one\nline two\nline three'),
    ('acceptance', ['one\r\ntwo'], ['one\ntwo']),
    ('acceptance', ['one\rtwo'], ['one\ntwo']),
])
def test_plan_hashes_owner_canonical_text(field, value, canonical):
    from prd_taskmaster.plan_output import build_plan, validate_plan
    original = build_plan('demo', [{**candidate(), field: value}])
    expected = build_plan('demo', [{**candidate(), field: canonical}])
    assert original == expected
    assert original['tasks'][0][field] == canonical
    assert validate_plan(original) == original
