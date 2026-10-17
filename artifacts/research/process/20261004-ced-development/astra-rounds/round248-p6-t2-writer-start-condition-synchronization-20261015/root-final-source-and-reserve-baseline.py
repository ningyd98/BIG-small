"""ROOT complete final source/history/native review; sole baseline reservation, stdlib only."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A / 'round248-p6-t2-writer-start-condition-synchronization-20261015'
checks = []
def identity(x):
    return {k: x[k] for k in ('path', 'bytes', 'sha256')}
def key(x):
    return tuple(x[k] for k in ('path', 'bytes', 'sha256'))
def pin(p, raw=None):
    raw = p.read_bytes() if raw is None else raw
    return {'path': str(p), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
def check(label, ok, **facts):
    checks.append({'label': label, 'ok': bool(ok), **facts})
def fixed(row, label='fixed'):
    p = Path(row['path'])
    raw = p.read_bytes() if p.is_file() and not p.is_symlink() else None
    check(label, raw is not None and pin(p, raw) == identity(row), expected=identity(row))
    return raw
def encoded(x):
    return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def save(p, x):
    raw = x if isinstance(x, bytes) else encoded(x)
    with p.open('xb') as stream:
        stream.write(raw)
    if p.read_bytes() != raw:
        raise ValueError('exclusive metadata write differs')
    return pin(p, raw)

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

plan_pin = {'path': str(D / 'plan.json'), 'bytes': 28368,
            'sha256': '67eafc3d136e5a38bc46c21d55c655ba464f69de0467bf2f73ca464956bafb40'}
plan_raw = fixed(plan_pin, 'actual_Astra_plan_JSON')
plan = json.loads(plan_raw)
fixed({'path': str(D / 'plan.md'), 'bytes': 4933,
       'sha256': 'b2f6ab2ea3e73e5979a3b98fdcf4bb6b21f86c8ffe0a3f45d8d677392d2045f0'}, 'actual_Astra_plan_MD')
check('durable_candidate_equals_plan', (D / 'prepared-plan-candidate.json').read_bytes() == plan_raw)
observation = json.loads(fixed(plan['inputs']['observation'], 'actual_observation'))
source = json.loads(fixed(plan['inputs']['current_baseline'], 'actual_R242_baseline'))
check('actual_R242_schema_counts', len(source['sources']) == 27 and len(source['protected']) == 211
      and len(source['scripts']) == 3 and len(source['history_observations']) == 812
      and len(source['explicit_maps']) == 13 and len(source['input_records']) == 28)
check('exact_input_count344', len(observation['inputs']) == 344)
maps = {}
pairs = observation['history_authority']['explicit_maps'] + [
    observation['additional_fixture_generation']] + observation['R242_final_settlement_maps']
check('exact_declared_map_sets', len(observation['history_authority']['explicit_maps']) == 13
      and len(observation['R242_final_settlement_maps']) == 7)
for pair in pairs:
    raw = fixed(pair['archive'], 'full_physical_historical_generation')
    check('full_archive_original_equivalence', raw is not None and len(raw) == pair['original']['bytes']
          and hashlib.sha256(raw).hexdigest() == pair['original']['sha256'])
    maps[key(pair['original'])] = pair['archive']
registry = {key(x['original']): x for x in observation['known_missing']}
check('unique_exact_missing35', len(registry) == 35)
for row in observation['known_missing']:
    original = row['original']
    p = Path(original['path'])
    check('registered_current_unavailability', not p.exists() and not p.is_symlink()
          and row['current_bytes'] is None and row['current_sha256'] is None and row['hash_match'] is None,
          original=original)
    authority = row['authority']
    container = json.loads(fixed(authority['pin'], 'registered_authority_container'))
    ordinal = authority['ordinal']
    if authority['selector'] == 'input_records':
        authoritative = container['input_records'][ordinal]
    elif authority['selector'] == 'new_retained_databases.pin':
        authoritative = container['new_retained_databases'][ordinal]['pin']
    else:
        raise ValueError('unrecognized exact authority selector')
    check('registered_exact_identity', identity(authoritative) == identity(original))
for row in observation['inputs']:
    if key(row) in registry:
        check('direct_explicit_unavailable', True, original=identity(row), hash_match=None)
    else:
        target = maps.get(key(row), row)
        raw = fixed(target, 'fixed_available_input344')
        check('fixed_input_equivalent_bytes', raw is not None and len(raw) == row['bytes']
              and hashlib.sha256(raw).hexdigest() == row['sha256'])
        if raw is not None and row['path'].endswith('/invocation.json'):
            invocation = json.loads(raw)
            for control in invocation.get('controls_before', []):
                decoded = base64.b64decode(control['base64'], validate=True)
                check('invocation_own_control_generation_only', pin(Path(control['path']), decoded) == identity(control))
for row in source['history_observations']:
    original = row['original']
    if key(original) in registry:
        check('historical_unavailability_not_hash_pass', row['hash_match'] is None)
    else:
        resolved = row['resolved']
        target = maps.get(key(original), maps.get(key(resolved), resolved))
        raw = fixed(target, 'historical812_available_generation')
        check('historical812_full_equivalence', raw is not None and len(raw) == original['bytes']
              and hashlib.sha256(raw).hexdigest() == original['sha256'])

C = A / 'round250-p6-t2-new-run-provenance-correction-20261015'
correction_pin = pin(C / 'root-source-correction-acceptance.json')
correction = json.loads(fixed(correction_pin, 'ROOT_accepted_R250_correction'))
check('R250_only_static_correction_accepted', correction['status'] == 'ACCEPTED_SOURCE_CORRECTION_ONLY'
      and correction['runtime_execution_count'] == 0)
report_pin = {'path': str(D / 'implementation/change-report.json'), 'bytes': 162277,
              'sha256': '49c5a9856ee174450e33d73ab391c768e9746df52d12987a978b9128a94a05d2'}
report = json.loads(fixed(report_pin, 'original_R248_source_report'))
fixture_before = report['fixture_before']
fixture_after = report['fixture_after']
before = fixed(fixture_before, 'full_c14_fixture_before')
after = fixed(fixture_after, 'current_106f_fixture_after')
delta = plan['scope']['exact_change']
old, new = delta['before'].encode(), delta['after'].encode()
check('unique_two_byte_fixture_delta', before.count(old) == 1
      and after == before.replace(old, new, 1) and len(before) - len(after) == 2
      and len(after) == delta['expected_after_bytes']
      and hashlib.sha256(after).hexdigest() == delta['expected_after_sha256'])
check('fixture_before_equals_pinned_R242_physical', before == fixed(
      observation['additional_fixture_generation']['archive']))
fixed(report['before_manifest'], 'complete_before_manifest')
fixed(report['limited_diff'], 'limited_fixture_diff')
fixed(report['scripts_limited_diff'], 'original_two_script_diff')
old_patches = [native(x) for x in report['native_receipts']]
check('fixture_native_exact_bytes', update_source(before, old_patches[0], Path(fixture_after['path'])) == after)
scripts = []
for ordinal, row in enumerate(report['scripts'], 1):
    original = fixed(row['candidate'], 'immutable_original_R248_candidate')
    check('original_report_full_base64', original == base64.b64decode(row['base64'], validate=True))
    check('original_native_AddFile_fullbytes', add_source(old_patches[ordinal], Path(row['path'])) == original)
    fixed(row['reference'], 'full_R242_script_parent')
    if row['path'].endswith('/run-command.py'):
        check('R250_full_before_equals_original_candidate', original == fixed(correction['runner_before']))
        current = fixed(correction['runner_after'], 'corrected_current_runner')
        check('exact_single_R250_native_update', update_source(original, native(correction['native_receipt']),
              Path(row['path'])) == current)
        check('new_complete_candidate_equal_current', current == fixed(correction['candidate']))
        check('only_provenance_R242_to_R248', original.count(b'This genuine new R242 run only; old bytes not recovered') == 1
              and current == original.replace(b'This genuine new R242 run only; old bytes not recovered',
                  b'This genuine new R248 run only; old bytes not recovered', 1))
        scripts.append(identity(correction['runner_after']))
    else:
        check('unmodified_prepare_equals_original_candidate', fixed(row) == original)
        scripts.append(identity(row))
for row in observation['current_sources']:
    physical = fixed(row['physical'], 'complete_original_physical27')
    expected = fixture_after if row['original']['path'] == fixture_after['path'] else row['original']
    current = fixed(expected, 'current_source27')
    check('source27_exact_allowed_delta', current == (after if expected['path'] == fixture_after['path'] else physical))
for row in observation['protected']:
    fixed(row, 'protected211')
for row in source['scripts']:
    check('old_scripts_full_bytes', fixed(row, 'frozen_script') == base64.b64decode(row['base64'], validate=True))
for row in source['sources']:
    original = base64.b64decode(row['base64'], validate=True)
    resolved = maps.get(key(row), row)
    check('source_index_full_original_generation', fixed(resolved) == original
          and fixed(row['physical']) == original)
    expected = fixture_after if row['path'] == fixture_after['path'] else row
    current = fixed(expected, 'current_source_full27')
    check('current_source_mode_and_bytes', current == (after if row['path'] == fixture_after['path'] else original)
          and Path(row['path']).stat().st_mode == row['mode'])
for row in report['current_sources27'] + report['protected211']:
    fixed(row, 'author_report_current_source_and_protected')
check('current_protected_exact_counts', len(report['current_sources27']) == 27 and len(report['protected211']) == 211)
for row in observation['old_absent_sidecars']:
    p = Path(row['path'])
    check('old90_sidecar_absence', not p.exists() and not p.is_symlink() and row['exists'] is False)
for row in observation['R242_current_persistent_databases']:
    fixed(row['pin'], 'actual_persistent_R242_DB6')
    for side in row['sidecars']:
        p = Path(side['path'])
        check('actual_R242_sidecar18', side['exists'] is False and side['is_symlink'] is False
              and not p.exists() and not p.is_symlink())
context = observation['current_final_context']
for row in [context['STATE'], context['PHASE']] + context['controls']:
    fixed(row, 'current_final_context_exact')
for filename in ('root-command-ledger.json', 'command-ledger.json'):
    q = A / 'round242-p6-t2-writer-barrier-condition-synchronization-20261015' / filename
    roles = json.loads(q.read_bytes())
    check('R242_all_slots_stay_spent', all(x['used'] == 1 and x['remaining'] == 0
          and x['state'].startswith('SPENT') for x in roles['commands'].values()))
draft_path = D / 'root-unreserved-literal-transports.json'
drafts = json.loads(draft_path.read_bytes())
for command in plan['commands']:
    name = command['id']
    draft = drafts[name]
    check('literal_command_environment_and_cwd', draft['argv'] == command['launcher_argv']
          and draft['finite_env'] == command['finite_env'] and draft['cwd'] == command['cwd'])
    for p in [D / 'implementation' / name, Path(draft['stdout_path']), Path(draft['stderr_path'])]:
        check('fresh_output_absent', not p.exists() and not p.is_symlink(), path=str(p))
controls = {name: (D / name).read_bytes() for name in
            ('source-gate.json', 'script-gate.json', 'root-activation.json',
             'command-ledger.json', 'root-command-ledger.json')}
for name in ('command-ledger.json', 'root-command-ledger.json'):
    roles = json.loads(controls[name])
    check('all_three_R248_slots_HELD', set(roles['commands']) == {'baseline','ruff','red'}
          and all(x == {'total':1,'used':0,'remaining':1,'state':'HELD'} for x in roles['commands'].values()))
failures = [x for x in checks if not x['ok']]
if failures:
    save(D / 'root-final-source-gate-failure.json', {'checks': checks, 'failures': failures})
    print(json.dumps({'status':'STOP', 'failures':failures[:3]}, ensure_ascii=False))
    raise SystemExit(1)
before_dir = D / 'before/root-final-source-gate-baseline-reservation'
before_dir.mkdir(parents=True, exist_ok=False)
history = []
for name, raw in controls.items():
    archive = before_dir / name
    save(archive, raw)
    history.append({'original':pin(D/name, raw), 'archive':pin(archive), 'base64':base64.b64encode(raw).decode()})
save(before_dir / 'index.json', {'records':history})
fixed_inputs = [plan_pin, pin(D/'plan.md'), plan['inputs']['observation'], plan['inputs']['current_baseline'],
                report_pin, correction_pin, pin(draft_path), pin(D/'input-check.json'),
                pin(D/'root-static-provenance-finding.json'), fixture_before,
                report['before_manifest'], report['limited_diff'], report['scripts_limited_diff']]
fixed_inputs += report['native_receipts'] + [x['candidate'] for x in report['scripts']]
fixed_inputs += [x['reference'] for x in report['scripts']] + correction['immutable_input_records'] + scripts
for row in fixed_inputs:
    fixed(row, 'exact_frozen_gate_input')
if any(not x['ok'] for x in checks):
    save(D / 'root-final-source-gate-failure.json', {'checks':checks})
    raise SystemExit(1)
prerequisite = next(x for x in observation['inputs'] if x['path'].endswith('/r235_startup_prerequisite.py'))
reservation_id = 'R248-baseline-once-after-R250-20261015'
gates = {}
for command in plan['commands']:
    name = command['id']
    gates[name] = {'state':'APPROVED' if name == 'baseline' else 'HELD',
        'full_source_reviewed':True, 'reservation_id':reservation_id if name == 'baseline' else None,
        'source':next(x for x in scripts if x['path'].endswith('/prepare-evidence.py' if name == 'baseline' else '/run-command.py')),
        'input_records':fixed_inputs, 'argv':command.get('child_argv', command['launcher_argv']),
        'launcher_argv':command['launcher_argv'], 'cwd':command['cwd'], 'finite_env':command['finite_env'],
        'timeout_seconds':command['timeout_seconds'], 'transport':drafts[name],
        'fixture_before_pin':fixture_before, 'context_history':[{'original':x['original'],'archive':x['archive']} for x in history],
        'scripts':scripts, 'prerequisite_source':identity(prerequisite), 'source_index_pin':None}
root_roles = json.loads(controls['root-command-ledger.json'])
root_roles['commands']['baseline'].update(state='RESERVED_BY_ROOT',used=1,remaining=0,reservation_id=reservation_id)
review = {'status':'APPROVED_BASELINE_ONLY_AFTER_R250_STATIC_PROVENANCE_CORRECTION',
    'checks':checks, 'full_source_reviewed':scripts, 'exact_fixture_before':fixture_before,
    'exact_fixture_after':fixture_after, 'correction':correction_pin,
    'historical_unavailable_count':35, 'all_historical_bytes_available':False,
    'current_R242_DB_checked':6, 'execution_released':['baseline'], 'T2_complete':False,'T12_complete':False}
changes = {'source-gate.json':encoded(review),
    'script-gate.json':encoded({'round':'R248','commands':gates}),
    'root-command-ledger.json':encoded(root_roles),
    'root-activation.json':encoded({'status':'BASELINE_RESERVED_ONCE','execution_released':['baseline'],
        'reservation_id':reservation_id,'transport':drafts['baseline']})}
for name, raw in controls.items():
    if (D/name).read_bytes() != raw:
        raise ValueError('immediate complete control CAS differs')
for name, raw in changes.items():
    temporary = D / ('.root-final-source-' + name + '.tmp')
    save(temporary,raw)
    os.replace(temporary,D/name)
save(D/'root-final-source-review-and-baseline-reservation.json',
    {'status':review['status'],'checks':len(checks),'before_index':pin(before_dir/'index.json'),
     'source_gate':pin(D/'source-gate.json'),'script_gate':pin(D/'script-gate.json'),
     'root_ledger':pin(D/'root-command-ledger.json'),'author_role_unchanged':pin(D/'command-ledger.json'),
     'reservation_id':reservation_id,'transport':drafts['baseline'],'new_slots':0})
print(json.dumps({'status':'BASELINE_RESERVED_ONCE','checks':len(checks),'historical_unavailable':35,
                  'current_R242_DB':6,'reservation_id':reservation_id},ensure_ascii=False))
