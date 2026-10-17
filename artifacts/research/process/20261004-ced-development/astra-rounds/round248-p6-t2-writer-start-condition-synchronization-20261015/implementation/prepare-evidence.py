"""R248 once-only source baseline with explicit historical evidence loss."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round248-p6-t2-writer-start-condition-synchronization-20261015'
E = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round245-p6-t2-missing-temporary-evidence-continuation-20261015'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def read_json(path):
    return json.loads(path.read_bytes())


def identity(row):
    return {key: row[key] for key in ('path', 'bytes', 'sha256')}


def key(row):
    return tuple(row[name] for name in ('path', 'bytes', 'sha256'))


def file_pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def fixed(row):
    path = Path(row['path'])
    raw = path.read_bytes()
    if path.is_symlink() or file_pin(path, raw) != identity(row):
        raise ValueError('fixed input differs: ' + str(path))
    return raw


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if type(value) is bytes else encoded(value)
    with path.open('xb') as handle:
        if handle.write(raw) != len(raw):
            raise OSError('partial exclusive metadata write')
    if path.read_bytes() != raw:
        raise ValueError('exclusive metadata readback differs')



def verify_contract(plan, gate):
    observation = json.loads(fixed(plan['inputs']['observation']))
    source = json.loads(fixed(plan['inputs']['current_baseline']))
    if (len(source['sources']) != 27 or len(source['protected']) != 211 or len(source['scripts']) != 3
            or len(source['history_observations']) != 812 or len(source['explicit_maps']) != 13
            or len(source['input_records']) != 28 or len(observation['inputs']) != 344):
        raise ValueError('actual R24227/211/3/812/13/28 and R248344 schema required')
    registry, missing = {}, []
    for row in observation['known_missing']:
        original, authority = row['original'], row['authority']
        if key(original) in registry or row['disposition'] != 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245':
            raise ValueError('unique exact historical unavailable identity required')
        container = json.loads(fixed(authority['pin']))
        ordinal, selector = authority['ordinal'], authority['selector']
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError('exact nonnegative authority ordinal required')
        if selector == 'input_records':
            values = container['input_records']
            if type(values) is not list or ordinal >= len(values):
                raise ValueError('input_records authority range differs')
            authoritative = values[ordinal]
        elif selector == 'new_retained_databases.pin':
            values = container['new_retained_databases']
            if type(values) is not list or ordinal >= len(values):
                raise ValueError('new database authority range differs')
            authoritative = values[ordinal]['pin']
        else:
            raise ValueError('unrecognized exact authority selector')
        if identity(authoritative) != identity(original):
            raise ValueError('historical registry exact original differs')
        path = Path(original['path'])
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError('historical unavailable path reappeared; provenance review required')
        registry[key(original)] = row
        missing.append({'original': original, 'authority': authority, 'disposition': row['disposition'],
                        'current_exists': False, 'current_is_symlink': False,
                        'current_bytes': None, 'current_sha256': None, 'hash_match': None})
    if len(registry) != 35:
        raise ValueError('exact35 unavailable identities required')
    pairs = (observation['history_authority']['explicit_maps']
             + [observation['additional_fixture_generation']] + observation['R242_final_settlement_maps'])
    if (len(observation['history_authority']['explicit_maps']) != 13
            or len(observation['R242_final_settlement_maps']) != 7):
        raise ValueError('exact inherited13 plus c14 plus final7 maps required')
    allowed = {str(ROOT / 'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007' / name)
               for name in ('active-t12-state.json', 'phase-summary.md')}
    allowed.update(str(D / name) for name in ('script-gate.json', 'source-gate.json', 'root-activation.json',
                                              'command-ledger.json', 'root-command-ledger.json'))
    for pair in gate['context_history']:
        if pair['original']['path'] not in allowed:
            raise ValueError('extra mapping outside authorized mutable context')
        pairs.append(pair)
    mappings = {}
    for pair in pairs:
        raw = fixed(pair['archive'])
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (pair['original']['bytes'], pair['original']['sha256']):
            raise ValueError('full physical original/archive equivalence differs')
        mappings[key(pair['original'])] = identity(pair['archive'])
    observations = []
    def historical(original, origin, resolved=None):
        if key(original) in registry:
            observations.append({'original': identity(original), 'origin': origin,
                                 'classification': 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245',
                                 'hash_match': None})
            return None
        target = mappings.get(key(original), mappings.get(key(resolved), resolved) if resolved is not None else original)
        raw = fixed(target)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (original['bytes'], original['sha256']):
            raise ValueError('exact mapped historical bytes differ')
        observations.append({'original': identity(original), 'origin': origin, 'resolved': identity(target),
                             'classification': 'VERIFIED_ARCHIVED' if target['path'] != original['path'] else 'CURRENT_EXACT',
                             'hash_match': True})
        return raw
    for name, rows in [('inputs344', observation['inputs']), ('baseline_inputs28', source['input_records']),
                       ('current_context', [observation['current_final_context']['STATE'],
                                            observation['current_final_context']['PHASE']]
                        + observation['current_final_context']['controls']),
                       ('gate_fixed_inputs', gate['input_records'])]:
        for ordinal, row in enumerate(rows):
            raw = historical(row, {'list': name, 'ordinal': ordinal})
            if raw is not None and row['path'].endswith('/invocation.json'):
                invocation = json.loads(raw)
                for control in invocation.get('controls_before', []):
                    decoded = base64.b64decode(control['base64'], validate=True)
                    if file_pin(Path(control['path']), decoded) != identity(control):
                        raise ValueError('invocation own exact recorded control generation differs')
    for ordinal, row in enumerate(source['history_observations']):
        if key(row['original']) in registry:
            if row['hash_match'] is not None:
                raise ValueError('unavailable historical hash cannot become true')
            historical(row['original'], {'list': 'history_observations812', 'ordinal': ordinal})
        else:
            historical(row['original'], {'list': 'history_observations812', 'ordinal': ordinal}, row['resolved'])
    fixture = Path(plan['scope']['modified_existing'][0])
    before = fixed(gate['fixture_before_pin'])
    if before != fixed(observation['additional_fixture_generation']['archive']):
        raise ValueError('c14 complete fixture before differs from physical authority')
    delta = plan['scope']['exact_change']
    old, new = delta['before'].encode(), delta['after'].encode()
    after = fixture.read_bytes()
    if (before.count(old) != 1 or after != before.replace(old, new, 1)
            or len(after) != delta['expected_after_bytes']
            or hashlib.sha256(after).hexdigest() != delta['expected_after_sha256']):
        raise ValueError('unique whole fixture start wait2B delta differs')
    for row in source['sources']:
        raw = base64.b64decode(row['base64'], validate=True)
        if file_pin(Path(row['path']), raw) != identity(row) or fixed(row['physical']) != raw:
            raise ValueError('actual R242 physical/base64 source identity differs')
        if Path(row['path']).read_bytes() != (after if row['path'] == str(fixture) else raw):
            raise ValueError('unapproved current source byte difference')
        if Path(row['path']).stat().st_mode != row['mode']:
            raise ValueError('current source mode differs')
    if len(observation['current_sources']) != 27 or len(observation['protected']) != 211:
        raise ValueError('current27/protected211 observation required')
    for row in observation['current_sources']:
        if fixed(row['physical']) != base64.b64decode(next(
                item['base64'] for item in source['sources'] if item['path'] == row['original']['path']), validate=True):
            raise ValueError('observed current source complete physical generation differs')
    for row in observation['protected'] + source['protected']:
        fixed(row)
    for row in source['scripts']:
        if fixed(row) != base64.b64decode(row['base64'], validate=True):
            raise ValueError('frozen parent script full bytes differ')
    sidecars = observation['old_absent_sidecars']
    if len(sidecars) != 90 or len({row['path'] for row in sidecars}) != 90:
        raise ValueError('exact90 historical sidecar paths required')
    for row in sidecars:
        path = Path(row['path'])
        if row['exists'] is not False or path.exists() or path.is_symlink():
            raise ValueError('old90 sidecar state differs')
    databases = observation['R242_current_persistent_databases']
    if len(databases) != 6 or len({row['pin']['path'] for row in databases}) != 6:
        raise ValueError('six current persistent R242 databases required')
    count = 0
    for row in databases:
        fixed(row['pin'])
        if key(row['pin']) in registry:
            raise ValueError('current persistent DB cannot use historical missing exception')
        for side in row['sidecars']:
            path = Path(side['path'])
            if (side['exists'] is not False or side['is_symlink'] is not False
                    or path.exists() or path.is_symlink()):
                raise ValueError('current R242 database sidecar state differs')
            count += 1
    if count != 18:
        raise ValueError('exact18 current R242 sidecar states required')
    return {'status': 'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
            'source': source, 'observation': observation, 'missing_registry': missing,
            'history_observations': observations, 'explicit_maps': pairs, 'sidecars': sidecars,
            'current_R242_databases': databases, 'commands': plan['commands'],
            'fixture_after': file_pin(fixture), 'all_historical_bytes_available': False}

def role_gate(key_name):
    plan = read_json(D / 'plan.json')
    gate_raw, author_raw, root_raw = [(D / name).read_bytes() for name in
                                     ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json')]
    gate = json.loads(gate_raw)['commands'][key_name]
    author, root = json.loads(author_raw), json.loads(root_raw)
    entry, reservation = author['commands'][key_name], root['commands'][key_name]
    if (gate['state'] != 'APPROVED' or gate['full_source_reviewed'] is not True
            or entry['state'] != 'HELD' or entry['used'] != 0 or entry['remaining'] != 1
            or reservation['state'] != 'RESERVED_BY_ROOT' or reservation['used'] != 1
            or reservation['remaining'] != 0 or gate['reservation_id'] != reservation['reservation_id']):
        raise ValueError('exact one-use ROOT reservation and author slot required')
    fixed(gate['source'])
    if gate['source']['path'] != str(Path(__file__)):
        raise ValueError('actual author source differs')
    mutable = {str(D / name) for name in ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json',
                                         'source-gate.json', 'root-activation.json')}
    if any(row['path'] in mutable for row in gate['input_records']):
        raise ValueError('live own mutable control in fixed input loop')
    controls = []
    for name in ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json', 'source-gate.json', 'root-activation.json'):
        path = D / name
        raw = path.read_bytes()
        controls.append({**file_pin(path, raw), 'base64': base64.b64encode(raw).decode()})
    return plan, gate, author, entry, controls, (gate_raw, author_raw, root_raw)


def consume(key_name, gate, author, entry, controls, raw_roles):
    for row in controls:
        fixed(row)
    if tuple((D / name).read_bytes() for name in
             ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json')) != raw_roles:
        raise ValueError('immediate full role/gate CAS differs')
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / ('.author-' + key_name + '.tmp')
    save(temporary, author)
    os.replace(temporary, D / 'command-ledger.json')


def post_controls(controls, author):
    for row in controls:
        if row['path'] == str(D / 'command-ledger.json'):
            if Path(row['path']).read_bytes() != encoded(author):
                raise ValueError('exact author one-slot transition differs')
        else:
            fixed(row)

def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R248 baseline120s')))
    signal.alarm(120)
    plan, gate, author, entry, controls, raw_roles = role_gate('baseline')
    verified = verify_contract(plan, gate)
    command = next(row for row in verified['commands'] if row['id'] == 'baseline')
    if (sys.argv != command['launcher_argv'][1:] or Path.cwd() != ROOT
            or gate['launcher_argv'] != command['launcher_argv'] or gate['argv'] != command['launcher_argv']
            or gate['cwd'] != command['cwd'] or gate['finite_env'] != command['finite_env']
            or gate['timeout_seconds'] != command['timeout_seconds'] or command['timeout_seconds'] != 120):
        raise ValueError('exact baseline command/cwd/env/cap differs')
    out = D / 'implementation/baseline'
    artifacts = {}
    scripts = []
    if len(gate['scripts']) != 2 or {row['path'] for row in gate['scripts']} != set(plan['scope']['new_author_scripts']):
        raise ValueError('exact two new author scripts required')
    for row in gate['scripts'] + [gate['prerequisite_source']]:
        scripts.append({**identity(row), 'base64': base64.b64encode(fixed(row)).decode()})
    source_rows = []
    for row in verified['source']['sources']:
        path = Path(row['path'])
        raw = path.read_bytes()
        physical = out / 'sources' / path.relative_to(ROOT)
        artifacts[physical] = raw
        source_rows.append({**file_pin(path, raw), 'mode': path.stat().st_mode,
                            'base64': base64.b64encode(raw).decode(), 'physical': file_pin(physical, raw),
                            'historical_original': identity(row)})
    fixture_before = fixed(gate['fixture_before_pin'])
    fixture_after = Path(verified['fixture_after']['path']).read_bytes()
    artifacts[out / 'fixture-before.py'] = fixture_before
    artifacts[out / 'fixture-after.py'] = fixture_after
    snapshot = {'round': 'R248', 'overlay': 'R245', 'sources': source_rows,
                'protected': verified['source']['protected'], 'scripts': scripts,
                'historical_registry': verified['missing_registry'],
                'history_observations': verified['history_observations'], 'explicit_maps': verified['explicit_maps'],
                'sidecar_states': verified['sidecars'], 'commands': verified['commands'],
                'fixture_before': gate['fixture_before_pin'], 'fixture_after': verified['fixture_after'],
                'all_historical_bytes_available': False, 'qualification': verified['status'],
                'input_records': gate['input_records']}
    artifacts[out / 'source-index.json'] = encoded(snapshot)
    artifacts[out / 'historical-unavailable.json'] = encoded({'registry': verified['missing_registry'],
         'all_historical_bytes_available': False, 'status': verified['status']})
    invocation = {'round': 'R248', 'overlay': 'R245', 'command': 'baseline',
                  'argv': command['launcher_argv'], 'launcher_argv': command['launcher_argv'],
                  'cwd': command['cwd'], 'finite_env': command['finite_env'], 'timeout_seconds': 120,
                  'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'],
                  'controls_before': controls, 'source': gate['source'], 'outer_capture': gate['transport'],
                  'independent_tool_streams': None}
    artifacts[out / 'invocation.json'] = encoded(invocation)
    if any(path.exists() or path.is_symlink() for path in [*artifacts, out / 'result.json']):
        raise ValueError('every baseline output must be absent and nonsymlink')
    consume('baseline', gate, author, entry, controls, raw_roles)
    for path, raw in artifacts.items():
        save(path, raw)
    post = verify_contract(plan, gate)
    for row in scripts:
        fixed(row)
    post_controls(controls, author)
    files = [path for path in out.rglob('*') if path.is_file() and not path.is_symlink()]
    result = {'round': 'R248', 'overlay': 'R245', 'command': 'baseline', 'exit_code': 0,
              'attempt': 1, 'retry': 0, 'test_execution': False, 'product_commands': 0,
              'qualification': post['status'], 'all_historical_bytes_available': False,
              'candidate': file_pin(out / 'source-index.json'), 'outputs': [file_pin(path) for path in sorted(files)],
              'historical_unavailable': post['missing_registry'], 'history_observations': post['history_observations'],
              'input_records': gate['input_records'], 'invocation': invocation,
              'runtime_evidence': None, 'actual_resources': None}
    save(out / 'result.json', result)
    signal.alarm(0)
    print(json.dumps({'command': 'baseline', 'exit_code': 0, 'historical_unavailable_count': len(post['missing_registry']),
                      'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        if sys.argv != [str(D / 'implementation/prepare-evidence.py'), 'baseline']:
            raise ValueError('exact R248 baseline launcher required')
        main()
    except BaseException as error:
        signal.alarm(0)
        out = D / 'implementation/baseline'
        out.mkdir(parents=True, exist_ok=True)
        if not (out / 'result.json').exists():
            save(out / 'result.json', {'round': 'R248', 'command': 'baseline', 'exit_code': 1,
                 'attempt': 1, 'retry': 0, 'exception': {'type': type(error).__name__, 'message': str(error),
                 'traceback': traceback.format_exc()}, 'runtime_evidence': None})
        print(json.dumps({'command': 'baseline', 'exit_code': 1, 'result_pin': file_pin(out / 'result.json')},
                         ensure_ascii=False))
        raise SystemExit(1)
