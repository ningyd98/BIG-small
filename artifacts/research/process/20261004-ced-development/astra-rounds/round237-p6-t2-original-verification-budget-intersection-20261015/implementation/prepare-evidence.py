"""R237/R238 one-shot source baseline; never executes the product projection."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round237-p6-t2-original-verification-budget-intersection-20261015'
CHECKS, WRITES = [], []


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def pin(path, data=None):
    data = path.read_bytes() if data is None else data
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def check(value, name, detail=None):
    CHECKS.append({'name': name, 'passed': bool(value), 'detail': detail})
    if not value:
        raise AssertionError(name)


def fixed(row):
    path = Path(row['path'])
    check(not path.is_symlink(), 'regular fixed input', str(path))
    raw = path.read_bytes()
    check(pin(path, raw) == {k: row[k] for k in ('path', 'bytes', 'sha256')}, 'fixed identity tuple', str(path))
    return raw


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITES.append({'path': str(path), 'status': 'ATTEMPTED_PARTIAL_UNKNOWN'})
    with path.open('xb') as handle:
        check(handle.write(raw) == len(raw), 'complete exclusive write', str(path))
    check(path.read_bytes() == raw, 'artifact byte readback', str(path))
    WRITES[-1]['status'] = 'COMPLETE_EXACT'


def history(plan, gate):
    observed = json.loads(fixed(plan['inputs']['index']))
    resolved = json.loads(fixed(gate['resolved_history_pin']))
    check(resolved['status'] == 'RESOLVED_FOR_ROOT_GATE' and not resolved['unresolved'], 'explicit complete history resolution')
    for row in resolved['documents']:
        fixed(row)
    records = []
    for item in resolved['entries']:
        original, archive = item['original'], item['resolution']['pin']
        check((archive['bytes'], archive['sha256']) == (original['bytes'], original['sha256']), 'historical original byte identity')
        check(item['resolution']['kind'] in {'EXACT_PHYSICAL_BEFORE', 'CURRENT_EXACT_BYTES'}, 'exact resolution kind')
        fixed(archive)
        records.append(archive)
    check(len(observed['retained_databases']) == 18, '18 retained old databases')
    absent = []
    for database in observed['retained_databases']:
        fixed(database['pin'])
        for row in database['sidecars']:
            path = Path(row['path'])
            check(row['exists'] is False and not path.exists() and not path.is_symlink(), 'old database sidecar absent', str(path))
            absent.append(row)
    check(len(absent) == 54, '54 retained sidecar absences')
    return observed, resolved, records, absent


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R237 baseline 120s')))
    signal.alarm(120)
    key = 'baseline'
    plan = json.loads((D / 'plan.json').read_bytes())
    command = next(row for row in plan['commands'] if row['id'] == key)
    gate_raw = (D / 'script-gate.json').read_bytes()
    author_raw, root_raw = (D / 'command-ledger.json').read_bytes(), (D / 'root-command-ledger.json').read_bytes()
    gate = json.loads(gate_raw)['commands'][key]
    author, root = json.loads(author_raw), json.loads(root_raw)
    entry, reservation = author['commands'][key], root['commands'][key]
    check(gate['state'] == 'APPROVED' and gate['full_source_reviewed'] is True, 'ROOT full source review')
    check(entry['state'] == 'HELD' and entry['used'] == 0 and entry['remaining'] == 1, 'unused author slot')
    check(reservation['state'] == 'RESERVED_BY_ROOT' and reservation['used'] == 1 and reservation['remaining'] == 0, 'single ROOT reservation')
    check(gate['reservation_id'] == reservation['reservation_id'], 'same reservation identity')
    check(gate['argv'] == gate['launcher_argv'] == command['launcher_argv'] == entry['launcher_argv'], 'exact baseline launcher')
    check(sys.argv == command['launcher_argv'][1:] and Path.cwd() == ROOT and gate['cwd'] == str(ROOT), 'actual argv/cwd')
    check(gate['finite_env'] == command['finite_env'] and gate['timeout_seconds'] == command['timeout_seconds'] == 120, 'finite environment/cap')
    check(all(os.environ.get(k) == v for k, v in command['finite_env'].items()), 'actual declared environment')
    fixed(gate['source'])
    check(gate['source']['path'] == str(Path(__file__)), 'baseline source identity')
    mutable = {str(D / name) for name in ('script-gate.json', 'source-gate.json', 'root-activation.json', 'command-ledger.json', 'root-command-ledger.json')}
    for row in gate['input_records']:
        check(row['path'] not in mutable, 'no live mutable control in fixed loop')
        fixed(row)
    observed, resolved, records, absent = history(plan, gate)
    before = json.loads(fixed(gate['before_manifest_pin']))
    scope = json.loads(fixed(gate['scope_contract_pin']))
    old = fixed(scope['before'])
    current_path = Path(scope['after']['path'])
    raw = fixed(scope['after'])
    text = raw.decode()
    helper = base64.b64decode(scope['helper'], validate=True).decode()
    check(text.count(helper) == 1, 'one complete static helper insertion')
    text = text.replace(helper, '', 1)
    for region in scope['regions']:
        old_region = base64.b64decode(region['before'], validate=True).decode()
        new_region = base64.b64decode(region['after'], validate=True).decode()
        check(text.count(new_region) == 1, 'one exact approved function region', region['name'])
        text = text.replace(new_region, old_region, 1)
    for line in scope['added_imports']:
        check(text.count(line) == 1, 'one required new import', line)
        text = text.replace(line, '', 1)
    check(text.encode() == old, 'all bytes outside five regions/helper/imports identical')
    check(pin(current_path, old) == scope['original_identity'], 'whole original runtime identity')
    check(len(scope['regions']) == 5 and scope['initial_export_count'] == 1, 'five regions and single original export')
    source_rows, physical = [], {}
    archives = {row['original']['path']: row for row in before['source_archives27']}
    check(len(observed['current_sources']) == len(archives) == 27 and len(observed['protected']) == 211, 'current27/protected211 coverage')
    out = D / 'implementation/baseline'
    for row in observed['current_sources']:
        path = Path(row['path'])
        original = archives[str(path)]
        previous = fixed(original['archive'])
        check(pin(path, previous) == original['original'], 'actual complete original27 generation')
        data = path.read_bytes()
        if path == current_path:
            check(data == raw, 'approved new runtime generation')
        else:
            check(data == previous, 'other26 source full bytes unchanged', str(path))
        check(path.stat().st_mode == original['mode'] and not path.is_symlink(), 'source mode/regular file unchanged')
        source_rows.append({**pin(path, data), 'mode': path.stat().st_mode, 'base64': base64.b64encode(data).decode(),
                            'physical_original': original})
        physical[out / 'sources' / path.relative_to(ROOT)] = data
    for row in observed['protected']:
        fixed(row)
    check(len(gate['scripts']) == 2 and {row['path'] for row in gate['scripts']} == set(plan['scope']['new_author_scripts']), 'exact two new author scripts')
    scripts = []
    for row in gate['scripts'] + [gate['prerequisite_source']]:
        scripts.append({**row, 'base64': base64.b64encode(fixed(row)).decode()})
    controls = []
    for name, data in (('command-ledger.json', author_raw), ('root-command-ledger.json', root_raw), ('script-gate.json', gate_raw)):
        controls.append({**pin(D / name, data), 'base64': base64.b64encode(data).decode()})
    for name in ('root-activation.json', 'source-gate.json'):
        data = (D / name).read_bytes()
        controls.append({**pin(D / name, data), 'base64': base64.b64encode(data).decode()})
    invocation = {'round': 'R237', 'continuation': 'R238', 'command': key, 'argv': command['launcher_argv'],
                  'launcher_argv': command['launcher_argv'], 'cwd': str(ROOT), 'finite_env': command['finite_env'],
                  'timeout_seconds': 120, 'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'],
                  'source': gate['source'], 'controls_before': controls, 'outer_capture': gate['transport'],
                  'independent_tool_streams': None}
    index = {'round': 'R237', 'sources': source_rows, 'protected': observed['protected'], 'scripts': scripts,
             'history': records, 'resolved_history': resolved, 'absent_sidecars': absent,
             'scope_contract': scope, 'input_records': gate['input_records']}
    index_raw = encoded(index)
    diff = ''.join(difflib.unified_diff(old.decode().splitlines(keepends=True), raw.decode().splitlines(keepends=True),
                                     fromfile=str(current_path) + ' (before)', tofile=str(current_path) + ' (after)')).encode()
    artifacts = {**physical, out / 'source-index.json': index_raw, out / 'limited.diff': diff,
                 out / 'scope-proof.json': encoded({'round': 'R237', 'checks': CHECKS, 'scope_contract': scope,
                                                   'product_execution': False}),
                 out / 'invocation.json': encoded(invocation)}
    check(all(not path.exists() for path in [*artifacts, out / 'result.json']), 'all baseline outputs absent')
    for row in gate['input_records'] + source_rows + scripts + controls:
        fixed(row)
    history(plan, gate)
    check((D / 'command-ledger.json').read_bytes() == author_raw and (D / 'root-command-ledger.json').read_bytes() == root_raw
          and (D / 'script-gate.json').read_bytes() == gate_raw, 'roles/gate immediate full CAS')
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / '.author-baseline.tmp'
    save(temporary, encoded(author))
    os.replace(temporary, D / 'command-ledger.json')
    for path, data in artifacts.items():
        save(path, data)
    for row in gate['input_records'] + source_rows + scripts:
        fixed(row)
    history(plan, gate)
    check((D / 'command-ledger.json').read_bytes() == encoded(author), 'exact author slot consumption')
    for row in controls:
        if row['path'] != str(D / 'command-ledger.json'):
            fixed(row)
    result = {'round': 'R237', 'command': key, 'exit_code': 0, 'attempt': 1, 'retry': 0,
              'test_execution': False, 'product_commands': 0, 'input_records': gate['input_records'],
              'candidate': pin(out / 'source-index.json', index_raw), 'outputs': [pin(path, data) for path, data in artifacts.items()],
              'checks': CHECKS, 'invocation': invocation, 'runtime_evidence': None, 'actual_resources': None}
    save(out / 'result.json', encoded(result))
    signal.alarm(0)
    print(json.dumps({'command': key, 'exit_code': 0, 'candidate': result['candidate'], 'result': pin(out / 'result.json')}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        if sys.argv != [str(D / 'implementation/prepare-evidence.py'), 'baseline']:
            raise ValueError('exact R237 baseline launcher required')
        main()
    except BaseException as error:
        signal.alarm(0)
        out = D / 'implementation/baseline'
        out.mkdir(parents=True, exist_ok=True)
        if not (out / 'result.json').exists():
            save(out / 'result.json', encoded({'round': 'R237', 'command': 'baseline', 'exit_code': 1,
                 'attempt': 1, 'retry': 0, 'checks': CHECKS, 'writes': WRITES,
                 'exception': {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}}))
        print(json.dumps({'command': 'baseline', 'exit_code': 1, 'result': str(out / 'result.json')}))
        raise SystemExit(1)
