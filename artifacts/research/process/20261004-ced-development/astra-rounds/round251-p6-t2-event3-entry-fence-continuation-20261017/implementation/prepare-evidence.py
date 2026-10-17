"""R251 original-budget source preparation with explicit historical evidence loss."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round251-p6-t2-event3-entry-fence-continuation-20261017'
ORIGIN = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round223-p6-t2-public-writer-binding-race-20261015'


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




def control_paths():
    links = read_json(D / 'ledger-links.json')
    expected = {'author_ledger': str(ORIGIN / 'command-ledger.json'),
                'ROOT_ledger': str(ORIGIN / 'root-command-ledger.json')}
    if any(links[name] != value for name, value in expected.items()) or links['new_slots'] != 0:
        raise ValueError('original R223 budget links required')
    return [D / 'script-gate.json', Path(links['author_ledger']), Path(links['ROOT_ledger']),
            D / 'source-gate.json', D / 'root-activation.json']


def verify_contract(plan, gate):
    observation = json.loads(fixed(plan['inputs']['observation']))
    source = json.loads(fixed(plan['inputs']['legal_RED_baseline']))
    if (len(source['sources']) != 27 or len(source['protected']) != 211 or len(source['scripts']) != 3
            or len(source['history_observations']) != 1223 or len(source['explicit_maps']) != 26
            or len(source['input_records']) != 32 or len(observation['inputs']) != 379):
        raise ValueError('actual R24827/211/3/1223/26/32 and R251379 schema required')
    if (observation['prior_exact_maps'] != source['explicit_maps']
            or observation['baseline_input_records'] != source['input_records']):
        raise ValueError('exact inherited maps and input record generations required')
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
    if (len(observation['event3_before']) != 3 or len(observation['R248_final_before_maps']) != 7
            or len(observation['R223_role_before']) != 2):
        raise ValueError('exact event3/final7/original2 role history required')
    pairs = (list(source['explicit_maps']) + observation['event3_before']
             + observation['R248_final_before_maps'] + observation['R223_role_before'])
    links = read_json(D / 'ledger-links.json')
    allowed = {str(path) for path in control_paths()}
    allowed.update(observation['current_context'][name]['path'] for name in ('STATE', 'PHASE'))
    for pair in links['context_history'] + gate['context_history']:
        if pair['original']['path'] not in allowed:
            raise ValueError('extra mapping outside authorized mutable context')
        pairs.append(pair)
    mappings = {}
    for pair in pairs:
        raw = fixed(pair['archive'])
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (pair['original']['bytes'], pair['original']['sha256']):
            raise ValueError('full physical original/archive equivalence differs')
        if 'base64' in pair and base64.b64decode(pair['base64'], validate=True) != raw:
            raise ValueError('mapped full original base64 differs')
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
    context = observation['current_context']
    for name, rows in [('inputs379', observation['inputs']), ('baseline_inputs32', source['input_records']),
                       ('current_context', [context['STATE'], context['PHASE']] + context['R248_final_controls']),
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
            historical(row['original'], {'list': 'history_observations1223', 'ordinal': ordinal})
        else:
            historical(row['original'], {'list': 'history_observations1223', 'ordinal': ordinal}, row['resolved'])
    old_targets = {row['original']['path']: row for row in observation['event3_before']}
    after_targets = {row['path']: row for row in gate['target_after_pins']}
    if len(after_targets) != 3 or set(after_targets) != set(old_targets):
        raise ValueError('exact three current event source pins required')
    if len(observation['current_sources']) != 27 or len(observation['protected']) != 211:
        raise ValueError('current27/protected211 observation required')
    source_by_path = {row['path']: row for row in source['sources']}
    if len(source_by_path) != 27:
        raise ValueError('unique27 source paths required')
    for observed in observation['current_sources']:
        row = source_by_path[observed['original']['path']]
        raw = base64.b64decode(row['base64'], validate=True)
        if (file_pin(Path(row['path']), raw) != identity(row) or fixed(row['physical']) != raw
                or fixed(observed['physical']) != raw or identity(observed['original']) != identity(row)):
            raise ValueError('complete accepted R248 source generation differs')
        if row['path'] in old_targets:
            before = old_targets[row['path']]
            if fixed(before['archive']) != raw or identity(before['original']) != identity(row):
                raise ValueError('exact event3 physical before differs')
            fixed(after_targets[row['path']])
        elif Path(row['path']).read_bytes() != raw:
            raise ValueError('one of24 unowned sources changed')
        if Path(row['path']).stat().st_mode != row['mode']:
            raise ValueError('current source mode differs')
    fixed(plan['inputs']['frozen_fixture'])
    for row in observation['protected'] + source['protected']:
        fixed(row)
    for row in source['scripts']:
        if fixed(row) != base64.b64decode(row['base64'], validate=True):
            raise ValueError('frozen R248 script full bytes differ')
    inventory = json.loads(fixed(gate['fence_inventory_pin']))
    if (type(inventory['entries']) is not list or len(inventory['entries']) != 72
            or {(row['path'], row['method']) for row in inventory['entries']}
            != {(row['path'], row['method']) for row in observation['writer_inventory']}):
        raise ValueError('exact72 unique writer source entries required')
    fixed(gate['source_report_pin'])
    sidecars = observation['old_absent_sidecars']
    if len(sidecars) != 90 or len({row['path'] for row in sidecars}) != 90:
        raise ValueError('exact90 historical sidecar paths required')
    for row in sidecars:
        path = Path(row['path'])
        if row['exists'] is not False or path.exists() or path.is_symlink():
            raise ValueError('old90 sidecar state differs')
    databases = observation['retained_workspace_databases']
    if len(databases) != 12 or len({row['pin']['path'] for row in databases}) != 12:
        raise ValueError('twelve current persistent workspace databases required')
    count = 0
    for row in databases:
        fixed(row['pin'])
        if key(row['pin']) in registry:
            raise ValueError('current persistent DB cannot use historical missing exception')
        for side in row['sidecars']:
            path = Path(side['path'])
            if (side['exists'] is not False or side['is_symlink'] is not False
                    or path.exists() or path.is_symlink()):
                raise ValueError('current workspace database sidecar state differs')
            count += 1
    if count != 36:
        raise ValueError('exact36 current workspace sidecar states required')
    return {'status': 'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
            'source': source, 'observation': observation, 'missing_registry': missing,
            'history_observations': observations, 'explicit_maps': pairs, 'sidecars': sidecars,
            'retained_workspace_databases': databases, 'commands': plan['commands'],
            'fixture_after': plan['inputs']['frozen_fixture'], 'all_historical_bytes_available': False}


def role_gate(key_name):
    plan = read_json(D / 'plan.json')
    paths = control_paths()
    gate_raw, author_raw, root_raw = [path.read_bytes() for path in paths[:3]]
    gate = json.loads(gate_raw)['commands'][key_name]
    author, root = json.loads(author_raw), json.loads(root_raw)
    entry, reservation = author['commands'][key_name], root['commands'][key_name]
    normative = next(row for row in plan['commands'] if row['id'] == key_name)
    execution = {name: value for name, value in normative.items()
                 if name not in {'authorized', 'used', 'remaining', 'state'}}
    for role_entry in (entry, reservation):
        continuation = role_entry['continuation']
        if (continuation['round'] != 'R251' or continuation['not_a_new_budget'] is not True
                or continuation['plan'] != file_pin(D / 'plan.json')
                or continuation['execution_contract'] != execution
                or (role_entry['authorized'], role_entry['used'] + role_entry['remaining']) != (1, 1)):
            raise ValueError('exact original R223 per-command continuation required')
    if (key_name == 'root_settlement' or entry.get('author_executable') is not True
            or gate['state'] != 'APPROVED' or gate['full_source_reviewed'] is not True
            or entry['state'] != 'HELD' or entry['used'] != 0 or entry['remaining'] != 1
            or reservation['state'] != 'RESERVED_BY_ROOT' or reservation['used'] != 1
            or reservation['remaining'] != 0 or gate['reservation_id'] != reservation['reservation_id']
            or reservation['gate_pin'] != file_pin(paths[0], gate_raw)):
        raise ValueError('exact one-use ROOT reservation and executable author slot required')
    fixed(gate['source'])
    if gate['source']['path'] != str(Path(__file__)):
        raise ValueError('actual author source differs')
    mutable = {str(path) for path in paths}
    if any(row['path'] in mutable for row in gate['input_records']):
        raise ValueError('live five mutable controls in fixed input loop')
    expected_scripts = set(plan['scope']['new_author_scripts'] + [plan['scope']['new_ROOT_script']])
    if len(gate['scripts']) != 3 or {row['path'] for row in gate['scripts']} != expected_scripts:
        raise ValueError('exact three reviewed new scripts required')
    for row in gate['scripts'] + [gate['prerequisite_source']]:
        fixed(row)
    controls = []
    for path in paths:
        raw = path.read_bytes()
        controls.append({**file_pin(path, raw), 'base64': base64.b64encode(raw).decode()})
    return plan, gate, author, entry, controls, (gate_raw, author_raw, root_raw)


def consume(key_name, gate, author, entry, controls, raw_roles):
    for row in controls:
        fixed(row)
    paths = control_paths()
    if tuple(path.read_bytes() for path in paths[:3]) != raw_roles:
        raise ValueError('immediate full original role/gate CAS differs')
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = ORIGIN / ('.r251-author-' + key_name + '.tmp')
    save(temporary, author)
    os.replace(temporary, paths[1])


def post_controls(controls, author):
    author_path = str(control_paths()[1])
    for row in controls:
        if row['path'] == author_path:
            if Path(row['path']).read_bytes() != encoded(author):
                raise ValueError('exact original author one-slot transition differs')
        else:
            fixed(row)

def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R251 prepare_green120s')))
    signal.alarm(120)
    plan, gate, author, entry, controls, raw_roles = role_gate('prepare_green')
    verified = verify_contract(plan, gate)
    command = next(row for row in verified['commands'] if row['id'] == 'prepare_green')
    if (sys.argv != command['launcher_argv'][1:] or Path.cwd() != ROOT
            or gate['launcher_argv'] != command['launcher_argv'] or gate['argv'] != command['launcher_argv']
            or gate['cwd'] != command['cwd'] or gate['finite_env'] != command['finite_env']
            or gate['timeout_seconds'] != command['timeout_seconds'] or command['timeout_seconds'] != 120):
        raise ValueError('exact original prepare_green command/cwd/env/cap differs')
    out = D / 'implementation/prepare_green'
    artifacts = {}
    scripts = [{**identity(row), 'base64': base64.b64encode(fixed(row)).decode()}
               for row in gate['scripts'] + [gate['prerequisite_source']]]
    if len(scripts) != 4 or len({row['path'] for row in scripts}) != 4:
        raise ValueError('new snapshot requires exactly four source scripts')
    source_rows = []
    for row in verified['source']['sources']:
        path = Path(row['path'])
        raw = path.read_bytes()
        physical = out / 'sources' / path.relative_to(ROOT)
        artifacts[physical] = raw
        source_rows.append({**file_pin(path, raw), 'mode': path.stat().st_mode,
                            'base64': base64.b64encode(raw).decode(), 'physical': file_pin(physical, raw),
                            'historical_original': identity(row)})
    snapshot = {'round': 'R251', 'origin_round': 'R223', 'sources': source_rows,
                'protected': verified['source']['protected'], 'scripts': scripts,
                'historical_registry': verified['missing_registry'],
                'history_observations': verified['history_observations'], 'explicit_maps': verified['explicit_maps'],
                'sidecar_states': verified['sidecars'], 'commands': verified['commands'],
                'fixture_after': verified['fixture_after'], 'target_after_pins': gate['target_after_pins'],
                'retained_workspace_databases': verified['retained_workspace_databases'],
                'fence_inventory_pin': gate['fence_inventory_pin'], 'source_report_pin': gate['source_report_pin'],
                'controls_before': controls, 'parent_source_index': plan['inputs']['legal_RED_baseline'],
                'all_historical_bytes_available': False, 'qualification': verified['status'],
                'input_records': gate['input_records']}
    artifacts[out / 'source-index.json'] = encoded(snapshot)
    artifacts[out / 'historical-unavailable.json'] = encoded({'registry': verified['missing_registry'],
         'all_historical_bytes_available': False, 'status': verified['status']})
    invocation = {'round': 'R251', 'origin_round': 'R223', 'command': 'prepare_green',
                  'argv': command['launcher_argv'], 'launcher_argv': command['launcher_argv'],
                  'cwd': command['cwd'], 'finite_env': command['finite_env'], 'timeout_seconds': 120,
                  'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'],
                  'controls_before': controls, 'source': gate['source'], 'outer_capture': gate['transport'],
                  'independent_tool_streams': None}
    artifacts[out / 'invocation.json'] = encoded(invocation)
    if any(path.exists() or path.is_symlink() for path in [*artifacts, out / 'result.json']):
        raise ValueError('every prepare_green output must be absent and nonsymlink')
    consume('prepare_green', gate, author, entry, controls, raw_roles)
    for path, raw in artifacts.items():
        save(path, raw)
    post = verify_contract(plan, gate)
    for row in scripts:
        fixed(row)
    post_controls(controls, author)
    files = [path for path in out.rglob('*') if path.is_file() and not path.is_symlink()]
    result = {'round': 'R251', 'origin_round': 'R223', 'command': 'prepare_green', 'exit_code': 0,
              'attempt': 1, 'retry': 0, 'test_execution': False, 'product_commands': 0,
              'qualification': post['status'], 'all_historical_bytes_available': False,
              'candidate': file_pin(out / 'source-index.json'), 'outputs': [file_pin(path) for path in sorted(files)],
              'historical_unavailable': post['missing_registry'], 'history_observations': post['history_observations'],
              'input_records': gate['input_records'], 'invocation': invocation,
              'runtime_evidence': None, 'actual_resources': None}
    save(out / 'result.json', result)
    signal.alarm(0)
    print(json.dumps({'command': 'prepare_green', 'exit_code': 0,
                      'historical_unavailable_count': len(post['missing_registry']),
                      'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        if sys.argv != [str(D / 'implementation/prepare-evidence.py'), 'green']:
            raise ValueError('exact R251 prepare_green launcher required')
        main()
    except BaseException as error:
        signal.alarm(0)
        out = D / 'implementation/prepare_green'
        out.mkdir(parents=True, exist_ok=True)
        if not (out / 'result.json').exists():
            save(out / 'result.json', {'round': 'R251', 'command': 'prepare_green', 'exit_code': 1,
                 'attempt': 1, 'retry': 0, 'exception': {'type': type(error).__name__, 'message': str(error),
                 'traceback': traceback.format_exc()}, 'runtime_evidence': None})
        print(json.dumps({'command': 'prepare_green', 'exit_code': 1, 'result_pin': file_pin(out / 'result.json')},
                         ensure_ascii=False))
        raise SystemExit(1)
