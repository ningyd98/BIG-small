"""ROOT ordinary joint R242/R245 applicability gate; no product imports or children."""
import base64
import hashlib
import json
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
B = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = B / 'round242-p6-t2-writer-barrier-condition-synchronization-20261015'
E = B / 'round245-p6-t2-missing-temporary-evidence-continuation-20261015'
checks = []

def ident(row):
    return {k: row[k] for k in ('path', 'bytes', 'sha256')}

def key(row):
    return tuple(row[k] for k in ('path', 'bytes', 'sha256'))

def record(label, ok, **details):
    checks.append({'label': label, 'ok': bool(ok), **details})

def verify(row, label):
    p = Path(row['path'])
    data = p.read_bytes() if p.is_file() and not p.is_symlink() else None
    actual = None if data is None else {
        'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    record(label, actual == ident(row), expected=ident(row), actual=actual)
    return data

def write(path, obj):
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

p = json.loads((D / 'plan.json').read_bytes())
q = json.loads((E / 'plan.json').read_bytes())
o = json.loads((D / 'input-observation.json').read_bytes())
u = json.loads((E / 'input-observation.json').read_bytes())
for row in [
    {'path': str(D / 'plan.md'), 'bytes': 5423, 'sha256': '8c7cd61d6aeee8d1368040a22b10e8cbce3643d8de5f55506161b758feea8eab'},
    {'path': str(D / 'plan.json'), 'bytes': 22524, 'sha256': 'f6d8aef8b1e7ee62aadaa55c95b8a465878d7eda46fe6e48f27f4d7a0c945137'},
    {'path': str(E / 'plan.md'), 'bytes': 3460, 'sha256': '46fc2837e7f4e30396a0a74cb2107ee0cfbe6fac9c5fd79c6cf0adebd072c380'},
    {'path': str(E / 'plan.json'), 'bytes': 13123, 'sha256': '5b41bb456d0323d4ba205b7c2bb61dc5ac0992594e93ee9491a4795400037601'},
] + [p['inputs']['observation']] + q['inputs'] + o['inputs'] + u['inputs']:
    verify(row, 'fixed_authority')
s = json.loads(Path(o['protected_authority']['index']['path']).read_bytes())
f = json.loads(Path(p['inputs']['root_final_findings']['path']).read_bytes())
missing = {key(row['original']): row for row in u['known_missing']}
record('exact_missing_registry35', len(missing) == 35)
for row in u['known_missing']:
    x = row['original']
    path = Path(x['path'])
    record('explicit_unavailable', not path.exists() and not path.is_symlink(),
           original=ident(x), current_exists=path.exists(), current_symlink=path.is_symlink(),
           current_bytes=None, current_sha256=None, disposition=row['disposition'])
    a = row['authority']
    verify(a['pin'], 'missing_authority_container')
    container = json.loads(Path(a['pin']['path']).read_bytes())
    if a['selector'] == 'new_retained_databases.pin':
        authoritative = container['new_retained_databases'][a['ordinal']]['pin']
    else:
        entry = container[a['selector']][a['ordinal']]
        authoritative = entry['pin'] if 'pin' in entry else entry
    record('missing_exact_authority_selector', ident(authoritative) == ident(x))
maps = {}
for entry in s['resolved_history']['entries']:
    maps[key(entry['original'])] = entry['resolution']['pin']
for pair in [o['frozen_fixture_archive']] + o['explicit_R239_settlement_history']:
    archive = pair['archive']
    raw = verify(archive, 'full_physical_archive')
    record('archive_exact_original_bytes', raw is not None and len(raw) == pair['original']['bytes']
           and hashlib.sha256(raw).hexdigest() == pair['original']['sha256'])
    maps[key(pair['original'])] = archive
    if 'current_as_of' in pair:
        verify(pair['current_as_of'], 'final_generation_current')

def historical(row, label):
    if key(row) in missing:
        record(label, True, original=ident(row), classification='HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245',
               hash_match=None, registry_exact=True)
        return
    target = maps.get(key(row), row)
    data = verify(target, label)
    record(label + '_byte_equivalence', data is not None and len(data) == row['bytes']
           and hashlib.sha256(data).hexdigest() == row['sha256'])

for row in s['history']:
    historical(row, 'fixed_history')
for row in s['input_records']:
    historical(row, 'fixed_input_record')
for row in s['resolved_history']['documents']:
    verify(row, 'resolved_history_document')
for row in o['current_sources']:
    verify(row, 'current_source')
for row in s['sources']:
    raw = verify(row, 'current_source_full')
    record('source_base64_exact', raw == base64.b64decode(row['base64'], validate=True))
    physical = verify(row['physical'], 'fresh_physical_source')
    record('fresh_physical_full_bytes', physical == raw)
for row in o['protected_authority']['records']:
    verify(row, 'protected_source')
for row in s['scripts']:
    raw = verify(row, 'old_script')
    record('old_script_base64_exact', raw == base64.b64decode(row['base64'], validate=True))
for row in o['immutable_raw']:
    verify(row, 'immutable_raw')
record('declared_counts', len(o['current_sources']) == 27 and len(o['protected_authority']['records']) == 211)
dbs = s['retained_databases'] + f['new_retained_databases']
sidecars = s['absent_sidecars'] + [x for row in f['new_retained_databases'] for x in row['sidecars']]
record('new_records_exact', o['database_authorities']['new_records'] == f['new_retained_databases'])
record('old_databases30_explicitly_missing', len(dbs) == 30 and len({x['pin']['path'] for x in dbs}) == 30
       and all(key(x['pin']) in missing for x in dbs))
prior_nested = {x['path']: x['exists'] for row in s['retained_databases'] for x in row['sidecars']}
record('prior_sidecar_consistency', prior_nested == {x['path']: x['exists'] for x in s['absent_sidecars']})
record('sidecar_count90', len(sidecars) == 90 and len({x['path'] for x in sidecars}) == 90)
for row in sidecars:
    path = Path(row['path'])
    record('sidecar_absent', row['exists'] is False and not path.exists() and not path.is_symlink(), path=str(path))
for row in o['context_only'].values():
    verify(row, 'current_context')
commands = json.loads(json.dumps(p['commands']))
override = q['execution_override']['replace_exact_child_argument']
for row in commands:
    if row['id'] == 'red':
        record('single_exact_basetemp_override', row['child_argv'].count(override['old']) == 1)
        row['child_argv'] = [override['new'] if x == override['old'] else x for x in row['child_argv']]
for name in ('baseline', 'ruff', 'red'):
    path = D / 'implementation' / name
    record('new_output_absent', not path.exists() and not path.is_symlink(), path=str(path))
persistent = Path(override['new'].split('=', 1)[1])
record('persistent_basetemp_absent_under_workspace', not persistent.exists() and not persistent.is_symlink()
       and persistent == D / 'implementation/red/persistent-basetemp')
record('R239_diagnostic_not_legal_RED', f['legal_RED'] is False)
failures = [x for x in checks if not x['ok']]
report = {'rounds': ['R242', 'R245'], 'status': 'FAILED' if failures else
          'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
          'checks': checks, 'failures': failures, 'check_count': len(checks),
          'missing_registry': u['known_missing'], 'historical_missing_count': 35,
          'all_historical_bytes_available': False, 'commands': commands,
          'source_preparation_only': not failures, 'execution_released': False,
          'T2_complete': False, 'T12_complete': False, 'native': False, 'formal': False}
input_pin = write(D / 'input-check.json', report)
write(E / 'input-check.json', {'joint_input_check': input_pin, 'status': report['status']})
if failures:
    print(json.dumps({'status': 'STOP', 'failure_count': len(failures), 'failures': failures[:5]}, ensure_ascii=False))
    raise SystemExit(1)
write(E / 'disposition.json', {'status': report['status'], 'missing_registry': u['known_missing'],
                             'old_bytes_recovered': False, 'cause': 'UNKNOWN', 'new_slots': 0})
write(E / 'root-activation.json', {'status': 'ACCEPTED_METADATA_OVERLAY_ONLY', 'joint_input_check': input_pin,
                                 'execution_released': False, 'new_slots': 0})
write(E / 'step-report.json', {'round': 'R245', 'status': report['status'], 'old_bytes_recovered': False,
                             'missing_databases': 30, 'missing_raw': 5, 'new_slots': 0,
                             'joint_input_check': input_pin, 'T2_complete': False, 'T12_complete': False,
                             'native': False, 'formal': False})
for name in ('source-gate.json', 'script-gate.json'):
    write(D / name, {'status': 'PENDING_AUTHOR_FULL_SOURCE_REVIEW', 'execution_released': False,
                     'joint_input_check': input_pin})
for name in ('command-ledger.json', 'root-command-ledger.json'):
    write(D / name, {'round': 'R242', 'role': 'ROOT' if name.startswith('root-') else 'AUTHOR',
                     'commands': {row['id']: {'total': 1, 'used': 0, 'remaining': 1, 'state': 'HELD'}
                                  for row in commands}})
write(D / 'root-activation.json', {'status': 'SOURCE_PREPARATION_ONLY', 'execution_released': False,
                                 'sole_author': '/root/p6_stage_b_sol', 'joint_input_check': input_pin,
                                 'commands': commands})
print(json.dumps({'status': report['status'], 'checks': len(checks), 'historical_unavailable': 35,
                  'source_preparation_only': True, 'execution_released': False}, ensure_ascii=False))
