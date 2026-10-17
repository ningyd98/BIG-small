"""ROOT R248 ordinary input/source-preparation gate; no source edits or validation."""
import base64
import hashlib
import json
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
for row in observation['current_sources']:
    raw = fixed(row['original'], 'current_source27')
    check('current_physical_complete_before', fixed(row['physical'], 'current_physical27') == raw)
for row in observation['protected']:
    fixed(row, 'protected211')
for row in source['scripts']:
    check('old_scripts_full_bytes', fixed(row, 'frozen_script') == base64.b64decode(row['base64'], validate=True))
for row in source['sources']:
    raw = fixed(row, 'current_source_full27')
    check('current_source_full_base64', raw == base64.b64decode(row['base64'], validate=True)
          and Path(row['path']).stat().st_mode == row['mode'])
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
delta = plan['scope']['exact_change']
fixture = Path(plan['scope']['modified_existing'][0])
before = fixture.read_bytes()
candidate = before.replace(delta['before'].encode(), delta['after'].encode(), 1)
check('single_planned_two_byte_change', before.count(delta['before'].encode()) == 1
      and len(before) == delta['before_bytes'] and hashlib.sha256(before).hexdigest() == delta['before_sha256']
      and len(candidate) == delta['expected_after_bytes']
      and hashlib.sha256(candidate).hexdigest() == delta['expected_after_sha256']
      and len(before) - len(candidate) == 2)
for command in plan['commands']:
    check('new_slot_HELD_zero_one', command['state'] == 'HELD' and command['used'] == 0
          and command['remaining'] == 1 and command['total'] == 1)
    p = D / 'implementation' / command['id']
    check('fresh_output_directory_absent', not p.exists() and not p.is_symlink(), path=str(p))
for path in plan['scope']['new_author_scripts']:
    p = Path(path)
    check('new_script_absent', not p.exists() and not p.is_symlink(), path=path)
failures = [x for x in checks if not x['ok']]
input_pin = save(D / 'input-check.json',
    {'status': 'FAILED' if failures else 'ACCEPTED_SOURCE_PREPARATION_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
     'checks': checks, 'check_count': len(checks), 'failures': failures,
     'historical_unavailable_count': 35, 'current_R242_DB_checked': 6,
     'execution_released': False, 'plan': plan_pin, 'T2_complete': False, 'T12_complete': False})
if failures:
    print(json.dumps({'status': 'STOP', 'failure_count': len(failures), 'failures': failures[:4]}, ensure_ascii=False))
    raise SystemExit(1)
for name in ('source-gate.json', 'script-gate.json'):
    save(D / name, {'status': 'PENDING_AUTHOR_FULL_SOURCE_REVIEW', 'execution_released': False,
                    'input_check': input_pin})
for name, role in [('root-command-ledger.json', 'ROOT'), ('command-ledger.json', 'AUTHOR')]:
    save(D / name, {'round': 'R248', 'role': role,
                    'commands': {x['id']: {'total': 1, 'used': 0, 'remaining': 1, 'state': 'HELD'}
                                 for x in plan['commands']}})
save(D / 'root-activation.json', {'status': 'SOURCE_PREPARATION_ONLY', 'sole_author': '/root/p6_stage_b_sol',
                                  'input_check': input_pin, 'execution_released': False})
print(json.dumps({'status': 'R248_SOURCE_PREPARATION_ONLY', 'checks': len(checks),
                  'historical_unavailable': 35, 'current_persistent_DB': 6, 'execution_released': False}))
