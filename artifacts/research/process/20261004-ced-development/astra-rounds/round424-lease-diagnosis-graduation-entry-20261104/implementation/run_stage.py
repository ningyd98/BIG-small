"""Execute each frozen R424 diagnostic stage once through the R413 supervisor."""

from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parent.parent
R413 = ROUND.parent / 'round413-full-long-validation-20261103'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def run(job, manifest, started):
    for pin in manifest['frozen_drivers']:
        data = (ROOT / pin['path']).read_bytes()
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], pin['path']
    remaining = 300 - (time.monotonic() - started)
    if remaining <= 30:
        save(ROUND / 'validation' / (job['id'] + '-not-started.json'), {'state': 'NOT_STARTED', 'reason': 'global budget reserve'})
        return
    directory = ROUND / 'validation' / job['id']
    directory.mkdir(parents=True, exist_ok=False)
    basetemp = Path('/tmp') / ('bigsmall-r424-' + job['id'])
    assert not basetemp.exists() and not basetemp.is_symlink(), 'never reuse an old basetemp'
    baseline = json.loads((ROUND / 'intake/runtime-source-baseline.json').read_text())['files']
    pins = baseline + manifest['frozen_drivers']
    for pin in pins:
        path = ROOT / pin['path']
        data = path.read_bytes()
        assert path.is_file() and not path.is_symlink()
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], pin['path']
    save(directory / 'preflight/runtime-source-pins.json', {'files': pins})
    original = json.loads((R413 / 'implementation/py-module-229/invocation.json').read_text())
    old = original['directory']
    first_node = original['nodes'][0]
    argv = [value.replace(old, str(directory)) for value in original['argv'][:original['argv'].index(first_node)]]
    argv = ['--basetemp=' + str(basetemp) if value.startswith('--basetemp=') else value for value in argv]
    argv.extend(['-p', 'r424_trace', job['nodeid']])
    environment = {key: value.replace(old, str(directory)) for key, value in original['env'].items()
                   if key != 'SIMULATION_RUNTIME_DB'}
    environment['PYTHONPATH'] += ':' + str(ROUND / 'implementation')
    environment['R424_TRACE_PATH'] = str(directory / 'trace.jsonl')
    environment['R424_GUARD_EVIDENCE'] = str(directory / 'guard-evidence')
    environment['REAL_MOTION_DISPATCH_ENABLED'] = 'false'
    for relative in original['resource_dirs']:
        (directory / relative).mkdir(parents=True, exist_ok=False)
    spec = {'id': job['id'], 'directory': str(directory), 'cwd': str(ROOT), 'argv': argv,
            'env': environment, 'nodes': [job['nodeid']], 'ports': [],
            'timeout_s': min(job['cap_s'], remaining - 30),
            'created_utc': datetime.now(UTC).isoformat(),
            'scope': 'R424_SOFTWARE_ONLY_DIAGNOSIS_NO_REPAIR', 'attempt': 1}
    save(directory / 'spec.json', spec)
    imported = importlib.util.spec_from_file_location('r424_owned_supervisor', R413 / 'bounded_stage.py')
    module = importlib.util.module_from_spec(imported)
    imported.loader.exec_module(module)
    module.ROUND = directory
    module.run(directory / 'spec.json')


def main():
    assert len(sys.argv) == 1
    started = time.monotonic()
    save(ROUND / 'preflight/run-budget.json', {'started_monotonic': started, 'total_cap_s': 300, 'cleanup_reserve_s': 30,
                                             'started_utc': datetime.now(UTC).isoformat()})
    manifest = json.loads((ROUND / 'preflight/target-manifest.json').read_text())
    for job in manifest['jobs']:
        run(job, manifest, started)
        result = json.loads((ROUND / 'validation' / job['id'] / 'result.json').read_text())
        assert result['state'] == 'FINISHED' and result['reaped'] and not result['remaining_live']
        assert not result['source_drift'] and not result['errors'] and not result['cancellations']
        if job['kind'] == 'original':
            events = [json.loads(line) for line in (ROUND / 'validation' / job['id'] / 'pytest-events.jsonl').read_text().splitlines()]
            reports = [row for row in events if row['event'] == 'report']
            assert [row['when'] for row in reports] == ['setup', 'call', 'teardown']
            assert reports[0]['outcome'] == reports[2]['outcome'] == 'passed'
            assert reports[1]['outcome'] in {'passed', 'failed'}
            if reports[1]['outcome'] == 'failed':
                assert job['expected_error'] in reports[1]['longrepr'], 'unplanned failure root; stop'
        else:
            assert result['returncode'] == 0, 'probe failed; stop, no retry'
    save(ROUND / 'preflight/run-budget-terminal.json', {'elapsed_s': time.monotonic() - started, 'all_stages_finished': True})


if __name__ == '__main__':
    main()
