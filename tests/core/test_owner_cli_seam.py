"""Optional real-owner seam, never the installed owner or a production home."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.core.test_plan_output import candidate
from tests.core.test_task_provider import save_plan

SOURCE = os.environ.get('ATLAS_TEST_HERMES_SOURCE')
pytestmark = pytest.mark.skipif(not SOURCE, reason='requires an explicit disposable-source Hermes checkout')


def test_real_hermes_cli_reasons_identity_and_dash_values(tmp_path, monkeypatch):
    from prd_taskmaster import task_provider as tp
    root = tmp_path / 'project'
    root.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    python = os.environ.get('ATLAS_TEST_HERMES_PYTHON', sys.executable)
    entry = tmp_path / 'hermes'
    entry.write_text(f'''#!{python}
import os, sys, types
from pathlib import Path
sys.path.insert(0, {str(SOURCE)!r})
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
           'XDG_CACHE_HOME': str(home / '.cache'), 'LANG': 'C.UTF-8'}
    # No inherited profile, board, task, DB, dotenv or authentication route.
    def cli(*args, code=0):
        result = subprocess.run([str(entry), 'kanban', *args], cwd=root, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == code, result.stdout + result.stderr
        return result
    assert cli('boards', 'create', 'fixture-board').returncode == 0
    for key in list(os.environ):
        if key.startswith('HERMES_'):
            monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert tp.run_configure(str(root), board='fixture-board')['ok']
    config = tp.load_config(str(root))
    # Owner a057781 predates ruling 13. Exercise the existing per-row seam,
    # not a fake fallback that would claim plan-check conformance.
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
    print('REAL OWNER: five ruling-6 cases, renamed mapping/replay, mapping_not_found, missing board, leading-dash title verified; temp homes only')
