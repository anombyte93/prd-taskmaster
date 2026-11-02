"""Second-harvest regressions, isolated owner protocol and shipped skill walk."""
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from tests.core.test_plan_output import candidate
from tests.core.test_task_provider import project, save_plan, cards, tree_hash, REPO


@pytest.mark.parametrize('file,expected', [
    ('.taskmaster/config.json', 'taskmaster-file'),
    ('.taskmaster/state.json', 'taskmaster-file'),
    ('.taskmaster/tasks/task_001.txt', 'taskmaster-file'),
    ('.taskmaster/docs/prd.md', 'taskmaster-file'),
    (None, 'atlas-kanban'), ('docs/prd.md', 'atlas-kanban'),
])
def test_only_an_existing_taskmaster_file_selects_legacy(tmp_path, file, expected):
    from prd_taskmaster import task_provider as tp
    (tmp_path / '.taskmaster').mkdir()
    if file:
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
    before = tree_hash(tmp_path)
    result = tp.load_config(str(tmp_path))
    assert result['task_provider'] == expected
    assert ('Legacy' in result['notice']) == (expected == 'taskmaster-file')
    assert tree_hash(tmp_path) == before
    # A persisted choice wins even if legacy files are present.
    assert tp.run_configure(str(tmp_path), task_provider='atlas-kanban', board='fixture-board')['ok']
    assert tp.load_config(str(tmp_path))['task_provider'] == 'atlas-kanban'
    assert tp.run_configure(str(tmp_path), task_provider='taskmaster-file')['ok']
    assert tp.load_config(str(tmp_path))['task_provider'] == 'taskmaster-file'


@pytest.mark.parametrize('already_exists', [False, True])
def test_file_partial_names_only_newly_created_tasks(project, monkeypatch, already_exists):
    from prd_taskmaster import task_provider as tp
    assert tp.run_configure(str(project), task_provider='taskmaster-file')['ok']
    first = save_plan(project, [candidate('a'), candidate('b')] if already_exists else [candidate('b')])
    assert tp.run_materialize(str(project), 'plan.json')['ok']
    (project / '.atlas-ai/materializations.json').unlink()
    save_plan(project, [candidate('a'), {**candidate('b'), 'title': 'Changed'}])
    monkeypatch.setattr(tp, '_owner_run', lambda *args: pytest.fail('file mode called owner'))
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok'] and result['state'] == 'partial'
    assert result['created_task_ids'] == ({} if already_exists else {'a': '2'})
    assert result['task_ids'] == {'a': '1' if already_exists else '2'}


@pytest.mark.parametrize('field', ['title', 'body'])
def test_readback_compares_planned_intent(project, monkeypatch, field):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project)
    request = tp._task_request(plan, plan['tasks'][0])
    real = tp._owner_run
    def stale(root, config, args):
        if args[0] == 'external':
            card = {'task_id': 't_1', 'execution_kind': 'external_session',
                    'title': request['title'], 'body': request['body']}
            card[field] = 'Stale intent'
            return subprocess.CompletedProcess([], 0, json.dumps({'task': card}), '')
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', stale)
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok'] and result['state'] == 'partial'
    assert 'planned title/body' in result['error']
    assert result['created_task_ids'] == {'build': 't_1'}
    assert result['task_ids'] == {}
    assert not (project / '.atlas-ai/materializations.json').exists()


def test_first_row_write_failure_is_partial_even_without_created_ids(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    real = tp._owner_run
    def fail(root, config, args):
        if args[0] == 'materialize':
            return subprocess.CompletedProcess([], 3, '{"state":"conflict","reason":"mapping_card_started"}', '')
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', fail)
    result = tp.run_materialize(str(project), 'plan.json')
    assert result['state'] == 'partial' and result['reason'] == 'mapping_card_started'
    assert result['created_task_ids'] == result['task_ids'] == {}
    assert not (project / 'owner.sqlite').exists()


@pytest.mark.parametrize('missing', ['--fingerprint', '--pending-parent-proposed', '--prior-rows-file'])
def test_doctor_rejects_each_missing_option_after_real_reference(project, monkeypatch, missing):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_materialize(str(project), 'plan.json')['ok']
    real = tp._owner_run
    def incomplete(root, config, args):
        result = real(root, config, args)
        if args == ['materialize-check', '--help']:
            result.stdout = ' '.join(word for word in result.stdout.split() if word != missing)
        return result
    monkeypatch.setattr(tp, '_owner_run', incomplete)
    report = tp.run_doctor(str(project))
    assert report['provider']['reachable'] is True
    assert report['provider']['advertised_contract'] is False
    assert report['provider']['contract'] == 'UNKNOWN' and not report['ok']


def test_wrong_host_without_references_refuses(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    assert tp.run_configure(str(project), owner_host='different-owner.invalid')['ok']
    monkeypatch.setattr(tp.subprocess, 'run', lambda *a, **k: pytest.fail('wrong host owner called'))
    assert 'owner_host is not this host' in tp.run_materialize(str(project), 'plan.json')['error']


def test_explicit_config_required_even_with_resolved_defaults(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    config = tp.load_config(str(project))
    (project / '.atlas-workflow.json').unlink()
    monkeypatch.setattr(tp, 'load_config', lambda *args: config)
    monkeypatch.setattr(tp, '_owner_run', lambda *a: pytest.fail('unpersisted owner called'))
    assert 'persist an explicit provider config' in tp.run_materialize(str(project), 'plan.json')['error']


def test_check_created_reply_must_have_null_id(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    calls = []
    def wrote(root, config, args):
        calls.append(args[0])
        return subprocess.CompletedProcess([], 0, '{"state":"created","task_id":"t_written"}', '')
    monkeypatch.setattr(tp, '_owner_run', wrote)
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok'] and calls == ['materialize-check']
    assert 'incompatible' in result['error']
    assert not (project / '.atlas-ai/materializations.json').exists()


def test_shipped_skill_fresh_project_reaches_owner_without_optional_engine(project):
    # Execute the literal documented CLI commands, not a parallel hand-written flow.
    skill = (REPO / 'SKILL.md').read_text()
    generate = (REPO / 'phases/GENERATE.md').read_text()
    values = {'PYTHON': sys.executable, 'ATLAS_SCRIPT': str(REPO / 'script.py'),
              'PROJECT_ROOT': str(project), 'ATLAS_BOARD': 'fixture-board', 'ATLAS_PROJECT': 'demo'}
    (project / '.atlas-workflow.json').unlink()  # genuinely unconfigured project
    (project / '.atlas-ai').mkdir(exist_ok=True)
    (project / '.atlas-ai/candidates.json').write_text(json.dumps({'tasks': [candidate()]}))
    for text, marker in [(skill, 'atlas-kanban-setup'), (generate, 'atlas-kanban-materialize')]:
        if marker == 'atlas-kanban-materialize':
            doctor = subprocess.run([sys.executable, str(REPO / 'script.py'), 'doctor',
                                     '--project-root', str(project)], cwd=project.parent,
                                    env={'HOME': str(project), 'PATH': str(project)},
                                    capture_output=True, text=True, timeout=30)
            diagnostic = json.loads(doctor.stdout)
            assert doctor.returncode == 1
            assert diagnostic['config']['task_provider'] == 'atlas-kanban'
            assert diagnostic['provider']['reachable'] == 'UNKNOWN'
            assert not (project / 'owner.sqlite').exists()
        assert f'<!-- {marker} -->' in text
        block = text.split(f'<!-- {marker} -->', 1)[1].split('```bash\n', 1)[1].split('```', 1)[0]
        for line in block.strip().splitlines():
            argv = shlex.split(line)
            for key, value in values.items():
                argv = [arg.replace('$' + key, value) for arg in argv]
            response = subprocess.run(argv, cwd=project.parent,
                                      env={'HOME': str(project), 'PATH': str(project)},
                                      capture_output=True, text=True, timeout=30)
            assert response.returncode == 0, response.stdout + response.stderr
    from prd_taskmaster import task_provider as tp
    assert tp.run_doctor(str(project))['ok']
    assert len(cards(project)) == 1
    assert not (project / '.taskmaster').exists()


BRANCH_CONTRACTS = {
    'phases/HANDOFF.md': ('atlas-kanban handoff (default)',
                          ['workflow-status', 'doctor', 'reservation/external-session', 'partial']),
    'skills/go/SKILL.md': ('Provider-aware routing before file-mode pipeline state',
                           ['/prd:setup', '/prd:discover', '/prd:generate', '/prd:handoff', 'canonical IDs']),
    'skills/setup/SKILL.md': ('Task provider routing comes first',
                              ['provider-configure', 'doctor', 'Do not initialise', 'taskmaster-file']),
    'skills/discover/SKILL.md': ('Task provider routing comes first',
                                 ['approval', 'constraint', 'phases/GENERATE.md', 'do not call']),
    'skills/generate/SKILL.md': ('Task provider routing comes first',
                                 ['phases/GENERATE.md', '`plan`', '`materialize`', 'canonical readback']),
    'skills/handoff/SKILL.md': ('Task provider routing comes first',
                                ['phases/HANDOFF.md', 'workflow-status', 'doctor', 'reservation']),
}


@pytest.mark.parametrize('path', BRANCH_CONTRACTS)
def test_provider_branch_has_actionable_route_not_just_name(path):
    heading, requirements = BRANCH_CONTRACTS[path]
    text = (REPO / path).read_text()
    branch = text.split('## ' + heading + '\n', 1)[1].split('\n## ', 1)[0]
    assert 'atlas-kanban' in branch
    for requirement in requirements:
        assert requirement in branch, (path, requirement)
    if path == 'skills/handoff/SKILL.md':
        assert '  - Bash\n' in text.split('---', 2)[1]


def test_standalone_provider_gates_and_native_mode_are_conditional():
    text = (REPO / 'SKILL.md').read_text()
    generate = text.split('## Phase 3:', 1)[1].split('## Phase 4:', 1)[0]
    assert 'atlas-kanban: approved/validated spec, hashed plan' in generate
    assert 'taskmaster-file: PRD validated GOOD+' in generate
    native = generate.split('### Native Mode', 1)[1]
    assert 'taskmaster-file only' in native
    handoff = text.split('## Phase 4:', 1)[1].split('## Feedback', 1)[0]
    assert 'For atlas-kanban' in handoff and 'For taskmaster-file' in handoff


@pytest.mark.parametrize('reason', ['materialization_conflict', 'revision_requires_mapping',
                                   'mapping_card_started', 'logical_id_retired'])
def test_owner_conflict_reason_is_literal(project, monkeypatch, reason):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project)
    monkeypatch.setattr(tp, '_owner_run', lambda *a: subprocess.CompletedProcess(
        [], 3, json.dumps({'state': 'conflict', 'reason': reason, 'task_id': 't_1'}), ''))
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok'] and result['state'] == 'conflict'
    assert result['reason'] == reason and reason in result['error']


def test_missing_mapping_reports_owner_refusal_not_bad_id(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    monkeypatch.setattr(tp, '_owner_run', lambda *a: subprocess.CompletedProcess(
        [], 1, '{"state":"refused","reason":"mapping_not_found"}', ''))
    result = tp.run_materialize(str(project), 'plan.json')
    assert result['state'] == 'refused' and result['reason'] == 'mapping_not_found'
    assert result['error'] == 'mapping_not_found'
    assert 'task_id' not in result


def test_nonexistent_board_is_definitive_refusal(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    message = "kanban: board 'fixture-board' does not exist. Create it with `hermes kanban boards create fixture-board`."
    monkeypatch.setattr(tp, '_owner_run', lambda *a: subprocess.CompletedProcess([], 1, '', message + '\n'))
    result = tp.run_materialize(str(project), 'plan.json')
    assert result['state'] == 'refused' and result['reason'] == 'board_not_found'
    assert result['error'] == message
    assert 'uncertain' not in result['error']


def test_leading_dash_title_is_a_value(project):
    from prd_taskmaster import task_provider as tp
    save_plan(project, [{**candidate(), 'title': '-urgent'}])
    result = tp.run_materialize(str(project), 'plan.json')
    assert result['ok'], result
    assert len(cards(project)) == 1


def test_plan_check_refuses_every_row_before_first_create(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project, [candidate('m')])
    assert tp.run_materialize(str(project), 'plan.json')['ok']
    save_plan(project, [candidate('a-new'), {**candidate('m'), 'title': 'Changed intent'}])
    (project / '.atlas-ai/materializations.json').unlink()
    before = tree_hash(project)
    result = tp.run_materialize(str(project), 'plan.json')
    assert len(cards(project)) == 1  # no orphan a-new and no owner reference/event writes
    assert not result['ok'] and result['reason'] == 'revision_requires_mapping'
    assert result['state'] == 'conflict'
    assert tree_hash(project) == before


def test_side_effect_free_owner_check_includes_dependencies_and_mapping(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    old = save_plan(project)
    assert tp.run_materialize(str(project), 'plan.json')['ok']
    plan = save_plan(project, [candidate('a'), {**candidate(), 'dependencies': ['a']}],
                     previous_plan=old, prior_mapping={'build': 'build'})
    before = tree_hash(project)
    requests = []
    real = tp._owner_run
    def capture(root, config, args):
        assert args[0] == 'materialize-check'
        requests.append((args, Path(args[args.index('--body-file') + 1]).read_text()))
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', capture)
    tp._check_plan(project, tp.load_config(str(project)), plan)
    assert len(requests) == 2
    args, body = requests[1]
    assert args[args.index('--project') + 1] == 'demo'
    assert args[args.index('--plan-revision') + 1] == plan['plan_revision']
    assert args[args.index('--proposed-id') + 1] == 'build'
    assert args[args.index('--parent-proposed') + 1] == 'a'
    assert '--pending-parent-proposed=a' in args
    assert args[args.index('--maps-from') + 1] == old['plan_revision'] + ':build'
    assert '--title=' + plan['tasks'][1]['title'] in args
    assert args[args.index('--fingerprint') + 1] == plan['tasks'][1]['intent_fingerprint']
    assert args[args.index('--execution-kind') + 1] == 'external_session'
    assert 'Focused tests pass' in body
    assert tree_hash(project) == before
    assert len(cards(project)) == 1


def test_failure_after_check_is_partial_and_names_created_cards(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project, [candidate('a'), candidate('b')])
    real = tp._owner_run
    def fail_second(root, config, args):
        if args[0] == 'materialize' and '--proposed-id' in args and args[args.index('--proposed-id') + 1] == 'b':
            return subprocess.CompletedProcess([], 3, '{"state":"conflict","reason":"mapping_card_started","task_id":"t_changed"}', '')
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', fail_second)
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok'] and result['state'] == 'partial'
    assert result['reason'] == 'mapping_card_started'
    assert result['created_task_ids'] == {'a': 't_1'}
    assert result['task_ids'] == {'a': 't_1'}
    assert result['failed_proposed_task_id'] == 'b'
    assert len(cards(project)) == 1


def test_successful_write_with_bad_readback_still_names_possible_orphan(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    real = tp._owner_run
    def wrong_read(root, config, args):
        if args[0] == 'external':
            return subprocess.CompletedProcess([], 0, '{"task_id":"t_wrong","execution_kind":"worker"}', '')
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', wrong_read)
    result = tp.run_materialize(str(project), 'plan.json')
    assert result['state'] == 'partial'
    assert result['created_task_ids'] == {'build': 't_1'}
    assert result['task_ids'] == {}
    assert not (project / '.atlas-ai/materializations.json').exists()
    assert len(cards(project)) == 1


def test_nested_empty_taskmaster_directory_stays_new(tmp_path):
    from prd_taskmaster import task_provider as tp
    (tmp_path / '.taskmaster/tasks').mkdir(parents=True)
    before = tree_hash(tmp_path)
    assert tp.load_config(str(tmp_path))['task_provider'] == 'atlas-kanban'
    assert tree_hash(tmp_path) == before


def test_check_sends_prior_rows_in_writer_order(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    from prd_taskmaster.plan_output import ordered_tasks
    plan = save_plan(project, [candidate('a', ['z']), candidate('m'), candidate('z')])
    ordered = ordered_tasks(plan['tasks'])
    alternate_temp = project / 'default-temp'
    alternate_temp.mkdir()
    monkeypatch.setattr(tp.tempfile, 'tempdir', str(alternate_temp))
    assert Path(tp.tempfile.gettempdir()) == alternate_temp
    seen = []
    real = tp._owner_run
    def capture(root, config, args):
        assert '--prior-rows-file' in args, args
        path = Path(args[args.index('--prior-rows-file') + 1])
        assert path.parent.parent == Path('/tmp')
        assert Path(args[args.index('--body-file') + 1]).parent == path.parent
        seen.append((path, json.loads(path.read_text())))
        return real(root, config, args)
    monkeypatch.setattr(tp, '_owner_run', capture)
    tp._check_plan(project, tp.load_config(str(project)), plan)
    assert len(seen) == 3
    assert [rows for _, rows in seen] == [[tp._task_request(plan, t) for t in ordered[:i]] for i in range(3)]
    assert all(not path.exists() for path, _ in seen)
    assert not (project / 'owner.sqlite').exists()


@pytest.mark.parametrize('reason,code,state', [
    ('revision_requires_mapping', 3, 'conflict'), ('mapping_card_started', 3, 'conflict'),
    ('logical_id_retired', 3, 'conflict'), ('mapping_not_found', 1, 'refused')])
def test_per_card_seam_also_preserves_literal_refusals(project, monkeypatch, reason, code, state):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project)
    monkeypatch.setattr(tp, '_owner_run', lambda *a: subprocess.CompletedProcess(
        [], code, json.dumps({'state': state, 'reason': reason}), ''))
    with pytest.raises(tp.CommandError) as refusal:
        tp._materialize_card(project, tp.load_config(str(project)), plan, plan['tasks'][0])
    assert refusal.value.extra == {'state': state, 'reason': reason}
    assert str(refusal.value) == reason


def test_check_unavailable_never_falls_through_to_create(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    save_plan(project)
    calls = []
    def unavailable(root, config, args):
        calls.append(args)
        return subprocess.CompletedProcess([], 2, '', 'unsupported command')
    monkeypatch.setattr(tp, '_owner_run', unavailable)
    result = tp.run_materialize(str(project), 'plan.json')
    assert not result['ok']
    assert [args[0] for args in calls] == ['materialize-check']
    assert not (project / 'owner.sqlite').exists()
    assert not (project / '.atlas-ai/materializations.json').exists()


@pytest.mark.parametrize('parent_id', [None, 't_parent'])
def test_row_preflight_projects_new_and_existing_parent_ids(project, monkeypatch, parent_id):
    from prd_taskmaster import task_provider as tp
    plan = save_plan(project, [candidate('a'), candidate('b', ['a'])])
    calls = []
    def check(root, config, args):
        calls.append(args)
        payload = {'state': 'created', 'task_id': None}
        if len(calls) == 1 and parent_id:
            payload = {'state': 'existing', 'task_id': parent_id}
        return subprocess.CompletedProcess([], 0, json.dumps(payload), '')
    monkeypatch.setattr(tp, '_owner_run', check)
    before = tree_hash(project)
    tp._check_plan(project, tp.load_config(str(project)), plan)
    assert len(calls) == 2
    assert all(args[0] == 'materialize-check' for args in calls)
    expected = '--pending-parent-proposed=a' + ('=' + parent_id if parent_id else '')
    assert expected in calls[1]
    assert tree_hash(project) == before


@pytest.mark.parametrize('module,old,new,selection', [
    ('prd_taskmaster/task_provider.py', 'any(path.is_file() for path in taskmaster.rglob("*"))',
     'taskmaster.exists()', 'only_an_existing_taskmaster_file_selects_legacy'),
    ('SKILL.md', '"$PYTHON" "$ATLAS_SCRIPT" provider-configure --project-root "$PROJECT_ROOT" --board "$ATLAS_BOARD"',
     '"$PYTHON" "$ATLAS_SCRIPT" init-project', 'shipped_skill_fresh_project'),
    ('prd_taskmaster/task_provider.py', 'extra = {"state": state, "reason": reason}',
     'extra = {"state": state}', 'owner_conflict_reason_is_literal'),
    ('prd_taskmaster/task_provider.py', '(result.returncode != 0 and state == "refused")',
     'False', 'missing_mapping_reports_owner_refusal'),
    ('prd_taskmaster/task_provider.py', 'result.returncode == 1 and result.stderr.strip() == missing_board',
     'False', 'nonexistent_board_is_definitive_refusal'),
    ('prd_taskmaster/task_provider.py', '"--title=" + task["title"]',
     '"--title", task["title"]', 'leading_dash_title_is_a_value'),
    ('prd_taskmaster/task_provider.py', '        _check_plan(root, config, plan)',
     '        pass  # removed owner plan check', 'plan_check_refuses_every_row_before_first_create'),
    ('prd_taskmaster/task_provider.py', 'for proposed, task_id in (pending_parents or {}).items():',
     'for proposed, task_id in {}.items():', 'row_preflight_projects_new_and_existing_parent_ids'),
    ('prd_taskmaster/task_provider.py', '**extra, "state": "partial"',
     '**extra, "state": "conflict"', 'failure_after_check_is_partial'),
])
def test_second_harvest_mutations(tmp_path, module, old, new, selection):
    run_mutation(tmp_path, module, old, new, selection)


def run_mutation(tmp_path, module, old, new, selection, test_file='test_task_provider_repairs.py'):
    export = tmp_path / 'export'
    export.mkdir()
    for directory in ['prd_taskmaster', 'phases', 'skills']:
        shutil.copytree(REPO / directory, export / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (export / 'tests/core').mkdir(parents=True)
    for file in ['script.py', 'SKILL.md', 'tests/__init__.py', 'tests/core/__init__.py',
                 'tests/core/test_plan_output.py', 'tests/core/test_task_provider.py',
                 'tests/core/test_task_provider_repairs.py']:
        shutil.copy2(REPO / file, export / file)
    source = export / module
    original = source.read_text()
    assert original.count(old) == 1
    source.write_text(original.replace(old, new))
    response = subprocess.run([sys.executable, '-m', 'pytest',
                               'tests/core/' + test_file, '-q', '--tb=short',
                               '--basetemp', str(export / 'nested-tmp'),
                               '-k', f'({selection}) and not mutations and not removed_guard_turns_proof_red'],
                              cwd=export, env={'HOME': str(export), 'PATH': '',
                                              'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                              capture_output=True, text=True, timeout=60)
    assert response.returncode == 1, response.stdout + response.stderr
    assert 'failed' in response.stdout and 'ERROR' not in response.stdout, response.stdout
    print(f'MUTATION CAUGHT {selection}: {response.stdout.splitlines()[-1]}')


def test_owner_run_scrubs_db_pin(project, monkeypatch):
    from prd_taskmaster import task_provider as tp
    monkeypatch.setenv('HERMES_KANBAN_DB', str(project / 'other-board.db'))
    seen = []
    def capture(args, **kwargs):
        seen.append(kwargs['env'])
        assert 'HERMES_KANBAN_DB' not in kwargs['env']
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(tp.subprocess, 'run', capture)
    config = tp.load_config(str(project))
    for args in [['materialize-check'], ['materialize'], ['external', 'status'], ['materialize-check', '--help']]:
        tp._owner_run(project, config, args)
    assert len(seen) == 4


THIRD_MUTANTS = [
    ('partial-only-if-created', '**extra, "state": "partial",',
     '**extra, "state": "partial" if created else "conflict",', 'first_row_write_failure'),
    ('doctor-ignores-help', 'advertised = advertised and result.returncode == 0 and all(o in result.stdout.split() for o in options)',
     'advertised = advertised and result.returncode == 0', 'doctor_rejects_each_missing_option'),
    ('R:doctor-drop-pending-flag', '"--body-file", "--parent-proposed", "--pending-parent-proposed", "--maps-from"',
     '"--body-file", "--parent-proposed", "--maps-from"', 'doctor_rejects_each_missing_option'),
    ('wrong-host-allowed', 'if config["owner_host"] not in {socket.gethostname(), "localhost"}:',
     'if False:', 'wrong_host_without_references'),
    ('no-explicit-config-needed', 'if not _config_path(root).is_file():', 'if False:', 'explicit_config_required'),
    ('R:check-ignores-null-rule', 'if check and payload.get("state") == "created" and payload.get("task_id", "missing") is None:',
     'if check and payload.get("state") == "created":', 'check_created_reply_must_have_null_id'),
    ('R:check-accepts-created-id', '({"existing", "mapped"} if check else {"created", "existing", "mapped"})',
     '{"created", "existing", "mapped"}', 'check_created_reply_must_have_null_id'),
    ('db-pin-scrub-removed', 'env={key: value for key, value in os.environ.items() if key != "HERMES_KANBAN_DB"}',
     'env=dict(os.environ)', 'owner_run_scrubs_db_pin'),
    ('title-body-readback-removed', 'if expected is not None and any(card.get(field) != expected[field] for field in ("title", "body")):',
     'if False:', 'readback_compares_planned_intent'),
    ('native-created-record-removed', 'if entry.pop("created"):', 'if entry.pop("created") and False:',
     'file_partial_names_only_newly_created'),
    ('file-mode-calls-check', '    if config["task_provider"] == "atlas-kanban":\n        _check_plan(root, config, plan)',
     '    if True:\n        _check_plan(root, config, plan)', 'file_partial_names_only_newly_created'),
    ('drop-readback-created', 'created.update(extra.get("created_task_ids", {}))', 'pass',
     'successful_write_with_bad_readback_still_names'),
    ('drop-created-record', 'if entry.pop("owner_state") == "created":', 'if entry.pop("owner_state") == "never":',
     'failure_after_check_is_partial_and_names'),
    ('R:null-parent-ids', 'checked[task["proposed_task_id"]] = payload["task_id"]',
     'checked[task["proposed_task_id"]] = None', 'row_preflight_projects_new_and_existing_parent_ids'),
    ('R:check-really-writes', '"materialize-check" if check else "materialize"', '"materialize"',
     'side_effect_free_owner_check_includes'),
]


@pytest.mark.parametrize('name,old,new,selection', THIRD_MUTANTS, ids=[row[0] for row in THIRD_MUTANTS])
def test_third_harvest_mutations(tmp_path, name, old, new, selection):
    run_mutation(tmp_path, 'prd_taskmaster/task_provider.py', old, new, selection)


@pytest.mark.parametrize('name,old,new,selection', [
    ('skip-external-kind-readback', 'if card.get("execution_kind") != "external_session":', 'if False:',
     'doctor_reachability_requires_successful_real_read and wrong-kind'),
    ('drop-card-readback', '        _read_card(root, config, payload["task_id"], request)', '        pass',
     'owner_write_is_read_back_before_recording_reference'),
    ('local-cache-decides', 'prior_ids = _check_revisions(refs, plan, config["task_provider"] == "atlas-kanban")',
     'prior_ids = _check_revisions(refs, plan, False)', 'mapping_reuses_card_and_replay_is_existing'),
    ('legacy-never', 'legacy = any(path.is_file() for path in taskmaster.rglob("*"))', 'legacy = False',
     'default_and_legacy_selection_are_read_only'),
    ('drop-maps-from-write', 'args.extend(["--maps-from", plan["prior_plan_revision"] + ":" + prior_id])', 'pass',
     'mapping_reuses_card_and_replay_is_existing'),
])
def test_retained_harvest_mutations(tmp_path, name, old, new, selection):
    run_mutation(tmp_path, 'prd_taskmaster/task_provider.py', old, new, selection, 'test_task_provider.py')


@pytest.mark.parametrize('path', BRANCH_CONTRACTS)
def test_gutted_skill_branch_mutations(tmp_path, path):
    heading, _ = BRANCH_CONTRACTS[path]
    original = (REPO / path).read_text().split('## ' + heading + '\n', 1)[1].split('\n## ', 1)[0]
    # Preserve the provider word and heading, remove the actionable branch.
    run_mutation(tmp_path, path, original, '\natlas-kanban\n', 'provider_branch_has_actionable_route_not_just_name')
