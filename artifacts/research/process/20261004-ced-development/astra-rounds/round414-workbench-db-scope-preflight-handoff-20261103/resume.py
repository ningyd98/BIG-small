"""Resume only never-invoked R413 stages after its recorded natural exit."""
from collections import Counter
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
HERE = Path(__file__).resolve().parent
R413 = HERE.parent / 'round413-full-long-validation-20261103'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def now():
    return datetime.now(UTC).isoformat()


def parent_absent():
    parent = read(HERE / 'preflight/block-intent.json')['original_parent']
    path = Path('/proc') / str(parent['pid'])
    if not path.exists():
        return True
    stat = (path / 'stat').read_text()
    return int(stat[stat.rfind(')') + 2:].split()[19]) != parent['starttime']


def main():
    assert sha(HERE / 'plan.json') == '94b0e908b4269f62307ddf4f14378f480cfece2ecfabf1cb0f4bc2e7a54be852'
    plan = read(HERE / 'plan.json')
    ready = read(HERE / 'preflight/implementation-ready.json')
    for item in plan['inputs'] + read(R413 / 'preflight/runtime-source-pins.json')['files'] + ready['files']:
        assert sha(ROOT / item['path']) == item['sha256'], item['path']
    terminal = read(HERE / 'preflight/original-parent-terminal.json')
    assert terminal['classification'] == 'EXPECTED_HANDOFF' and terminal['exit_code'] != 0
    assert terminal['unified_exec_session'] == 12273 and terminal['actual_terminal_received']
    assert 'Refusing repeat: py-module-073' in terminal['output']
    assert parent_absent(), 'Original parent still alive; no overlap is permitted'
    progress = [json.loads(line) for line in (R413 / 'progress.jsonl').read_text().splitlines()]
    starts = Counter(item['stage_id'] for item in progress if item['event'] == 'stage_start')
    ends = Counter(item['stage_id'] for item in progress if item['event'] == 'stage_end')
    assert starts == ends and max(starts.values(), default=0) <= 1
    assert not starts['py-module-073']
    guard = read(R413 / 'implementation/py-module-073/result.json')
    assert guard['state'] == 'BLOCKED_PRECONDITION_R414_DB_SCOPE' and guard['launched'] is False
    assert guard['pytest_attempts'] == 0
    successor = read(HERE / 'specs/py-module-073-r414-db-scope.json')
    assert 'SIMULATION_RUNTIME_DB' not in successor['env']
    queue = []
    retained = []
    started_nodes = Counter()
    stages = read(R413 / 'stages.json')
    for spec in stages:
        if spec.get('lane', 'main') != 'main':
            continue
        directory = Path(spec['directory'])
        invocation = directory / 'invocation.json'
        result_path = directory / 'result.json'
        if spec['id'] == 'py-module-073':
            assert not invocation.exists() and not (directory / 'pytest-events.jsonl').exists()
            queue.append(successor)
            continue
        if invocation.exists() or result_path.exists():
            assert result_path.exists(), f'Unclosed stage: {spec["id"]}'
            result = read(result_path)
            if invocation.exists():
                assert result.get('reaped') and not result.get('source_drift') and not result.get('remaining_live') and not result.get('errors')
            retained.append({'id': spec['id'], 'result_sha256': sha(result_path), 'returncode': result.get('returncode'), 'state': result['state']})
            events = directory / 'pytest-events.jsonl'
            if events.exists():
                for line in events.read_text().splitlines():
                    item = json.loads(line)
                    if item['event'] == 'started':
                        started_nodes[item['nodeid']] += 1
            continue
        assert not starts[spec['id']]
        queue.append(spec)
    assert max(started_nodes.values(), default=0) <= 1
    assert queue[0]['id'] == successor['id']
    assert all(not (Path(spec['directory']) / 'invocation.json').exists() and
               not (Path(spec['directory']) / 'result.json').exists() for spec in queue)
    manifest = {'generated_utc': now(), 'original_parent_absent': True, 'signals_sent': [],
                'retained': retained, 'retained_count': len(retained),
                'already_started_unique_nodes': len(started_nodes), 'duplicate_starts': [],
                'original_unlaunched_slot': 'py-module-073', 'successor': successor['id'],
                'queue': [{'id': spec['id'], 'spec_sha256': hashlib.sha256(json.dumps(spec, ensure_ascii=False, indent=2).encode() + b'\n').hexdigest(),
                           'nodes': len(spec.get('nodes', [])), 'timeout_s': spec['timeout_s']} for spec in queue],
                'queue_count': len(queue), 'policy': 'Original order and frozen execute; no previously invoked stage is restarted.'}
    save(HERE / 'preflight/resume-manifest.json', manifest)
    module_spec = importlib.util.spec_from_file_location('frozen_r413_runner', R413 / 'run_batch.py')
    runner = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(runner)
    assert runner.ROUND == R413 and runner.ROOT == ROOT
    save(HERE / 'resume-start.json', {'at_utc': now(), 'queue_count': len(queue),
                                      'manifest_sha256': sha(HERE / 'preflight/resume-manifest.json'),
                                      'original_execute_sha256': sha(R413 / 'run_batch.py'), 'pid': os.getpid()})
    for spec in queue:
        runner.execute(spec)
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
