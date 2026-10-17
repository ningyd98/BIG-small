"""ROOT final source/native/history review and sole baseline reservation, stdlib only."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A / 'round242-p6-t2-writer-barrier-condition-synchronization-20261015'
E = A / 'round245-p6-t2-missing-temporary-evidence-continuation-20261015'
F = A / 'round247-p6-t2-runner-durable-source-preparation-20261015'
checks = []

def identity(x):
    return {k: x[k] for k in ('path', 'bytes', 'sha256')}

def key(x):
    return tuple(x[k] for k in ('path', 'bytes', 'sha256'))

def pin(p, data=None):
    data = p.read_bytes() if data is None else data
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def check(label, ok, **facts):
    checks.append({'label': label, 'ok': bool(ok), **facts})

def fixed(x, label='fixed'):
    p = Path(x['path'])
    data = p.read_bytes() if p.is_file() and not p.is_symlink() else None
    actual = None if data is None else pin(p, data)
    check(label, actual == identity(x), expected=identity(x), actual=actual)
    return data

def encoded(x):
    return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()

def save(p, value):
    raw = value if isinstance(value, bytes) else encoded(value)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as stream:
        stream.write(raw)
    check('exclusive_saved_full_bytes', p.read_bytes() == raw, path=str(p))

def native(record):
    fixed(record, 'native_record')
    obj = json.loads(Path(record['path']).read_bytes())
    check('native_actual_null_unknowns', obj['actual_tool_return'] == {}
          and obj['numeric_exit'] is None and obj['independent_stdout'] is None
          and obj['independent_stderr'] is None)
    return obj['tool_arguments']

def add_source(patch, target):
    lines = patch.splitlines()
    check('native_add_header', lines[:2] == ['*** Begin Patch', '*** Add File: ' + str(target)]
          and lines[-1] == '*** End Patch')
    body = lines[2:-1]
    check('native_add_all_lines', all(line.startswith('+') for line in body))
    return ('\n'.join(line[1:] for line in body) + '\n').encode()

def update_source(raw, patch, target):
    lines = patch.splitlines()
    check('native_update_header', lines[:2] == ['*** Begin Patch', '*** Update File: ' + str(target)]
          and lines[-1] == '*** End Patch')
    chunks, current = [], None
    for line in lines[2:-1]:
        if line.startswith('@@'):
            if current is not None:
                chunks.append(current)
            current = []
        else:
            if current is None or not line or line[0] not in ' +-':
                raise ValueError('unknown native update source shape')
            current.append(line)
    if current is not None:
        chunks.append(current)
    for chunk in chunks:
        old = ('\n'.join(x[1:] for x in chunk if x[0] in ' -') + '\n').encode()
        new = ('\n'.join(x[1:] for x in chunk if x[0] in ' +') + '\n').encode()
        check('native_unique_update_hunk', bool(old) and raw.count(old) == 1)
        if not old or raw.count(old) != 1:
            raise ValueError('native hunk not unique')
        raw = raw.replace(old, new, 1)
    return raw

plan = json.loads((D / 'plan.json').read_bytes())
overlay = json.loads((E / 'plan.json').read_bytes())
observation = json.loads((D / 'input-observation.json').read_bytes())
unavailable = json.loads((E / 'input-observation.json').read_bytes())
index = json.loads(Path(observation['protected_authority']['index']['path']).read_bytes())
report_path = D / 'implementation/change-report.json'
report_pin = {'path': str(report_path), 'bytes': 189219,
              'sha256': 'e91ff348898506fbf556a7accd98d2590f86b9a5ad77fef94a37b144505d53ab'}
report = json.loads(fixed(report_pin, 'final_source_report'))
reference_report = json.loads((F / 'implementation/change-report.json').read_bytes())
scripts = [identity(x) for x in report['scripts']]
expected_scripts = {
    str(D / 'implementation/prepare-evidence.py'): (19065, '0c236e16c7cf3d3f7bcb7267a060de261ce5d1f9fa730f3a82f670736fcfd39d'),
    str(D / 'implementation/run-command.py'): (46895, 'de3d17cad6a467856e6b31f71e360536aec9551807e7c6e8d35d74a3e48c0a2f')}
for row in report['scripts']:
    raw = fixed(row, 'final_author_source')
    check('frozen_author_source_expected', (row['bytes'], row['sha256']) == expected_scripts[row['path']])
    check('author_fullbase64', raw == base64.b64decode(row['base64'], validate=True))
fixture = report['fixture']
before = fixed(fixture['before'], 'fixture_complete_before')
after = fixed(fixture['after'], 'fixture_current_after')
old, new = [plan['scope']['exact_change'][k].encode() for k in ('before', 'after')]
check('exact_fixture_two_byte_delta', before.count(old) == 1 and after == before.replace(old, new, 1)
      and len(before) - len(after) == 2)
check('fixture_R239_complete_archive', before == fixed(observation['frozen_fixture_archive']['archive']))
fixed(fixture['diff'], 'limited_fixture_diff')
fixed(report['before_manifest'], 'complete_before_manifest')
fixed(report['runner_candidate'], 'immutable_runner_candidate')
check('runner_complete_candidate_equality', Path(report['runner_candidate']['path']).read_bytes()
      == Path(D / 'implementation/run-command.py').read_bytes())
fixed(report['durable_runner_reference'], 'durable_reference')
check('reference_full_old_bytes', Path(report['durable_runner_reference']['path']).read_bytes()
      == (A / 'round237-p6-t2-original-verification-budget-intersection-20261015/implementation/run-command.py').read_bytes())
fixed(report['runner_diff'], 'runner_limited_diff')
records = report['native_receipts']
patches = [native(x) for x in records]
check('fixture_exact_native_reconstruction', update_source(before, patches[0], Path(fixture['after']['path'])) == after)
prepare_path = D / 'implementation/prepare-evidence.py'
prepare_added = add_source(patches[1], prepare_path)
prepare_final = update_source(prepare_added, patches[2], prepare_path)
check('prepare_native_complete_reconstruction', prepare_final == prepare_path.read_bytes())
runner_path = D / 'implementation/run-command.py'
check('runner_native_complete_reconstruction', add_source(patches[3], runner_path) == runner_path.read_bytes())
for row in report['current_sources27']:
    fixed(row, 'current27')
for row in report['protected211']:
    fixed(row, 'protected211')
check('current_protected_exact_counts', len(report['current_sources27']) == 27 and len(report['protected211']) == 211)
missing = {key(x['original']): x for x in unavailable['known_missing']}
for row in missing.values():
    p = Path(row['original']['path'])
    check('explicit_unavailable_path', not p.exists() and not p.is_symlink(),
          original=row['original'], hash_match=None)
maps = {key(e['original']): e['resolution']['pin'] for e in index['resolved_history']['entries']}
for pair in [observation['frozen_fixture_archive']] + observation['explicit_R239_settlement_history']:
    maps[key(pair['original'])] = pair['archive']
for row in index['input_records'] + index['history']:
    if key(row) in missing:
        check('exact_unavailable_disposition', True, original=identity(row), hash_match=None)
    else:
        target = maps.get(key(row), row)
        data = fixed(target, 'available_historical_record')
        check('historical_full_equivalence', data is not None and len(data) == row['bytes']
              and hashlib.sha256(data).hexdigest() == row['sha256'])
for row in unavailable['sidecar_observations']:
    p = Path(row['path'])
    check('old_sidecar_absent', not p.exists() and not p.is_symlink(), path=str(p))
draft_path = D / 'root-unreserved-literal-transports.json'
drafts = json.loads(draft_path.read_bytes())
effective = json.loads(json.dumps(plan['commands']))
change = overlay['execution_override']['replace_exact_child_argument']
for command in effective:
    if command['id'] == 'red':
        command['child_argv'] = [change['new'] if x == change['old'] else x for x in command['child_argv']]
    draft = drafts[command['id']]
    check('literal_argv_env_cwd_exact', draft['argv'] == command['launcher_argv']
          and draft['finite_env'] == command['finite_env'] and draft['cwd'] == command['cwd'])
    for path in [D / 'implementation' / command['id'], Path(draft['stdout_path']), Path(draft['stderr_path'])]:
        check('fresh_output_absent', not path.exists() and not path.is_symlink(), path=str(path))
controls = {name: (D / name).read_bytes() for name in
            ('source-gate.json', 'script-gate.json', 'root-activation.json',
             'command-ledger.json', 'root-command-ledger.json')}
for name in ('command-ledger.json', 'root-command-ledger.json'):
    obj = json.loads(controls[name])
    check('all_three_original_slots_held', all(x['state'] == 'HELD' and x['used'] == 0
          and x['remaining'] == 1 and x['total'] == 1 for x in obj['commands'].values()))
failures = [x for x in checks if not x['ok']]
if failures:
    save(D / 'root-source-review-failure.json', {'checks': checks, 'failures': failures})
    print(json.dumps({'status': 'STOP', 'failures': failures[:3]}, ensure_ascii=False))
    raise SystemExit(1)
before_dir = D / 'before/root-source-gate-baseline-reservation'
pairs = []
for name, raw in controls.items():
    original = pin(D / name, raw)
    archive = before_dir / name
    save(archive, raw)
    pairs.append({'original': original, 'archive': pin(archive), 'base64': base64.b64encode(raw).decode()})
save(before_dir / 'index.json', {'records': pairs})
fixed_inputs = [report_pin, pin(F / 'implementation/change-report.json'), pin(draft_path),
                fixture['before'], report['before_manifest'], report['runner_candidate'],
                report['durable_runner_reference'], report['runner_diff'], fixture['diff']] + records + scripts
for directory in (D, E, A / 'round246-p6-t2-author-count-field-display-disposition-20261015', F):
    for name in ('plan.md', 'plan.json'):
        fixed_inputs.append(pin(directory / name))
fixed_inputs.extend([pin(D / 'input-observation.json'), pin(E / 'input-observation.json'),
                     pin(D / 'input-check.json'), pin(D / 'root-author-prepare-full-source-read-actual.json'),
                     pin(D / 'root-author-runner-complete-two-halves-read-actuals.json')])
prerequisite = next(x for x in observation['inputs'] if x['path'].endswith('/r235_startup_prerequisite.py'))
gates = {}
reservation_id = 'R242-baseline-once-20261015'
for command in effective:
    name = command['id']
    gates[name] = {'state': 'APPROVED' if name == 'baseline' else 'HELD',
                   'full_source_reviewed': True, 'reservation_id': reservation_id if name == 'baseline' else None,
                   'source': next(x for x in scripts if x['path'].endswith(
                       '/prepare-evidence.py' if name == 'baseline' else '/run-command.py')),
                   'input_records': fixed_inputs, 'argv': command.get('child_argv', command['launcher_argv']),
                   'launcher_argv': command['launcher_argv'], 'cwd': command['cwd'],
                   'finite_env': command['finite_env'], 'timeout_seconds': command['timeout_seconds'],
                   'transport': drafts[name], 'overlay_plan_pin': pin(E / 'plan.json'),
                   'overlay_observation_pin': pin(E / 'input-observation.json'), 'fixture_before_pin': fixture['before'],
                   'context_history': [{'original': x['original'], 'archive': x['archive']} for x in pairs],
                   'scripts': scripts, 'prerequisite_source': identity(prerequisite), 'source_index_pin': None}
root_role = json.loads(controls['root-command-ledger.json'])
root_role['commands']['baseline'].update(state='RESERVED_BY_ROOT', used=1, remaining=0,
                                        reservation_id=reservation_id)
source_review = {'status': 'APPROVED_FOR_BASELINE_ONLY_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
                 'checks': checks, 'reviewed_full_sources': scripts, 'exact_fixture_delta': fixture,
                 'all_historical_bytes_available': False, 'historical_unavailable_count': 35,
                 'execution_released': ['baseline'], 'T2_complete': False, 'T12_complete': False}
mutations = {
    'source-gate.json': encoded(source_review),
    'script-gate.json': encoded({'round': 'R242', 'commands': gates}),
    'root-command-ledger.json': encoded(root_role),
    'root-activation.json': encoded({'status': 'BASELINE_RESERVED_ONCE', 'execution_released': ['baseline'],
                                    'reservation_id': reservation_id, 'transport': drafts['baseline']})}
for name, raw in controls.items():
    if (D / name).read_bytes() != raw:
        raise ValueError('immediate complete control CAS differs')
for name, raw in mutations.items():
    temporary = D / ('.root-source-review-' + name + '.tmp')
    save(temporary, raw)
    os.replace(temporary, D / name)
save(D / 'root-source-review-and-baseline-reservation.json',
     {'status': source_review['status'], 'checks': len(checks), 'before_index': pin(before_dir / 'index.json'),
      'source_gate': pin(D / 'source-gate.json'), 'script_gate': pin(D / 'script-gate.json'),
      'root_ledger': pin(D / 'root-command-ledger.json'), 'reservation_id': reservation_id,
      'transport': drafts['baseline'], 'author_role_unchanged': pin(D / 'command-ledger.json'),
      'new_slots': 0})
print(json.dumps({'status': 'BASELINE_RESERVED_ONCE', 'checks': len(checks),
                  'reservation_id': reservation_id, 'historical_unavailable': 35}, ensure_ascii=False))
