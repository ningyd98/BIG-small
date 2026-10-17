"""ROOT baseline integrity acceptance and next Ruff reservation; no product execution."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A / 'round248-p6-t2-writer-start-condition-synchronization-20261015'
E = A / 'round245-p6-t2-missing-temporary-evidence-continuation-20261015'
O = D / 'implementation/baseline'
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
    actual = None if raw is None else pin(p, raw)
    check(label, actual == identity(row), expected=identity(row), actual=actual)
    return raw

def encoded(x):
    return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()

def save(p, x):
    raw = x if isinstance(x, bytes) else encoded(x)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as stream:
        stream.write(raw)
    if p.read_bytes() != raw:
        raise ValueError('exclusive metadata copy differs')
    return pin(p, raw)

actual = json.loads((O / 'actual-tool-return.json').read_bytes())
result = json.loads((O / 'result.json').read_bytes())
invocation = json.loads((O / 'invocation.json').read_bytes())
snapshot = json.loads(fixed(result['candidate'], 'baseline_candidate'))
observation = json.loads((D / 'input-observation.json').read_bytes())
overlay_observation = observation
plan = json.loads((D / 'plan.json').read_bytes())
previous = json.loads(Path(plan['inputs']['current_baseline']['path']).read_bytes())
report = json.loads((D / 'implementation/change-report.json').read_bytes())
drafts = json.loads((D / 'root-unreserved-literal-transports.json').read_bytes())
gate = json.loads((D / 'script-gate.json').read_bytes())
check('actual_unique_once_exit0', actual['attempt'] == 1 and actual['retry'] == 0
      and actual['actual_tool_return']['exit_code'] == 0
      and actual['initial'] == actual['actual_tool_return'] == actual['final']
      and actual['polls'] == [] and actual['completion'] is None)
check('actual_literal_exact', actual['invocation'] == drafts['baseline']['invocation'])
check('tool_independent_streams_unknown', actual['independent_stdout'] is None and actual['independent_stderr'] is None)
check('baseline_no_runtime_execution', result['exit_code'] == 0 and result['attempt'] == 1 and result['retry'] == 0
      and result['test_execution'] is False and result['product_commands'] == 0
      and result['runtime_evidence'] is None and result['actual_resources'] is None)
check('invocation_exact', result['invocation'] == invocation
      and invocation['argv'] == gate['commands']['baseline']['launcher_argv']
      and invocation['finite_env'] == drafts['baseline']['finite_env']
      and invocation['outer_capture'] == gate['commands']['baseline']['transport'])
check('qualified_historical_loss', snapshot['all_historical_bytes_available'] is False
      and result['all_historical_bytes_available'] is False
      and snapshot['qualification'] == result['qualification']
      == 'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS')
current = {x['path']: x for x in report['current_sources27']}
historical = {x['path']: x for x in previous['sources']}
check('exact_source_script_protected_counts', len(snapshot['sources']) == 27
      and len(snapshot['scripts']) == 3 and len(snapshot['protected']) == 211)
for row in snapshot['sources']:
    raw = fixed(row, 'fresh_current_source')
    check('full_fresh_base64', raw == base64.b64decode(row['base64'], validate=True))
    physical = fixed(row['physical'], 'fresh_physical_source')
    check('physical_complete_and_path', physical == raw
          and row['physical']['path'] == str(O / 'sources' / Path(row['path']).relative_to(R)))
    check('source_expected_generation_and_mode', identity(row) == identity(current[row['path']])
          and row['historical_original'] == identity(historical[row['path']])
          and Path(row['path']).stat().st_mode == row['mode'])
check('protected_exact_list', snapshot['protected'] == previous['protected'])
for row in snapshot['protected']:
    fixed(row, 'protected')
for row in snapshot['scripts']:
    raw = fixed(row, 'author_or_prerequisite')
    check('script_full_base64', raw == base64.b64decode(row['base64'], validate=True))
for row in result['outputs']:
    fixed(row, 'baseline_artifact')
check('all_baseline_output_paths', {x['path'] for x in result['outputs']} ==
      {x['physical']['path'] for x in snapshot['sources']} |
      {str(O / x) for x in ('fixture-before.py', 'fixture-after.py', 'source-index.json',
                            'historical-unavailable.json', 'invocation.json')})
check('complete_fixture_generations', (O / 'fixture-before.py').read_bytes() ==
      Path(report['fixture_before']['path']).read_bytes()
      and (O / 'fixture-after.py').read_bytes() == Path(report['fixture_after']['path']).read_bytes())
registry = {key(x['original']): x for x in overlay_observation['known_missing']}
check('registry_exact35', len(snapshot['historical_registry']) == 35
      and {key(x['original']) for x in snapshot['historical_registry']} == set(registry)
      and snapshot['historical_registry'] == result['historical_unavailable'])
for row in snapshot['historical_registry']:
    original = row['original']
    p = Path(original['path'])
    check('registered_unavailable_is_not_hash_pass', not p.exists() and not p.is_symlink()
          and row['hash_match'] is None and row['current_bytes'] is None and row['current_sha256'] is None
          and row['authority'] == registry[key(original)]['authority']
          and row['disposition'] == registry[key(original)]['disposition'], original=original)
expected_lists = {
    'inputs344': observation['inputs'], 'baseline_inputs28': previous['input_records'],
    'current_context': [observation['current_final_context']['STATE'], observation['current_final_context']['PHASE']]
        + observation['current_final_context']['controls'],
    'gate_fixed_inputs': gate['commands']['baseline']['input_records'],
    'history_observations812': [x['original'] for x in previous['history_observations']]}
expected_origins = {(name, n): identity(row) for name, rows in expected_lists.items() for n, row in enumerate(rows)}
seen = set()
check('complete_history_count', len(snapshot['history_observations']) == len(expected_origins)
      and snapshot['history_observations'] == result['history_observations'])
for row in snapshot['history_observations']:
    origin = (row['origin']['list'], row['origin']['ordinal'])
    check('unique_history_origin', origin not in seen and row['original'] == expected_origins.get(origin))
    seen.add(origin)
    if key(row['original']) in registry:
        check('history_unavailable_explicit', row['hash_match'] is None
              and row['classification'] == 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245')
    else:
        raw = fixed(row['resolved'], 'available_history')
        check('available_history_byte_equivalence', row['hash_match'] is True
              and len(raw) == row['original']['bytes']
              and hashlib.sha256(raw).hexdigest() == row['original']['sha256'])
for row in snapshot['explicit_maps']:
    raw = fixed(row['archive'], 'full_mapped_generation')
    check('explicit_archive_equivalent', len(raw) == row['original']['bytes']
          and hashlib.sha256(raw).hexdigest() == row['original']['sha256'])
check('sidecar_exact90', len(snapshot['sidecar_states']) == 90 and
      {x['path'] for x in snapshot['sidecar_states']} ==
      {x['path'] for x in observation['old_absent_sidecars']})
for row in snapshot['sidecar_states']:
    p = Path(row['path'])
    check('old_sidecar_still_absent', row['exists'] is False and not p.exists() and not p.is_symlink())
expected_maps = (observation['history_authority']['explicit_maps']
    + [observation['additional_fixture_generation']] + observation['R242_final_settlement_maps']
    + gate['commands']['baseline']['context_history'])
check('exact_only_explicit_generation_maps', snapshot['explicit_maps'] == expected_maps)
check('exact_frozen_command_schema', snapshot['commands'] == plan['commands'])
expected_scripts = gate['commands']['baseline']['scripts'] + [gate['commands']['baseline']['prerequisite_source']]
check('all_three_current_script_identities', [identity(x) for x in snapshot['scripts']] == expected_scripts)
for row in observation['R242_current_persistent_databases']:
    fixed(row['pin'], 'retained_R242_database6_after_baseline')
    for side in row['sidecars']:
        p = Path(side['path'])
        check('retained_R242_database_sidecar18', not p.exists() and not p.is_symlink()
              and side['exists'] is False and side['is_symlink'] is False)
for row in invocation['controls_before']:
    raw = base64.b64decode(row['base64'], validate=True)
    check('complete_control_before', pin(Path(row['path']), raw) == identity(row))
    if row['path'] == str(D / 'command-ledger.json'):
        author = json.loads(raw)
        author['commands']['baseline'].update(state='SPENT', used=1, remaining=0,
                                              reservation_id=invocation['reservation_id'])
        check('author_exact_single_slot_change', Path(row['path']).read_bytes() == encoded(author))
    else:
        fixed(row, 'other_controls_unchanged_during_baseline')
outer_stdout = D / 'implementation/baseline-outer.stdout.txt'
outer_stderr = D / 'implementation/baseline-outer.stderr.txt'
out = outer_stdout.read_bytes()
err = outer_stderr.read_bytes()
summary = json.loads(out)
check('actual_outer_stdout_summary', len(out) <= 6000 and summary['exit_code'] == 0
      and summary['historical_unavailable_count'] == 35 and summary['result_pin'] == pin(O / 'result.json'))
check('actual_outer_stderr_empty', err == b'')
for path in (D / 'implementation/ruff', Path(drafts['ruff']['stdout_path']), Path(drafts['ruff']['stderr_path'])):
    check('ruff_outputs_absent', not path.exists() and not path.is_symlink(), path=str(path))
failures = [x for x in checks if not x['ok']]
if failures:
    save(D / 'root-baseline-failure.json', {'checks': checks, 'failures': failures})
    print(json.dumps({'status': 'STOP', 'failures': failures[:3]}, ensure_ascii=False))
    raise SystemExit(1)
streams = {'stdout': save(O / 'stdout.txt', out), 'stderr': save(O / 'stderr.txt', err)}
save(O / 'outer-stream-copy-provenance.json',
     {'stdout_original': pin(outer_stdout), 'stderr_original': pin(outer_stderr),
      'canonical_exact_copies': streams, 'independent_tool_streams': None})
controls = {name: (D / name).read_bytes() for name in
            ('source-gate.json', 'script-gate.json', 'root-activation.json',
             'root-command-ledger.json', 'command-ledger.json')}
pairs = []
before = D / 'before/root-baseline-acceptance-and-ruff-reservation'
for name, raw in controls.items():
    archive = before / name
    save(archive, raw)
    pairs.append({'original': pin(D / name, raw), 'archive': pin(archive),
                  'base64': base64.b64encode(raw).decode()})
before_pin = save(before / 'index.json', {'records': pairs})
accepted_pin = save(D / 'root-baseline-acceptance.json',
    {'status': 'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
     'checks': checks, 'check_count': len(checks), 'actual': pin(O / 'actual-tool-return.json'),
     'result': pin(O / 'result.json'), 'accepted_source_index': result['candidate'],
     'streams': streams, 'complete_before': before_pin, 'historical_unavailable_count': 35,
     'all_historical_bytes_available': False, 'runtime_evidence': None, 'T2_complete': False,
     'T12_complete': False, 'native': False, 'formal': False})
root = json.loads(controls['root-command-ledger.json'])
root['commands']['baseline']['state'] = 'SPENT_ACCEPTED_BASELINE'
reservation_id = 'R248-ruff-once-20261015'
root['commands']['ruff'].update(state='RESERVED_BY_ROOT', used=1, remaining=0, reservation_id=reservation_id)
gate['commands']['baseline']['state'] = 'SPENT_ACCEPTED_BASELINE'
for name in ('ruff', 'red'):
    gate['commands'][name]['source_index_pin'] = result['candidate']
    gate['commands'][name]['input_records'].append(accepted_pin)
    gate['commands'][name]['context_history'].extend(
        {'original': x['original'], 'archive': x['archive']} for x in pairs)
gate['commands']['ruff'].update(state='APPROVED', reservation_id=reservation_id)
gate['commands']['ruff']['transport']['status'] = 'RESERVED_LITERAL_BY_ROOT'
source_gate = json.loads(controls['source-gate.json'])
source_gate.update(status='BASELINE_ACCEPTED_RUFF_RESERVED', execution_released=['ruff'],
                   baseline_acceptance=accepted_pin)
mutations = {'script-gate.json': encoded(gate), 'root-command-ledger.json': encoded(root),
             'source-gate.json': encoded(source_gate),
             'root-activation.json': encoded({'status': 'RUFF_RESERVED_ONCE', 'execution_released': ['ruff'],
                  'reservation_id': reservation_id, 'baseline_acceptance': accepted_pin,
                  'transport': gate['commands']['ruff']['transport']})}
for name, raw in controls.items():
    if (D / name).read_bytes() != raw:
        raise ValueError('immediate complete control CAS differs')
for name, raw in mutations.items():
    temporary = D / ('.root-baseline-' + name + '.tmp')
    save(temporary, raw)
    os.replace(temporary, D / name)
save(D / 'root-ruff-reservation.json',
     {'reservation_id': reservation_id, 'baseline_acceptance': accepted_pin,
      'complete_before': before_pin, 'transport': gate['commands']['ruff']['transport'],
      'root_ledger': pin(D / 'root-command-ledger.json'), 'script_gate': pin(D / 'script-gate.json')})
print(json.dumps({'status': 'BASELINE_ACCEPTED_RUFF_RESERVED_ONCE', 'checks': len(checks),
                  'source_index': result['candidate'], 'historical_unavailable': 35}, ensure_ascii=False))
