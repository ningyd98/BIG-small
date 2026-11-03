"""R415 continuation after a proven natural parent exit; no node retry."""
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
HERE = Path(__file__).resolve().parent
R413 = HERE.parent / 'round413-full-long-validation-20261103'
R414 = HERE.parent / 'round414-workbench-db-scope-preflight-handoff-20261103'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def identity_alive(pid, starttime):
    try:
        stat = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return False
    return int(stat[stat.rfind(')') + 2:].split()[19]) == int(starttime)


def event_rows(directory):
    path = directory / 'pytest-events.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def fresh(original, identity, nodes=None):
    spec = deepcopy(original)
    old = spec['directory']
    new = str(HERE / 'implementation' / identity)
    spec['id'] = identity
    spec['directory'] = new
    selected = original.get('nodes', []) if nodes is None else nodes
    args = [arg.replace(old, new) for arg in original['argv']]
    if nodes is not None:
        args = [arg for arg in args if arg not in original['nodes']] + selected
        spec['nodes'] = selected
        spec['parent_stage'] = original['id']
        spec['continue_unstarted'] = False
        spec['timeout_s'] = original['tail_timeout_s']
    basetemp = '/tmp/bigsmall-r415-' + identity
    assert not Path(basetemp).exists()
    spec['argv'] = ['--basetemp=' + basetemp if arg.startswith('--basetemp=') else arg for arg in args]
    spec['env'] = {key: value.replace(old, new) for key, value in original['env'].items()}
    # Reverse path normalization proves all unselected flags and environment unchanged.
    normalized = deepcopy(spec)
    normalized['id'] = original['id']
    normalized['directory'] = old
    normalized['env'] = {key: value.replace(new, old) for key, value in spec['env'].items()}
    normalized['argv'] = [arg.replace(new, old) for arg in spec['argv']]
    original_basetemp = next(arg for arg in original['argv'] if arg.startswith('--basetemp='))
    normalized['argv'] = [original_basetemp if arg.startswith('--basetemp=') else arg for arg in normalized['argv']]
    expected = deepcopy(original)
    if nodes is not None:
        expected['nodes'] = selected
        expected['argv'] = [arg for arg in original['argv'] if arg not in original['nodes']] + selected
        expected['parent_stage'] = original['id']
        expected['continue_unstarted'] = False
        expected['timeout_s'] = original['tail_timeout_s']
    assert normalized == expected
    directory = Path(new)
    directory.mkdir(parents=True, exist_ok=False)
    for name in spec.get('resource_dirs', []):
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert (directory / relative).resolve().is_relative_to(directory.resolve())
        (directory / relative).mkdir(parents=True, exist_ok=True)
    save(HERE / 'specs' / (identity + '.json'), spec)
    return spec


def main():
    assert sha(HERE / 'plan.json') == '64f939fc79e288807190d2f0d896405ceab41a0407ed8e41bf541b5e299f710a'
    plan = read(HERE / 'plan.json')
    ready = read(HERE / 'preflight/implementation-ready.json')
    for item in plan['inputs'] + read(R413 / 'preflight/runtime-source-pins.json')['files'] + ready['files']:
        assert sha(ROOT / item['path']) == item['sha256'], item['path']
    receipt = read(HERE / 'preflight/original-parent-terminal.json')
    assert receipt['actual_terminal_received'] and receipt['unified_exec_session'] == 80573
    assert receipt['exit_code'] != 0
    terminal = read(R414 / 'resume-terminal.json')
    if receipt['classification'] == 'DIRECTORY_PREPARATION_FAILURE':
        assert terminal['error_type'] == 'FileNotFoundError' and 'r223/resources' in terminal['error']
    else:
        assert receipt['classification'] == 'EXPECTED_HANDOFF_AT_076'
        assert terminal['error_type'] == 'RuntimeError' and terminal['error'] == 'Refusing repeat: py-module-076'
    parent = read(HERE / 'preflight/block-intent.json')['original_parent']
    assert not identity_alive(parent['pid'], parent['starttime']), 'Original parent remains alive'
    guard = read(R413 / 'implementation/py-module-076/result.json')
    assert guard['state'] == 'BLOCKED_PRECONDITION_R415_RESOURCE_PARENT'
    assert guard['launched'] is False and guard['pytest_attempts'] == 0
    # Audit every registered successor/tail, not only the initial 402 stages.
    all_specs = [read(path) for path in sorted((R413 / 'specs').glob('*.json'))]
    started = Counter()
    retained = []
    live_owned = []
    for spec in all_specs:
        directory = Path(spec['directory'])
        invocation = directory / 'invocation.json'
        result_path = directory / 'result.json'
        if invocation.exists():
            assert result_path.exists(), 'Unclosed invoked stage: ' + spec['id']
            result = read(result_path)
            assert result.get('reaped') and not result.get('source_drift') and not result.get('remaining_live') and not result.get('errors')
            identities = directory / 'owned-process-identities.json'
            assert identities.exists()
            for identity in read(identities):
                if identity_alive(identity['pid'], identity['starttime_ticks']):
                    live_owned.append(identity)
        if result_path.exists():
            retained.append({'id': spec['id'], 'result_sha256': sha(result_path),
                             'state': read(result_path)['state'], 'invoked': invocation.exists()})
        rows = event_rows(directory)
        collections = [row for row in rows if row['event'] == 'collection_finished']
        if collections:
            assert collections[-1]['nodeids'] == spec.get('nodes', [])
        for row in rows:
            if row['event'] == 'started':
                assert row['nodeid'] in spec.get('nodes', [])
                started[row['nodeid']] += 1
    assert not live_owned, live_owned
    assert max(started.values(), default=0) <= 1
    stages = read(R413 / 'stages.json')
    original = next(spec for spec in stages if spec['id'] == 'py-module-075')
    directory = Path(original['directory'])
    result075 = read(directory / 'result.json')
    rows075 = event_rows(directory)
    collections = [row for row in rows075 if row['event'] == 'collection_finished']
    assert collections and collections[-1]['nodeids'] == original['nodes']
    assert result075['state'] in ['FINISHED', 'TIMEOUT']
    finished075 = any(row['event'] == 'finished' for row in rows075)
    pending = [] if finished075 else [node for node in original['nodes'] if not started[node]]
    partials = []
    for candidate in sorted((R413 / 'implementation').glob('py-module-075-tail-*')):
        forbidden = ['invocation.json', 'raw-exit.json', 'pytest-events.jsonl', 'result.json']
        assert not any((candidate / name).exists() for name in forbidden)
        partials.append({'directory': str(candidate), 'entries': sorted(str(path.relative_to(candidate)) for path in candidate.rglob('*')),
                         'invoked': False, 'policy': 'Preserved unused; new R415 identity will be used.'})
    queue = []
    for index, node in enumerate(pending, 1):
        spec = fresh(original, f'py-module-075-r415-tail-{index:04}', [node])
        assert spec['timeout_s'] == 600 and not started[node]
        queue.append(('run_one', spec))
    for spec in stages:
        if spec.get('lane', 'main') != 'main':
            continue
        directory = Path(spec['directory'])
        if spec['id'] == 'py-module-076':
            assert not (directory / 'invocation.json').exists() and not event_rows(directory)
            successor = fresh(spec, 'py-module-076-r415-handoff')
            assert len(successor['nodes']) == 4 and successor['timeout_s'] == 1800
            queue.append(('execute', successor))
        elif (directory / 'invocation.json').exists() or (directory / 'result.json').exists():
            continue
        else:
            assert not any(started[node] for node in spec.get('nodes', []))
            queue.append(('execute', spec))
    assert queue and all(spec['id'] != 'py-module-075' for action, spec in queue)
    assert all(not (Path(spec['directory']) / 'invocation.json').exists() and
               not (Path(spec['directory']) / 'result.json').exists() for action, spec in queue)
    manifest = {'generated_utc': now(), 'parent_terminal_classification': receipt['classification'],
                'original_parent_absent': True, 'owned_identities_still_alive': live_owned,
                'retained': retained, 'global_unique_started_nodes': len(started), 'duplicate_starts': [],
                'original075_state': result075['state'], 'original075_session_finished': finished075,
                'original075_pending_never_started': pending, 'old_partial_tail_directories': partials,
                '075_started_incomplete_kept': [node for node in original['nodes'] if started[node] and not all(
                    any(row.get('nodeid') == node and row.get('event') == 'report' and row.get('when') == phase
                        for row in rows075) for phase in ['setup', 'call', 'teardown'])],
                '076_original_slot_launched': False, '076_successor': 'py-module-076-r415-handoff',
                'queue': [{'action': action, 'id': spec['id'], 'directory': spec['directory'],
                           'nodes': spec.get('nodes', []), 'timeout_s': spec['timeout_s']} for action, spec in queue],
                'queue_count': len(queue), 'signals_sent': [], 'new_test_retry_quota': 0}
    save(HERE / 'preflight/resume-manifest.json', manifest)
    module_spec = importlib.util.spec_from_file_location('frozen_r413_runner', R413 / 'run_batch.py')
    runner = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(runner)
    bindings = {name: getattr(runner, name) for name in ['ROUND', 'ROOT', 'events', 'event', 'save', 'run_one', 'json', 'Path']}
    exec(compile((HERE / 'derived_execute.py').read_text(), str(HERE / 'derived_execute.py'), 'exec'), bindings)
    execute = bindings['execute']
    assert runner.ROUND == R413 and execute.__globals__['ROUND'] == R413
    save(HERE / 'resume-start.json', {'at_utc': now(), 'pid': os.getpid(), 'queue_count': len(queue),
         'manifest_sha256': sha(HERE / 'preflight/resume-manifest.json'),
         'original_runner_sha256': sha(R413 / 'run_batch.py'), 'derived_execute_sha256': sha(HERE / 'derived_execute.py')})
    for action, spec in queue:
        if action == 'run_one':
            runner.run_one(spec)
        else:
            execute(spec)
    save(HERE / 'resume-complete.json', {'at_utc': now(), 'queue_count': len(queue), 'completed_original_order': True})


if __name__ == '__main__':
    for name, fd in [('resume.stdout.log', 1), ('resume.stderr.log', 2)]:
        stream = (HERE / name).open('x', encoding='utf-8')
        os.dup2(stream.fileno(), fd)
        stream.close()
    try:
        main()
    except BaseException as error:
        traceback.print_exc()
        save(HERE / 'resume-terminal.json', {'at_utc': now(), 'status': 'ERROR', 'error_type': type(error).__name__, 'error': str(error)})
        raise
    else:
        save(HERE / 'resume-terminal.json', {'at_utc': now(), 'status': 'FINISHED', 'returncode': 0})
