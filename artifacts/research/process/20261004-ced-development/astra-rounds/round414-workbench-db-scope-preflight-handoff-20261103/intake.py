"""Apply the R414 pre-launch guard; never signal or start a test."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
HERE = Path(__file__).resolve().parent
R413 = HERE.parent / 'round413-full-long-validation-20261103'
PLAN_SHA = '94b0e908b4269f62307ddf4f14378f480cfece2ecfabf1cb0f4bc2e7a54be852'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def processes():
    result = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            args = [a.decode(errors='replace') for a in (directory / 'cmdline').read_bytes().split(b'\0') if a]
            stat = (directory / 'stat').read_text()
            fields = stat[stat.rfind(')') + 2:].split()
            result.append({'pid': int(directory.name), 'ppid': int(fields[1]),
                           'session': int(fields[3]), 'starttime': int(fields[19]), 'argv': args})
        except (OSError, ValueError):
            continue
    return result


def check_unlaunched(directory, progress, live):
    forbidden = ['invocation.json', 'raw-exit.json', 'terminal.json', 'pytest-events.jsonl', 'junit.xml']
    assert not any((directory / name).exists() for name in forbidden)
    assert not any(row.get('stage_id') == 'py-module-073' for row in progress)
    assert not any(any(arg == str(R413 / 'specs/py-module-073.json') or
                       arg.startswith('--basetemp=/tmp/bigsmall-r413-py-module-073')
                       for arg in item['argv']) for item in live)


def main():
    assert sha(HERE / 'plan.json') == PLAN_SHA
    plan = json.loads((HERE / 'plan.json').read_text())
    pins = plan['inputs'] + json.loads((R413 / 'preflight/runtime-source-pins.json').read_text())['files']
    mismatches = [item['path'] for item in pins if sha(ROOT / item['path']) != item['sha256']]
    assert not mismatches, mismatches
    live = processes()
    parents = [item for item in live if any(arg.endswith('/run_batch.py') for arg in item['argv'])]
    assert len(parents) == 1, parents
    parent = parents[0]
    assert (parent['pid'], parent['starttime'], parent['session']) == (384770, 15532494, 384770), parent
    progress = [json.loads(line) for line in (R413 / 'progress.jsonl').read_text().splitlines()]
    original = R413 / 'implementation/py-module-073'
    check_unlaunched(original, progress, live)
    assert not (original / 'result.json').exists()
    authority = {'path': str(HERE / 'plan.json'), 'sha256': PLAN_SHA}
    intent = {'at_utc': datetime.now(UTC).isoformat(), 'authority': authority,
              'input_pins_verified': len(pins), 'pin_mismatches': mismatches,
              'original_parent': parent, 'unified_exec_session': 12273,
              'latest_progress': progress[-1], 'original_stage_id': 'py-module-073',
              'successor_id': plan['successor']['id'], 'before_directory_entries': sorted(p.name for p in original.iterdir()),
              'unlaunched_verified': True, 'signals_sent': []}
    save(HERE / 'preflight/block-intent.json', intent)
    save(original / 'result.json', {
        'stage_id': 'py-module-073', 'state': 'BLOCKED_PRECONDITION_R414_DB_SCOPE',
        'launched': False, 'pytest_attempts': 0, 'returncode': None,
        'at_utc': datetime.now(UTC).isoformat(), 'reason': 'known_shared_db_env_conflict',
        'authority': authority, 'successor_id': plan['successor']['id'],
        'note': 'Administrative pre-launch guard only; no test child, exit, JUnit or cleanup is claimed.'})
    check_unlaunched(original, [json.loads(line) for line in (R413 / 'progress.jsonl').read_text().splitlines()], processes())
    save(HERE / 'preflight/block-applied.json', {
        'at_utc': datetime.now(UTC).isoformat(), 'guard_sha256': sha(original / 'result.json'),
        'unlaunched_rechecked': True, 'signals_sent': [], 'parent': parent,
        'next': 'Wait for the original parent to naturally refuse this never-launched stage and exit.'})
    print(json.dumps({'guard_applied': True, 'launched': False, 'parent': parent['pid']}))


if __name__ == '__main__':
    main()
