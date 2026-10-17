"""ROOT Ruff integrity acceptance and sole real RED reservation, stdlib only."""
import base64
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A / 'round248-p6-t2-writer-start-condition-synchronization-20261015'
E = A / 'round245-p6-t2-missing-temporary-evidence-continuation-20261015'
O = D / 'implementation/ruff'
checks = []
def identity(x):
    return {k: x[k] for k in ('path', 'bytes', 'sha256')}
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
        raise ValueError('exclusive metadata readback differs')
    return pin(p, raw)

actual = json.loads((O / 'actual-tool-return.json').read_bytes())
result = json.loads((O / 'result.json').read_bytes())
invocation = json.loads((O / 'invocation.json').read_bytes())
gate = json.loads((D / 'script-gate.json').read_bytes())
drafts = json.loads((D / 'root-unreserved-literal-transports.json').read_bytes())
baseline = json.loads(fixed(result['source_index_pin'], 'accepted_fresh_baseline'))
acceptance = json.loads((D / 'root-baseline-acceptance.json').read_bytes())
check('accepted_baseline_exact', acceptance['accepted_source_index'] == result['source_index_pin'])
initial = actual['initial']
polls = actual['polls']
final = actual['final']
expected_final = polls[-1] if polls else initial
check('actual_once_same_original_session_final', actual['attempt'] == 1 and actual['retry'] == 0
      and expected_final == final == actual['actual_tool_return'] and final['exit_code'] == 0
      and ((polls and initial.get('session_id') is not None and actual['completion'] == final)
           or (not polls and initial.get('session_id') is None and actual['completion'] is None)))
check('actual_literal_exact', actual['invocation'] == drafts['ruff']['invocation'])
check('tool_streams_unknown', actual['independent_stdout'] is None and actual['independent_stderr'] is None)
check('actual_expected_Ruff_outcome', result['child_exit'] == result['wrapper_exit'] == 0
      and result['accepted_command_outcome'] is True and result['timed_out'] is False
      and result['runner_exception'] is None and result['observation_errors'] == []
      and result['cleanup'] == {'leader_reaped': True, 'group_remaining': False, 'cleanup_notes': []})
check('no_behavioral_evidence_from_Ruff', result['JUnit'] is None and result['resource_summary'] is None
      and result['cases'] == [] and result['prerequisite'] is None and result['new_run_index'] is None
      and result['GREEN'] is False and result['product_acceptance'] is False)
check('exact_invocation', invocation == result['invocation']
      and invocation['argv'] == gate['commands']['ruff']['argv']
      and invocation['launcher_argv'] == gate['commands']['ruff']['launcher_argv']
      and invocation['finite_env'] == gate['commands']['ruff']['finite_env']
      and invocation['outer_capture'] == gate['commands']['ruff']['transport'])
check('fresh_source_and_protection_counts', len(baseline['sources']) == 27 and len(baseline['protected']) == 211)
for row in baseline['sources']:
    raw = fixed(row, 'current27')
    check('full_current_base64_and_physical', raw == base64.b64decode(row['base64'], validate=True)
          and fixed(row['physical'], 'physical27') == raw
          and Path(row['path']).stat().st_mode == row['mode'])
for row in baseline['protected']:
    fixed(row, 'protected211')
for row in baseline['scripts']:
    check('scripts_full_base64', fixed(row, 'author_or_prerequisite') == base64.b64decode(row['base64'], validate=True))
for row in baseline['history_observations']:
    if row['hash_match'] is True:
        raw = fixed(row['resolved'], 'available_history')
        check('available_history_equivalence', len(raw) == row['original']['bytes']
              and hashlib.sha256(raw).hexdigest() == row['original']['sha256'])
for row in result['input_records']:
    fixed(row, 'current_gate_fixed_input')
check('input_list_exact', result['input_records'] == gate['commands']['ruff']['input_records'])
check('historical_loss_exact', result['historical_unavailable'] == baseline['historical_registry']
      and len(result['historical_unavailable']) == 35 and result['all_historical_bytes_available'] is False
      and result['qualification'] == baseline['qualification'])
for row in result['historical_unavailable']:
    p = Path(row['original']['path'])
    check('explicit_missing_current_absence', not p.exists() and not p.is_symlink() and row['hash_match'] is None)
for row in baseline['sidecar_states']:
    p = Path(row['path'])
    check('explicit_sidecar_current_absence', row['exists'] is False and not p.exists() and not p.is_symlink())
observation = json.loads((D/'input-observation.json').read_bytes())
for row in observation['R242_current_persistent_databases']:
    fixed(row['pin'], 'retained_R242_database6_after_Ruff')
    for side in row['sidecars']:
        p = Path(side['path'])
        check('retained_R242_database_sidecar18', not p.exists() and not p.is_symlink()
              and side['exists'] is False and side['is_symlink'] is False)
check('source_after_exact', result['source_after'] ==
      {'all_unchanged': True, 'sources': [identity(x) for x in baseline['sources']], 'protected_count': 211}
      and json.loads((O / 'source-after.json').read_bytes()) == result['source_after'])
for row in result['streams'].values():
    fixed(row, 'actual_child_stream')
check('actual_child_Ruff_stdout', (O / 'stdout.txt').read_bytes() == b'All checks passed!\n')
check('actual_child_stderr_empty', (O / 'stderr.txt').read_bytes() == b'')
check('full_file_indexes_retained', json.loads((O / 'file-index.json').read_bytes()) == result['file_index']
      and json.loads((O / 'temp-index.json').read_bytes()) == result['temp_index'] == [])
for row in result['file_index']:
    fixed(row, 'raw_file_index_entry')
for row in invocation['controls_before']:
    raw = base64.b64decode(row['base64'], validate=True)
    check('complete_before_raw', pin(Path(row['path']), raw) == identity(row))
    if row['path'] == str(D / 'command-ledger.json'):
        expected = json.loads(raw)
        expected['commands']['ruff'].update(state='SPENT', used=1, remaining=0,
                                            reservation_id=invocation['reservation_id'])
        check('exact_single_author_role_change', Path(row['path']).read_bytes() == encoded(expected))
    else:
        fixed(row, 'controls_unchanged_during_Ruff')
summary_raw = Path(drafts['ruff']['stdout_path']).read_bytes()
summary = json.loads(summary_raw)
check('actual_outer_summary', len(summary_raw) <= 6000 and summary['child_exit'] == summary['wrapper_exit'] == 0
      and summary['accepted_command_outcome'] is True and summary['result_pin'] == pin(O / 'result.json'))
check('actual_outer_stderr_empty', Path(drafts['ruff']['stderr_path']).read_bytes() == b'')
persistent = D / 'implementation/red/persistent-basetemp'
for p in (D / 'implementation/red', persistent, Path(drafts['red']['stdout_path']), Path(drafts['red']['stderr_path'])):
    check('RED_outputs_absent', not p.exists() and not p.is_symlink(), path=str(p))
check('persistent_exact_workspace_parent', persistent.parent == D / 'implementation/red'
      and not D.is_symlink() and not (D / 'implementation').is_symlink())
failures = [x for x in checks if not x['ok']]
if failures:
    save(D / 'root-ruff-failure.json', {'checks': checks, 'failures': failures})
    print(json.dumps({'status': 'STOP', 'failures': failures[:3]}, ensure_ascii=False))
    raise SystemExit(1)
controls = {name: (D / name).read_bytes() for name in
            ('source-gate.json', 'script-gate.json', 'root-activation.json',
             'root-command-ledger.json', 'command-ledger.json')}
pairs = []
before = D / 'before/root-ruff-acceptance-and-red-reservation'
for name, raw in controls.items():
    archive = before / name
    save(archive, raw)
    pairs.append({'original': pin(D / name, raw), 'archive': pin(archive),
                  'base64': base64.b64encode(raw).decode()})
before_pin = save(before / 'index.json', {'records': pairs})
accepted_pin = save(D / 'root-ruff-acceptance.json',
    {'status': 'ACCEPTED_RUFF_ONLY_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
     'checks': checks, 'check_count': len(checks), 'actual': pin(O / 'actual-tool-return.json'),
     'result': pin(O / 'result.json'), 'source_index': result['source_index_pin'],
     'complete_before': before_pin, 'historical_unavailable_count': 35,
     'all_historical_bytes_available': False, 'T2_complete': False, 'T12_complete': False,
     'native': False, 'formal': False})
root = json.loads(controls['root-command-ledger.json'])
root['commands']['ruff']['state'] = 'SPENT_ACCEPTED_RUFF'
reservation_id = 'R248-red-once-20261015'
root['commands']['red'].update(state='RESERVED_BY_ROOT', used=1, remaining=0, reservation_id=reservation_id)
gate['commands']['ruff']['state'] = 'SPENT_ACCEPTED_RUFF'
red = gate['commands']['red']
red.update(state='APPROVED', reservation_id=reservation_id)
red['input_records'].append(accepted_pin)
red['context_history'].extend({'original': x['original'], 'archive': x['archive']} for x in pairs)
red['transport']['status'] = 'RESERVED_LITERAL_BY_ROOT'
source_gate = json.loads(controls['source-gate.json'])
source_gate.update(status='BASELINE_RUFF_ACCEPTED_RED_RESERVED', execution_released=['red'],
                   Ruff_acceptance=accepted_pin)
mutations = {'script-gate.json': encoded(gate), 'root-command-ledger.json': encoded(root),
             'source-gate.json': encoded(source_gate),
             'root-activation.json': encoded({'status': 'RED_RESERVED_ONCE', 'execution_released': ['red'],
                  'reservation_id': reservation_id, 'Ruff_acceptance': accepted_pin,
                  'transport': red['transport'], 'persistent_basetemp_absent': True})}
for name, raw in controls.items():
    if (D / name).read_bytes() != raw:
        raise ValueError('immediate complete control CAS differs')
for name, raw in mutations.items():
    temporary = D / ('.root-ruff-' + name + '.tmp')
    save(temporary, raw)
    os.replace(temporary, D / name)
save(D / 'root-red-reservation.json',
     {'reservation_id': reservation_id, 'Ruff_acceptance': accepted_pin,
      'complete_before': before_pin, 'transport': red['transport'], 'persistent_basetemp': str(persistent),
      'root_ledger': pin(D / 'root-command-ledger.json'), 'script_gate': pin(D / 'script-gate.json')})
print(json.dumps({'status': 'RUFF_ACCEPTED_RED_RESERVED_ONCE', 'checks': len(checks),
                  'historical_unavailable': 35, 'persistent_basetemp': str(persistent)}, ensure_ascii=False))
