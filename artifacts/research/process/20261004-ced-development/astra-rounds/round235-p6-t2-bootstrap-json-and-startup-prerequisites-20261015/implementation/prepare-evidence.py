"""R235 one-shot stdlib source baseline; no product/prerequisite import."""
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
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round235-p6-t2-bootstrap-json-and-startup-prerequisites-20261015'
CHECKS, WRITES = [], []
CHANGES = {
    'worker_runtime.py': (
        ('        self._local_original = {\n', '        self._local_original = _descriptor_plain({\n'),
        ('        }\n        owner._local_original = self._local_original\n',
         '        })\n        owner._local_original = self._local_original\n'),
    ),
    'operational_windows.py': (
        ('        return LocalAuthorityDecision.from_payload({\n',
         '        return LocalAuthorityDecision.from_payload(_descriptor_plain({\n'),
        ('            "disposition": "VALID", "reasons": [],\n        })\n',
         '            "disposition": "VALID", "reasons": [],\n        }))\n'),
    ),
}


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
    check(pin(path, raw) == {k: row[k] for k in ('path', 'bytes', 'sha256')}, 'fixed input bytes/hash', str(path))
    return raw


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITES.append({'path': str(path), 'status': 'ATTEMPTED_PARTIAL_UNKNOWN'})
    with path.open('xb') as handle:
        check(handle.write(raw) == len(raw), 'full exclusive write', str(path))
    check(path.read_bytes() == raw, 'artifact exact byte readback', str(path))
    WRITES[-1]['status'] = 'COMPLETE_EXACT'


def histories(observed):
    rows = observed['inputs'] + observed['trace_pins'] + observed['old_role_pins']
    rows += observed['additional_source_evidence'] + observed['protected_current_pins']
    rows += [db['pin'] for db in observed['old_databases']]
    for row in rows:
        fixed(row)
    absent = [item for db in observed['old_databases'] for item in db['sidecars']]
    check(len(absent) == 18, '18 exact old DB sidecar absences')
    for row in absent:
        path = Path(row['path'])
        check(row['exists'] is False and not path.exists() and not path.is_symlink(), 'old sidecar remains absent', str(path))
    return rows, absent


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R235 baseline 120s')))
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
    check(reservation['state'] == 'RESERVED_BY_ROOT' and reservation['used'] == 1 and reservation['remaining'] == 0, 'one ROOT reservation')
    check(gate['reservation_id'] == reservation['reservation_id'], 'same reservation id')
    check(gate['argv'] == gate['launcher_argv'] == command['launcher_argv'] == entry['argv'], 'exact baseline argv')
    check(sys.argv == command['launcher_argv'][1:] and Path.cwd() == ROOT and gate['cwd'] == str(ROOT), 'actual source argv/cwd')
    check(gate['finite_env'] == command['finite_env'] and gate['timeout_seconds'] == command['timeout_seconds'] == 120, 'finite env and cap')
    check(all(os.environ.get(k) == v for k, v in command['finite_env'].items()), 'actual declared environment')
    fixed(gate['source'])
    check(gate['source']['path'] == str(Path(__file__)), 'exact source identity')
    mutable = {str(D / name) for name in ('command-ledger.json', 'root-command-ledger.json', 'script-gate.json', 'source-gate.json', 'root-activation.json')}
    for row in gate['input_records']:
        check(row['path'] not in mutable, 'no mutable control in fixed loop')
        fixed(row)
    observed = json.loads(fixed(plan['inputs']['index']))
    before = json.loads(fixed(gate['before_manifest_pin']))
    for pair in before['controls']:
        fixed(pair['archive'])
    original_products = {row['current']['path']: row for row in before['before_products']}
    scope = {row['path']: row for row in plan['scope']['product_changes']}
    check(set(scope) == set(original_products) and len(scope) == 2, 'exact two producer regions')
    history, absent = histories(observed)
    sources, physical, diffs, proofs = [], {}, [], []
    out = D / 'implementation/baseline'
    check(len(observed['source_pairs']) == 27, 'exact27 source pairs')
    for pair in observed['source_pairs']:
        path = Path(pair['current']['path'])
        old = fixed(pair['archive'])
        check(pin(path, old) == {k: pair['current'][k] for k in ('path', 'bytes', 'sha256')}, 'historical27 identity via exact physical archive', str(path))
        raw = path.read_bytes()
        if str(path) in scope:
            original = original_products[str(path)]
            check(fixed(original['physical_before']) == old, 'exclusive before equals accepted historical generation')
            expected = old.decode()
            for old_text, new_text in CHANGES[path.name]:
                check(expected.count(old_text) == 1, 'unique exact producer boundary', [str(path), old_text])
                expected = expected.replace(old_text, new_text, 1)
            check(raw == expected.encode(), 'full file exact approved wrapping only', str(path))
            check(path.stat().st_mode == original['mode'], 'product mode unchanged', str(path))
            proofs.append({'function': scope[str(path)]['function'], 'before': pair['current'],
                           'physical_before': original['physical_before'], 'after': pin(path, raw),
                           'full_file_equals_exact_boundary_replacement': True,
                           'all_other_function_prefix_suffix_bytes_identical': True})
            diffs.extend(difflib.unified_diff(old.decode().splitlines(keepends=True), raw.decode().splitlines(keepends=True),
                                            fromfile=str(path) + ' (before)', tofile=str(path) + ' (after)'))
        else:
            check(raw == old, 'all25 non-product source bytes unchanged', str(path))
        check(not path.is_symlink(), 'no source symlink')
        sources.append({**pin(path, raw), 'mode': path.stat().st_mode, 'base64': base64.b64encode(raw).decode(),
                        'original_generation': pair})
        physical[out / 'sources' / path.relative_to(ROOT)] = raw
    scripts = []
    check(len(gate['scripts']) == 3 and {row['path'] for row in gate['scripts']} == set(plan['scope']['new_sources']), 'exact three scripts')
    for row in gate['scripts']:
        raw = fixed(row)
        scripts.append({**row, 'base64': base64.b64encode(raw).decode()})
    controls = []
    for name, raw in (('command-ledger.json', author_raw), ('root-command-ledger.json', root_raw), ('script-gate.json', gate_raw)):
        controls.append({**pin(D / name, raw), 'base64': base64.b64encode(raw).decode()})
    for name in ('root-activation.json', 'source-gate.json'):
        raw = (D / name).read_bytes()
        controls.append({**pin(D / name, raw), 'base64': base64.b64encode(raw).decode()})
    invocation = {'round': 'R235', 'command': key, 'argv': command['launcher_argv'], 'launcher_argv': command['launcher_argv'],
                  'cwd': str(ROOT), 'finite_env': command['finite_env'], 'timeout_seconds': 120,
                  'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'], 'source': gate['source'],
                  'outer_capture': gate['transport'], 'controls_before': controls, 'independent_tool_streams': None}
    index = {'round': 'R235', 'sources': sources, 'protected': observed['protected_current_pins'],
             'scripts': scripts, 'history': history, 'absent_sidecars': absent,
             'input_records': gate['input_records'], 'scope_proofs': proofs}
    index_raw = encoded(index)
    artifacts = {**physical, out / 'source-index.json': index_raw, out / 'invocation.json': encoded(invocation),
                 out / 'scope-proof.json': encoded({'round': 'R235', 'checks': CHECKS, 'proofs': proofs,
                                                   'product_execution': False}),
                 out / 'limited.diff': ''.join(diffs).encode()}
    check(all(not path.exists() for path in [*artifacts, out / 'result.json']), 'all new baseline outputs absent')
    for row in gate['input_records'] + sources + gate['scripts']:
        fixed(row)
    histories(observed)
    check((D / 'command-ledger.json').read_bytes() == author_raw and (D / 'root-command-ledger.json').read_bytes() == root_raw
          and (D / 'script-gate.json').read_bytes() == gate_raw, 'roles/gate immediate full-byte CAS')
    for row in controls:
        fixed(row)
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / '.author-baseline.tmp'
    save(temporary, encoded(author))
    os.replace(temporary, D / 'command-ledger.json')
    for path, raw in artifacts.items():
        save(path, raw)
    for row in gate['input_records'] + sources + gate['scripts']:
        fixed(row)
    histories(observed)
    check((D / 'command-ledger.json').read_bytes() == encoded(author), 'author exact single-slot generation after write')
    for row in controls:
        if row['path'] != str(D / 'command-ledger.json'):
            fixed(row)
    result = {'round': 'R235', 'command': key, 'exit_code': 0, 'attempt': 1, 'retry': 0,
              'test_execution': False, 'product_commands': 0, 'input_records': gate['input_records'],
              'candidate': pin(out / 'source-index.json', index_raw), 'outputs': [pin(path, raw) for path, raw in artifacts.items()],
              'checks': CHECKS, 'runtime_evidence': None, 'actual_resources': None, 'invocation': invocation}
    save(out / 'result.json', encoded(result))
    signal.alarm(0)
    print(json.dumps({'command': key, 'exit_code': 0, 'candidate': result['candidate'], 'result': pin(out / 'result.json')}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        if sys.argv != [str(D / 'implementation/prepare-evidence.py'), 'baseline']:
            raise ValueError('exact R235 baseline launcher required')
        main()
    except BaseException as error:
        signal.alarm(0)
        out = D / 'implementation/baseline'
        out.mkdir(parents=True, exist_ok=True)
        if not (out / 'result.json').exists():
            save(out / 'result.json', encoded({'round': 'R235', 'command': 'baseline', 'exit_code': 1,
                 'attempt': 1, 'retry': 0, 'checks': CHECKS, 'writes': WRITES,
                 'exception': {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}}))
        print(json.dumps({'command': 'baseline', 'exit_code': 1, 'result': str(out / 'result.json')}))
        raise SystemExit(1)
