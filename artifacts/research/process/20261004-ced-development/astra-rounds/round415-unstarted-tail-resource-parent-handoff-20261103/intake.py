"""Apply only the authorized R415 never-launched administrative guard."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
HERE = Path(__file__).resolve().parent
R413 = HERE.parent / 'round413-full-long-validation-20261103'
R414 = HERE.parent / 'round414-workbench-db-scope-preflight-handoff-20261103'
PLAN_SHA = '64f939fc79e288807190d2f0d896405ceab41a0407ed8e41bf541b5e299f710a'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def processes():
    rows = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            args = [a.decode(errors='replace') for a in (directory / 'cmdline').read_bytes().split(b'\0') if a]
            stat = (directory / 'stat').read_text()
            fields = stat[stat.rfind(')') + 2:].split()
            rows.append({'pid': int(directory.name), 'ppid': int(fields[1]),
                         'session': int(fields[3]), 'starttime': int(fields[19]), 'argv': args})
        except (OSError, ValueError):
            pass
    return rows


def check_unlaunched(directory):
    forbidden = ['invocation.json', 'raw-exit.json', 'terminal.json', 'pytest-events.jsonl', 'junit.xml']
    assert not any((directory / name).exists() for name in forbidden)
    progress = [json.loads(line) for line in (R413 / 'progress.jsonl').read_text().splitlines()]
    assert not any(item.get('stage_id') == 'py-module-076' for item in progress)
    assert not any(any(arg == str(R413 / 'specs/py-module-076.json') or
                       arg.startswith('--basetemp=/tmp/bigsmall-r413-py-module-076')
                       for arg in item['argv']) for item in processes())
    return progress[-1]


def main():
    assert sha(HERE / 'plan.json') == PLAN_SHA
    plan = json.loads((HERE / 'plan.json').read_text())
    pins = plan['inputs'] + json.loads((R413 / 'preflight/runtime-source-pins.json').read_text())['files']
    assert all(sha(ROOT / item['path']) == item['sha256'] for item in pins)
    parents = [item for item in processes() if any(arg.endswith('round414-workbench-db-scope-preflight-handoff-20261103/resume.py') for arg in item['argv'])]
    assert len(parents) == 1 and parents[0]['pid'] == 523308, parents
    parent = parents[0]
    original = R413 / 'implementation/py-module-076'
    latest = check_unlaunched(original)
    assert not (original / 'result.json').exists()
    authority = {'path': str(HERE / 'plan.json'), 'sha256': PLAN_SHA}
    save(HERE / 'preflight/block-intent.json', {'at_utc': datetime.now(UTC).isoformat(),
         'authority': authority, 'original_parent': parent, 'unified_exec_session': 80573,
         'input_pins_verified': len(pins), 'latest_progress': latest,
         'unlaunched_verified': True, 'before_directory_entries': sorted(p.name for p in original.iterdir()),
         'signals_sent': [], 'scope': 'Original075 continues;076 administrative guard only.'})
    save(original / 'result.json', {'stage_id': 'py-module-076',
         'state': 'BLOCKED_PRECONDITION_R415_RESOURCE_PARENT', 'launched': False,
         'pytest_attempts': 0, 'returncode': None, 'at_utc': datetime.now(UTC).isoformat(),
         'authority': authority, 'successor_id': 'py-module-076-r415-handoff',
         'reason': 'Known static unstarted-tail resource parent directory preparation defect; natural handoff only.',
         'note': 'No test child/exit/JUnit/cleanup is claimed for this slot.'})
    latest = check_unlaunched(original)
    save(HERE / 'preflight/block-applied.json', {'at_utc': datetime.now(UTC).isoformat(),
         'guard_sha256': sha(original / 'result.json'), 'unlaunched_rechecked': True,
         'latest_progress': latest, 'signals_sent': [], 'parent': parent})
    print(json.dumps({'guard_applied': True, 'stage': 'py-module-076', 'launched': False,
                      'parent': parent['pid'], 'starttime': parent['starttime']}))


if __name__ == '__main__':
    main()
