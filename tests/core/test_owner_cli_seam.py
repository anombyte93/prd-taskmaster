"""Optional real-owner seam, never the installed owner or a production home."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile

import pytest

from tests.core.test_plan_output import candidate
from tests.core.test_task_provider import save_plan

OWNER_COMMIT = '1612064424681e49cf121e20d4b68e0def852d26'
SOURCE = os.environ.get('ATLAS_TEST_HERMES_SOURCE')


@pytest.fixture
def owner(tmp_path, monkeypatch):
    if not SOURCE:
        if os.environ.get('ATLAS_REQUIRE_OWNER_SEAM') == '1':
            pytest.fail('real-owner seam is required; ATLAS_TEST_HERMES_SOURCE missing')
        pytest.skip('requires an explicit Hermes source checkout for git archive')
    export = tmp_path / 'owner-export'
    export.mkdir()
    archive = tmp_path / 'owner.tar'
    subprocess.run(['git', '-C', SOURCE, 'archive', '--format=tar', OWNER_COMMIT,
                    '-o', str(archive)], check=True, capture_output=True, text=True)
    with tarfile.open(archive) as source:
        source.extractall(export, filter='data')
    root = tmp_path / 'project'
    root.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    python = os.environ.get('ATLAS_TEST_HERMES_PYTHON', sys.executable)
    entry = tmp_path / 'hermes'
    entry.write_text(f'''#!{python}
import faulthandler, os, sys, types
from pathlib import Path
faulthandler.dump_traceback_later(10, repeat=True)
sys.path.insert(0, {str(export)!r})
# Source-checkout dotenv fallback can read secrets despite a disposable HOME.
# Replace ONLY that unrelated loader; the real CLI/parser/kernel/SQLite run.
loader = types.ModuleType("hermes_cli.env_loader")
loader.load_hermes_dotenv = lambda **kw: None
sys.modules["hermes_cli.env_loader"] = loader
from hermes_cli import _early_recovery
_early_recovery.recover_if_needed = lambda: None
from hermes_cli.main import main
main()
''')
    entry.chmod(0o700)
    env = {'HOME': str(home), 'HERMES_HOME': str(home / '.hermes'),
           'PATH': str(tmp_path), 'XDG_CONFIG_HOME': str(home / '.config'),
           'XDG_CACHE_HOME': str(home / '.cache'), 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(tmp_path)}
    # No inherited profile, board, task, DB, dotenv or authentication route.
    def cli(*args, code=0):
        try:
            result = subprocess.run([str(entry), 'kanban', *args], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            pytest.fail(f'owner startup timed out: {exc.stderr!r}')
        assert result.returncode == code, result.stdout + result.stderr
        return result
    assert cli('boards', 'create', 'fixture-board').returncode == 0
    # Whitelist the plugin process too: _owner_run inherits only this disposable
    # HOME/PATH/owner home, never the dispatcher's auth or live-board environment.
    for key in list(os.environ):
        monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return root, home, env, cli


def test_real_hermes_cli_reasons_identity_and_dash_values(owner):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    config = tp.load_config(str(root))
    # Exercise the existing per-row writer seam first, then the complete
    # preflight/materialize integration below. No installed/live owner is used.
    old = save_plan(root, [{**candidate(), 'title': '-urgent'}])
    def materialize(plan):
        return tp._materialize_card(root, config, plan, plan['tasks'][0])
    first = materialize(old)
    assert first['owner_state'] == 'created'
    status = tp.run_status(str(root), first['task_id'])
    assert status['task']['title'] == '-urgent'
    assert materialize(old)['task_id'] == first['task_id']
    forged = json.loads(json.dumps(old))
    forged['tasks'][0]['intent_fingerprint'] = 'changed-in-same-revision'
    with pytest.raises(tp.CommandError) as conflict:
        materialize(forged)
    assert conflict.value.extra['reason'] == 'materialization_conflict'
    unchanged = save_plan(root, [old['tasks'][0], candidate('extra')])
    assert materialize(unchanged)['task_id'] == first['task_id']
    changed = save_plan(root, [{**candidate(), 'title': 'Changed'}])
    with pytest.raises(tp.CommandError) as mapping:
        materialize(changed)
    assert mapping.value.extra['reason'] == 'revision_requires_mapping'
    mapped = save_plan(root, [{**candidate(), 'title': 'Changed'}],
                       previous_plan=old, prior_mapping={'build': 'build'})
    assert materialize(mapped)['task_id'] == first['task_id']
    assert materialize(mapped)['owner_state'] == 'existing'
    renamed = save_plan(root, [candidate('renamed')], previous_plan=mapped,
                        prior_mapping={'build': 'renamed'})
    assert materialize(renamed)['task_id'] == first['task_id']
    missing = json.loads(json.dumps(renamed))
    missing['plan_revision'] = 'missing-map-revision'
    missing['prior_plan_revision'] = 'missing'
    with pytest.raises(tp.CommandError) as refusal:
        materialize(missing)
    assert refusal.value.extra == {'state': 'refused', 'reason': 'mapping_not_found'}
    with pytest.raises(tp.CommandError) as absent:
        tp._materialize_card(root, {**config, 'board': 'absent'}, old, old['tasks'][0])
    assert absent.value.extra['reason'] == 'board_not_found'
    assert 'does not exist' in str(absent.value) and 'uncertain' not in str(absent.value)
    # Original buggy argv really exits 2, corrected --title=value created a card.
    original = cli('--board', 'fixture-board', 'materialize', '--project', 'probe',
                   '--plan-revision', 'r', '--proposed-id', 'dash', '--fingerprint', 'f',
                   '--title', '-urgent', '--execution-kind', 'external_session', '--json', code=2)
    assert 'expected one argument' in original.stderr

    def owner_counts():
        counts = {}
        for database in home.rglob('kanban.db'):
            with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as conn:
                counts[str(database)] = [conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                                         for table in ['tasks', 'task_materializations', 'task_events']]
        assert counts
        return counts

    first_plan = save_plan(root, [candidate('m')])
    first_run = tp.run_materialize(str(root), 'plan.json')
    assert first_run['ok'], first_run
    m_id = first_run['task_ids']['m']
    (root / '.atlas-ai/materializations.json').unlink()
    save_plan(root, [candidate('a-new'), {**candidate('m'), 'title': 'Changed'}])
    before = owner_counts()
    refused = tp.run_materialize(str(root), 'plan.json')
    assert refused['state'] == 'conflict' and refused['reason'] == 'revision_requires_mapping'
    assert owner_counts() == before  # real owner: no a-new card, reference or event
    assert not (root / '.atlas-ai/materializations.json').exists()

    # New parent (null preview ID), then existing parent (canonical preview ID).
    new_parent_plan = save_plan(root, [candidate('p'), {**candidate('m', ['p']), 'title': 'Mapped'}],
                                previous_plan=first_plan, prior_mapping={'m': 'm'})
    before = owner_counts()
    tp._check_plan(root, config, new_parent_plan)
    assert owner_counts() == before
    mapped_run = tp.run_materialize(str(root), 'plan.json')
    assert mapped_run['ok'] and mapped_run['task_ids']['m'] == m_id, mapped_run
    assert tp.run_status(str(root), m_id)['task']['title'] == 'Mapped'
    save_plan(root, [candidate('p'), {**candidate('m', ['p']), 'title': 'Mapped again'}],
              previous_plan=new_parent_plan, prior_mapping={'p': 'p', 'm': 'm'})
    existing_parent_run = tp.run_materialize(str(root), 'plan.json')
    assert existing_parent_run['ok'] and existing_parent_run['task_ids'] == mapped_run['task_ids'], existing_parent_run
    assert tp.run_doctor(str(root))['ok']
    print('REAL OWNER: ruling-6 identity, literal reasons/title, complete row preflight, no-orphan refusal, new/existing pending parents and mapped intent verified; temp homes only')


def database(home, board='fixture-board'):
    return home / '.hermes/kanban/boards' / board / 'kanban.db'


def count_cards(home, board='fixture-board'):
    path = database(home, board)
    if not path.exists():
        return 0
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        return db.execute('SELECT count(*) FROM tasks').fetchone()[0]


@pytest.mark.parametrize('prior,successor,new_id', [('k', 'z', 'a-orphan'), ('zk', 'ay', '0-new')])
def test_real_owner_keep_and_map_refuses_before_any_create(owner, prior, successor, new_id):
    from prd_taskmaster import task_provider as tp
    from prd_taskmaster.plan_output import build_plan, content_hash
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    old = save_plan(root, [candidate(prior)])
    assert tp.run_materialize(str(root), 'plan.json')['ok']
    body = build_plan('demo', [candidate(new_id), candidate(prior), candidate(successor)])
    body.pop('plan_revision')
    body.update(prior_plan_revision=old['plan_revision'], prior_mapping={prior: successor})
    (root / 'plan.json').write_text(json.dumps({**body, 'plan_revision': content_hash(body)}))
    (root / '.atlas-ai/materializations.json').unlink()
    before = count_cards(home)
    result = tp.run_materialize(str(root), 'plan.json')
    print('D2', prior, result, 'cards added', count_cards(home) - before)
    assert not result['ok'] and 'prior logical id remains' in result['error']
    assert count_cards(home) == before
    assert not (root / '.atlas-ai/materializations.json').exists()


def test_real_owner_renamed_plan_replays_and_continues_chain(owner):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    previous = save_plan(root, [candidate('x')])
    initial = tp.run_materialize(str(root), 'plan.json')
    assert initial['ok'], initial
    card_id = initial['task_ids']['x']
    for prior, successor in [('x', 'y'), ('y', 'z')]:
        previous = save_plan(root, [candidate(successor)], previous_plan=previous,
                             prior_mapping={prior: successor})
        first = tp.run_materialize(str(root), 'plan.json')
        replay = tp.run_materialize(str(root), 'plan.json')
        assert first['ok'] and replay['ok'], (prior, successor, first, replay)
        assert first['task_ids'] == replay['task_ids'] == {successor: card_id}
        assert count_cards(home) == 1


def test_real_owner_scrubs_inherited_db_pin(owner, monkeypatch):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    cli('boards', 'create', 'otherb')
    monkeypatch.setenv('HERMES_KANBAN_DB', str(database(home, 'otherb')))
    monkeypatch.setenv('HERMES_KANBAN_BOARD', 'otherb')
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    save_plan(root)
    result = tp.run_materialize(str(root), 'plan.json')
    doctor = tp.run_doctor(str(root))
    print('D3', result, 'named cards', count_cards(home), 'other cards', count_cards(home, 'otherb'))
    assert result['ok'] and doctor['ok']
    assert count_cards(home) == 1 and count_cards(home, 'otherb') == 0


def test_real_owner_reverting_old_fingerprint_is_not_false_success(owner):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    a = save_plan(root, [{**candidate(), 'title': 'Version A', 'description': 'A body'}])
    first = tp.run_materialize(str(root), 'plan.json')
    assert first['ok'], first
    b = save_plan(root, [{**candidate(), 'title': 'Version B', 'description': 'B body'}],
                  previous_plan=a, prior_mapping={'build': 'build'})
    assert tp.run_materialize(str(root), 'plan.json')['ok']
    save_plan(root, a['tasks'], previous_plan=b, prior_mapping={'build': 'build'})
    (root / '.atlas-ai/materializations.json').unlink()
    result = tp.run_materialize(str(root), 'plan.json')
    card = tp.run_status(str(root), first['task_ids']['build'])['task']
    print('D4', result, 'actual title', card['title'])
    # The current owner applies the mapped A intent instead of replaying stale B.
    assert result['ok'] and result['task_ids'] == first['task_ids'], result
    assert card['title'] == 'Version A' and card['body'].startswith('A body\n')
    assert count_cards(home) == 1

    # Dependency-only A -> B -> A must restore readiness too, not just text.
    dep_a = save_plan(root, [candidate('child'), candidate('parent')])
    dep_first = tp.run_materialize(str(root), 'plan.json')
    assert dep_first['ok'], dep_first
    dep_b = save_plan(root, [candidate('child', ['parent']), candidate('parent')],
                      previous_plan=dep_a, prior_mapping={'child': 'child', 'parent': 'parent'})
    assert tp.run_materialize(str(root), 'plan.json')['ok']
    child = dep_first['task_ids']['child']
    assert tp.run_status(str(root), child)['task']['status'] == 'todo'
    save_plan(root, dep_a['tasks'], previous_plan=dep_b,
              prior_mapping={'child': 'child', 'parent': 'parent'})
    assert tp.run_materialize(str(root), 'plan.json')['ok']
    assert tp.run_status(str(root), child)['task']['status'] == 'ready'
    assert count_cards(home) == 3


def test_real_owner_dependency_reversal_agrees_with_writer(owner, monkeypatch):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    old = save_plan(root, [candidate('m'), candidate('p', ['m'])])
    first = tp.run_materialize(str(root), 'plan.json')
    assert first['ok'], first
    revised = save_plan(root, [candidate('m', ['p']), candidate('p')],
                        previous_plan=old, prior_mapping={'m': 'm', 'p': 'p'})
    (root / '.atlas-ai/materializations.json').unlink()
    before = count_cards(home)
    config = tp.load_config(str(root))
    by_id = {t['proposed_task_id']: t for t in revised['tasks']}
    # Negative control: the additive input is necessary. The same check with
    # only pending IDs still sees the old p -> m edge and refuses m -> p.
    run = tp._owner_run
    def without_prior(root, config, args):
        if '--prior-rows-file' in args:
            index = args.index('--prior-rows-file')
            args = args[:index] + args[index + 2:]
        return run(root, config, args)
    with monkeypatch.context() as control:
        control.setattr(tp, '_owner_run', without_prior)
        preview = tp._materialize_card(root, config, revised, by_id['p'], check=True)
        with pytest.raises(tp.CommandError) as refusal:
            tp._materialize_card(root, config, revised, by_id['m'], check=True,
                                 pending_parents={'p': preview['task_id']})
    assert refusal.value.extra == {'state': 'refused', 'reason': 'mapping_dependency_cycle'}
    assert count_cards(home) == before
    assert not (root / '.atlas-ai/materializations.json').exists()
    replies = []
    run = tp._owner_run
    def record(root, config, args):
        reply = run(root, config, args)
        if args[0] in {'materialize-check', 'materialize'}:
            replies.append((args[0], json.loads(reply.stdout)))
        return reply
    monkeypatch.setattr(tp, '_owner_run', record)
    result = tp.run_materialize(str(root), 'plan.json')
    print('REVERSAL', result, replies)
    assert result['ok'] and result['task_ids'] == first['task_ids'], result
    assert [reply['state'] for op, reply in replies if op == 'materialize-check'] == ['mapped', 'mapped']
    assert [reply['state'] for op, reply in replies if op == 'materialize'] == ['mapped', 'mapped']
    assert all('reason' not in reply for _, reply in replies)
    assert count_cards(home) == before
    with sqlite3.connect(database(home).as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT parent_id,child_id FROM task_links').fetchall() == [
            (first['task_ids']['p'], first['task_ids']['m'])]


def test_real_owner_shipped_skill_literal_commands(owner):
    import shlex
    from tests.core.test_task_provider import REPO
    root, home, env, cli = owner
    (root / '.atlas-ai').mkdir()
    (root / '.atlas-ai/candidates.json').write_text(json.dumps({'tasks': [candidate()]}))
    values = {'PYTHON': sys.executable, 'ATLAS_SCRIPT': str(REPO / 'script.py'),
              'PROJECT_ROOT': str(root), 'ATLAS_BOARD': 'fixture-board', 'ATLAS_PROJECT': 'demo'}
    for path, marker in [('SKILL.md', 'atlas-kanban-setup'),
                         ('phases/GENERATE.md', 'atlas-kanban-materialize')]:
        text = (REPO / path).read_text()
        block = text.split(f'<!-- {marker} -->', 1)[1].split('```bash\n', 1)[1].split('```', 1)[0]
        for line in block.strip().splitlines():
            argv = shlex.split(line)
            for key, value in values.items():
                argv = [arg.replace('$' + key, value) for arg in argv]
            result = subprocess.run(argv, cwd=root.parent, env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            print('SKILL COMMAND', argv, result.returncode)
    from prd_taskmaster import task_provider as tp
    task_id = json.loads((root / '.atlas-ai/materializations.json').read_text())['revisions']
    task_id = next(iter(next(iter(task_id.values())).values()))['task_id']
    for args in [('workflow-status', '--task', task_id), ('doctor',)]:
        result = subprocess.run([sys.executable, str(REPO / 'script.py'), *args,
                                 '--project-root', str(root)], cwd=root.parent, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        print('SKILL HANDOFF', args, json.loads(result.stdout)['ok'])
    assert count_cards(home) == 1 and not (root / '.taskmaster').exists()


def test_mcp_stdio_end_to_end_against_real_owner(owner):
    import asyncio
    from datetime import timedelta
    pytest.importorskip('mcp')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from tests.core.test_task_provider import REPO
    root, home, env, cli = owner
    (root / 'candidates.json').write_text(json.dumps({'tasks': [candidate()]}))

    async def walk():
        server = StdioServerParameters(command=sys.executable,
                                       args=[str(REPO / 'mcp-server/server.py')],
                                       env=env, cwd=str(root))
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
                await client.initialize()
                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert {'provider_configure', 'plan', 'materialize', 'doctor', 'workflow_status'} <= tools
                async def call(name, **arguments):
                    reply = await client.call_tool(name, arguments)
                    assert not reply.isError, reply
                    payload = json.loads(reply.content[0].text)
                    print('MCP STDIO', name, payload.get('ok'), payload.get('task_ids'))
                    return payload
                assert (await call('provider_configure', project_root=str(root), board='fixture-board'))['ok']
                before = await call('doctor', project_root=str(root))
                assert before['provider']['reachable'] == 'UNKNOWN'
                assert (await call('plan', project_root=str(root), project='demo', input_path='candidates.json'))['ok']
                first = await call('materialize', project_root=str(root), plan_path='.atlas-ai/plan.json')
                replay = await call('materialize', project_root=str(root), plan_path='.atlas-ai/plan.json')
                assert first['ok'] and replay['task_ids'] == first['task_ids']
                task_id = first['task_ids']['build']
                status = await call('workflow_status', project_root=str(root), task_id=task_id)
                assert status['ok'] and status['task']['execution_kind'] == 'external_session'
                assert (await call('doctor', project_root=str(root)))['ok']
    asyncio.run(walk())
    assert count_cards(home) == 1 and not (root / '.taskmaster').exists()


@pytest.mark.parametrize('key,changes', [('padded', {'title': '  padded title  '}),
                                        ('crlf', {'description': 'line one\r\nline two'})])
def test_real_owner_padded_title_and_crlf_converge(owner, key, changes):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    save_plan(root, [{**candidate(key), **changes}])
    first = tp.run_materialize(str(root), 'plan.json')
    replay = tp.run_materialize(str(root), 'plan.json')
    print('CANONICAL', key, first, replay)
    assert first['ok'] and replay['ok'], (first, replay)
    assert first['task_ids'] == replay['task_ids']
    assert count_cards(home) == 1


def test_real_owner_clean_text_is_preserved(owner):
    from prd_taskmaster import task_provider as tp
    root, home, env, cli = owner
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    text = 'Unicode 雪\nembedded newline\twith tab and trailing whitespace  \n'
    plan = save_plan(root, [{**candidate(), 'title': '雪\nTitle\twith tab',
                             'description': text, 'acceptance': [text]}])
    first = tp.run_materialize(str(root), 'plan.json')
    replay = tp.run_materialize(str(root), 'plan.json')
    assert first['ok'] and replay['ok'], (first, replay)
    assert replay['task_ids'] == first['task_ids'] and count_cards(home) == 1
    card = tp.run_status(str(root), first['task_ids']['build'])['task']
    request = tp._task_request(plan, plan['tasks'][0])
    assert card['title'] == request['title'] and card['body'] == request['body']
    assert text in card['body']
