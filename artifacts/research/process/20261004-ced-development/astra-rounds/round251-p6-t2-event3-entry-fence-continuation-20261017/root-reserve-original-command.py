"""ROOT R251 original R223 per-command metadata gate and reservation; stdlib bytes only."""
import base64
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = R/'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A/'round251-p6-t2-event3-entry-fence-continuation-20261017'
KEYS = ['prepare_green', 'ruff', 'green', 'root_settlement']
checks = []

def identity(row):
    return {name: row[name] for name in ('path', 'bytes', 'sha256')}

def key(row):
    return tuple(row[name] for name in ('path', 'bytes', 'sha256'))

def pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def check(label, ok, **facts):
    checks.append(dict(label=label, ok=bool(ok), **facts))

def fixed(row, label='fixed'):
    path = Path(row['path'])
    raw = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    check(label, raw is not None and pin(path, raw) == identity(row), expected=identity(row))
    return raw

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else encoded(value)
    with path.open('xb') as stream:
        if stream.write(raw) != len(raw):
            raise OSError('partial exclusive metadata write')
    if path.read_bytes() != raw:
        raise ValueError('exclusive full metadata write differs')
    return pin(path, raw)

if len(sys.argv) != 2 or sys.argv[1] not in KEYS:
    raise ValueError('one exact original command key required')
selected = sys.argv[1]
ordinal = KEYS.index(selected)
plan_pin = dict(path=str(D/'plan.json'), bytes=37541,
                sha256='5a59a5e3f9e0f80071d083187f69eb9ba791ced7d62a65c64a07e126b2a4cd68')
plan = json.loads(fixed(plan_pin, 'actual_Astra_plan'))
fixed(dict(path=str(D/'plan.md'), bytes=5100,
           sha256='93fdd97dad01b7fb1e5472dfdee0917d216902fab8a24c43647badfcb0fe4042'))
runtime_path = D/'root-runtime-source-contract.json'
runtime_pin = dict(path=str(runtime_path), bytes=27407,
                   sha256='04b20d87fcaf69f766a2373a6d6a43a489744d0577d8237d81bc712f717054d6')
runtime = json.loads(fixed(runtime_pin, 'fixed_runtime_source_contract'))
check('original_frozen_contract', runtime['source_plan'] == plan_pin and runtime['runtime_release'] is False)
check('exact47_fixed_records', len(runtime['input_records']) == 47
      and len({key(row) for row in runtime['input_records']}) == 47)
for row in runtime['input_records']:
    fixed(row, 'new_fixed_metadata_source_input')
after_by_path = {row['path']: row for row in runtime['target_after_pins']}
check('only_exact_three_after_sources', set(after_by_path) == set(plan['scope']['product_paths'])
      and len(after_by_path) == 3)
for row in runtime['scripts']+[runtime['prerequisite_source']]:
    fixed(row, 'reviewed_actual_script')
check('three_new_scripts_plus_import_prerequisite', len(runtime['scripts']) == 3
      and {row['path'] for row in runtime['scripts']} ==
          set(plan['scope']['new_author_scripts']+[plan['scope']['new_ROOT_script']]))
json.loads(fixed(runtime['source_report_pin']))
scope = json.loads(fixed(runtime['fence_inventory_pin']))
corrected_pin = next(row for row in runtime['input_records']
                     if row['path'] == str(A/'round253-p6-t2-checkpoint-prelock-read-candidate-20261017/implementation/prepared-product-values.json'))
corrected = json.loads(fixed(corrected_pin))
check('exact_final72_source_inventory', scope['entries'] == corrected['entries'] and len(scope['entries']) == 72)
observation = json.loads(fixed(plan['inputs']['observation']))
baseline = json.loads(fixed(plan['inputs']['legal_RED_baseline']))
check('actual_schema', len(observation['inputs']) == 379 and len(baseline['sources']) == 27
      and len(baseline['protected']) == 211 and len(baseline['scripts']) == 3
      and len(baseline['history_observations']) == 1223 and len(baseline['explicit_maps']) == 26
      and len(baseline['input_records']) == 32)
check('exact_inherited_schema', observation['prior_exact_maps'] == baseline['explicit_maps']
      and observation['baseline_input_records'] == baseline['input_records'])
role_paths = [Path(plan['budget_continuation'][name]) for name in ('ROOT_ledger', 'author_ledger')]
mutable = [D/'source-gate.json', D/'script-gate.json', D/'root-activation.json', *role_paths]
check('exact_five_mutable_controls', {str(path) for path in mutable} == set(runtime['mutable_controls']))
check('no_live_mutable_fixed_loop', not {str(path) for path in mutable} &
      {row['path'] for row in runtime['input_records']})
role_raw = {path: path.read_bytes() for path in role_paths}
root_role, author_role = [json.loads(role_raw[path]) for path in role_paths]
old_gate = json.loads((D/'script-gate.json').read_bytes())
links = json.loads((D/'ledger-links.json').read_bytes())
check('same_original_ledger_links', links['ROOT_ledger'] == str(role_paths[0])
      and links['author_ledger'] == str(role_paths[1]) and links['new_slots'] == 0)
context = observation['current_context']
allowed_context = {str(path) for path in mutable} | {context[name]['path'] for name in ('STATE', 'PHASE')}
old_entries = old_gate.get('commands', {})
extra_pairs = list(links['context_history'])
for value in old_entries.values():
    extra_pairs.extend(value.get('context_history', []))
check('only_exact_mutable_context_generations',
      all(pair['original']['path'] in allowed_context for pair in extra_pairs))
pairs = (observation['prior_exact_maps']+observation['event3_before']
         +observation['R248_final_before_maps']+observation['R223_role_before']+extra_pairs)
check('exact_declared_mapping_sets', len(observation['prior_exact_maps']) == 26
      and len(observation['event3_before']) == 3 and len(observation['R248_final_before_maps']) == 7
      and len(observation['R223_role_before']) == 2)
maps = {}
for pair in pairs:
    raw = fixed(pair['archive'], 'physical_generation_archive')
    check('physical_full_original_equivalence', raw is not None
          and pin(Path(pair['original']['path']), raw) == identity(pair['original']))
    if 'base64' in pair:
        check('full_base64_equivalence', raw == base64.b64decode(pair['base64'], validate=True))
    maps[key(pair['original'])] = pair['archive']
registry = {key(row['original']): row for row in observation['known_missing']}
check('exact35_unique_unavailable', len(registry) == len(observation['known_missing']) == 35)
for row in observation['known_missing']:
    path = Path(row['original']['path'])
    check('exact_missing_still_absent', not path.exists() and not path.is_symlink()
          and row['current_bytes'] is None and row['current_sha256'] is None and row['hash_match'] is None
          and row['disposition'] == 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245', original=row['original'])
    authority = row['authority']
    container = json.loads(fixed(authority['pin'], 'exact_missing_authority'))
    number = authority['ordinal']
    check('authority_nonnegative_integer', type(number) is int and number >= 0)
    if authority['selector'] == 'input_records':
        authoritative = container['input_records'][number]
    elif authority['selector'] == 'new_retained_databases.pin':
        authoritative = container['new_retained_databases'][number]['pin']
    else:
        raise ValueError('unknown exact missing authority selector')
    check('exact_registry_identity', identity(authoritative) == identity(row['original']))
for rows, label in ((observation['inputs'], 'available_direct379'),
                    (baseline['input_records'], 'available_baseline32'),
                    ([context['STATE'], context['PHASE']]+context['R248_final_controls'], 'current_final_context')):
    for row in rows:
        if key(row) in registry:
            check('explicit_unavailable_not_hash_pass', True, original=row, hash_match=None)
        else:
            raw = fixed(maps.get(key(row), row), label)
            check('direct_original_equivalence', raw is not None
                  and pin(Path(row['path']), raw) == identity(row))
            if raw is not None and row['path'].endswith('/invocation.json'):
                invocation = json.loads(raw)
                for control in invocation.get('controls_before', []):
                    decoded = base64.b64decode(control['base64'], validate=True)
                    check('invocation_own_recorded_generation', pin(Path(control['path']), decoded) == identity(control))
for row in baseline['history_observations']:
    original = row['original']
    if key(original) in registry:
        check('historical_unavailable_not_pass', row['hash_match'] is None)
    else:
        resolved = row['resolved']
        raw = fixed(maps.get(key(original), maps.get(key(resolved), resolved)), 'available_history1223')
        check('historical_full_equivalence', raw is not None
              and pin(Path(original['path']), raw) == identity(original))
for row in observation['current_sources']:
    original_raw = fixed(row['physical'], 'accepted_original_physical27')
    check('original_source_identity', original_raw is not None
          and pin(Path(row['original']['path']), original_raw) == identity(row['original']))
    fixed(after_by_path.get(row['original']['path'], row['original']), 'actual_current27')
for row in baseline['sources']:
    raw = base64.b64decode(row['base64'], validate=True)
    check('full_original_source_base64', pin(Path(row['path']), raw) == identity(row) and raw == fixed(row['physical']))
    current = fixed(after_by_path.get(row['path'], row), 'current_full27')
    check('source_mode_retained', Path(row['path']).stat().st_mode == row['mode'])
    if row['path'] not in after_by_path:
        check('unowned24_entire_bytes_retained', current == raw)
for row in observation['protected']:
    fixed(row, 'protected211')
for row in baseline['scripts']:
    check('prior_scripts_full_base64', fixed(row) == base64.b64decode(row['base64'], validate=True))
for row in observation['old_absent_sidecars']:
    path = Path(row['path'])
    check('old90_sidecar_absent', row['exists'] is False and not path.exists() and not path.is_symlink())
for row in observation['retained_workspace_databases']:
    fixed(row['pin'], 'strict_current_workspace_DB12')
    check('available_DB_not_old_missing', key(row['pin']) not in registry)
    for side in row['sidecars']:
        path = Path(side['path'])
        check('current_workspace_sidecar36', side['exists'] is False and side['is_symlink'] is False
              and not path.exists() and not path.is_symlink())
check('exact12_and36_current_DB_states', len(observation['retained_workspace_databases']) == 12
      and sum(len(row['sidecars']) for row in observation['retained_workspace_databases']) == 36)
acceptance = json.loads(fixed(plan['inputs']['legal_RED_acceptance']))
receipt = json.loads(fixed(plan['inputs']['legal_RED_receipt']))
check('independent_legal_RED_predecessor', acceptance['legal_RED'] is True and receipt['legal_RED'] is True
      and acceptance['status'] == 'ACCEPTED_LEGAL_ORIGINAL_RACE_RED')
writers, names = observation['writer_inventory'], observation['writer_names']
check('72_unique_entries_36_each', len(writers) == 72 and len(names) == len(set(names)) == 36
      and len({(row['path'], row['method']) for row in writers}) == 72
      and all({row['method'] for row in writers
               if row['path'] == str(R/'src/cloud_edge_robot_arm/repositories/event_autonomy'/filename)}
              == set(names) for filename in ('memory.py', 'sqlite.py')))
for row in writers:
    original = next(value for value in baseline['sources'] if value['path'] == row['path'])
    lines = base64.b64decode(original['base64'], validate=True).decode().splitlines()
    check('literal_original_method_range', 0 < row['start_line'] <= row['end_line'] <= len(lines)
          and lines[row['start_line']-1].strip().startswith('def '+row['method']+'('))
    for item in row['current_controls']:
        check('actual_original_control_text', lines[item['line']-1].strip() == item['text'])
check('scope_targets_not_protected',
      not set(plan['scope']['product_paths']) & {row['path'] for row in observation['protected']})
commands = {row['id']: row for row in plan['commands']}
check('same_original_four_keys', list(commands) == KEYS)
roles = dict(zip(role_paths, (root_role, author_role)))
for original in observation['R223_role_values']:
    live = roles[Path(original['pin']['path'])]
    check('historical_top_fields_unchanged', {k:v for k,v in live.items() if k != 'commands'} ==
          {k:v for k,v in original['value'].items() if k != 'commands'})
    for name in ('prepare_red', 'red'):
        check('original_failed_chain_spent_immutable', live['commands'][name] == original['value']['commands'][name])
for name in KEYS:
    normative = commands[name]
    contract = {k:v for k,v in normative.items() if k not in ('authorized', 'used', 'remaining', 'state')}
    for role in (root_role, author_role):
        entry = role['commands'][name]
        check('same_original_continuation_contract', entry['authorized'] == 1
              and entry['continuation'] == dict(round='R251', plan=plan_pin,
                  execution_contract=contract, not_a_new_budget=True))
        if KEYS.index(name) < ordinal:
            check('prior_same_identity_spent', entry['used'] == 1 and entry['remaining'] == 0)
        else:
            check('unspent_same_identity_held', entry['used'] == 0 and entry['remaining'] == 1
                  and entry['state'].startswith('HELD'))
check('author_root_slot_stays_nonexecutable', author_role['commands']['root_settlement']['owner'] == 'ROOT'
      and author_role['commands']['root_settlement']['author_executable'] is False)
accepted = {}
source_index = None
for name in KEYS[:ordinal]:
    path = D/('root-'+name+'-acceptance.json')
    value = json.loads(path.read_bytes())
    check('independent_prior_ROOT_acceptance', value['round'] == 'R251' and value['command'] == name
          and value['status'] == 'ACCEPTED'
          and value['result'] == pin(D/'implementation'/name/'result.json')
          and value['actual_tool_return'] == pin(D/'implementation'/name/'actual-tool-return.json'))
    actual = json.loads(fixed(value['actual_tool_return']))
    check('actual_prior_exit0', actual['final']['exit_code'] == 0 and actual['attempt'] == 1 and actual['retry'] == 0)
    fixed(value['result'])
    fixed(value['source_index'])
    if source_index is None:
        source_index = value['source_index']
    check('one_accepted_source_index_generation', source_index == value['source_index'])
    accepted[name] = pin(path)
if ordinal:
    snapshot = json.loads(fixed(source_index))
    check('accepted_new_full_source_counts', len(snapshot['sources']) == 27 and len(snapshot['protected']) == 211
          and len(snapshot['scripts']) == 4)
    for row in snapshot['sources']:
        raw = fixed(row)
        check('accepted_current_source_entire_bytes', raw == base64.b64decode(row['base64'], validate=True)
              and raw == fixed(row['physical']) and Path(row['path']).stat().st_mode == row['mode'])
    for row in snapshot['scripts']:
        check('accepted_script_entire_bytes', fixed(row) == base64.b64decode(row['base64'], validate=True))
    for row in snapshot['protected']:
        fixed(row, 'accepted_current_protected211')
    check('same_after_targets_inventory_report', snapshot['target_after_pins'] == runtime['target_after_pins']
          and snapshot['fence_inventory_pin'] == runtime['fence_inventory_pin']
          and snapshot['source_report_pin'] == runtime['source_report_pin'])
command = commands[selected]
transport = runtime['transports'][selected]
expected_cap = 630 if selected == 'green' else 150
args = [k+'='+v for k,v in command['finite_env'].items()]+command['launcher_argv']
stdout, stderr = [D/'implementation'/(selected+'.tool.'+kind+'.raw') for kind in ('stdout', 'stderr')]
expected_cmd = ('set -C\nexec /usr/bin/timeout --signal=TERM --kill-after=5s '+str(expected_cap)
    +'s /usr/bin/env -i '+shlex.join(args)+' > '+shlex.quote(str(stdout))+' 2> '+shlex.quote(str(stderr)))
check('literal_finite_transport', transport['invocation'] == dict(cmd=expected_cmd, workdir=str(R),
      max_output_tokens=1800, yield_time_ms=1000) and transport['outer_timeout_seconds'] == expected_cap
      and transport['kill_after_seconds'] == 5 and transport['stdout'] == str(stdout) and transport['stderr'] == str(stderr))
for path in (stdout, stderr, Path(command['evidence_directory'])):
    check('selected_original_outputs_absent', not path.exists() and not path.is_symlink(), path=str(path))
failures = [row for row in checks if not row['ok']]
if failures:
    save(D/('root-'+selected+'-reservation-failure.json'),
         dict(checks=checks, failures=failures, runtime_release=False))
    raise ValueError('ROOT source/input/original budget gate failed')
raw_before = {path: path.read_bytes() for path in mutable}
for path in role_paths:
    if raw_before[path] != role_raw[path]:
        raise ValueError('role changed during complete metadata input gate')
before = []
before_dir = D/'before'/('root-reserve-'+selected)
for number, path in enumerate(mutable):
    raw = raw_before[path]
    archive = before_dir/(str(number)+'-'+path.name)
    save(archive, raw)
    before.append(dict(original=pin(path, raw), archive=pin(archive),
                       base64=base64.b64encode(raw).decode(), mode=path.stat().st_mode))
before_index = save(before_dir/'index.json', dict(round='R251', command=selected, records=before))
entries = old_entries
history = list(extra_pairs)+before
history = list({key(row['original']): row for row in history}.values())
inputs = list(runtime['input_records'])+[runtime_pin]+list(accepted.values())
inputs = list({key(row): identity(row) for row in inputs}.values())
for name in KEYS:
    if name not in entries:
        current = commands[name]
        script = current['launcher_argv'][1]
        entries[name] = dict(state='HELD_PENDING_PREVIOUS_ROOT_ACCEPTANCE', full_source_reviewed=True,
            source=next(row for row in runtime['scripts'] if row['path'] == script),
            launcher_argv=current['launcher_argv'], argv=current.get('child_argv', current['launcher_argv']),
            cwd=current['cwd'], finite_env=current['finite_env'], timeout_seconds=current['timeout_seconds'],
            transport=runtime['transports'][name], scripts=runtime['scripts'],
            prerequisite_source=runtime['prerequisite_source'], target_after_pins=runtime['target_after_pins'],
            fence_inventory_pin=runtime['fence_inventory_pin'], source_report_pin=runtime['source_report_pin'],
            input_records=inputs, context_history=history)
for name in KEYS[:ordinal]:
    root_role['commands'][name].update(state='SPENT_ACCEPTED_BY_ROOT', ROOT_acceptance=accepted[name])
    entries[name]['state'] = 'SPENT_ACCEPTED_BY_ROOT'
reservation_id = 'R251:R223.'+selected+':original-once'
entry = entries[selected]
entry.update(state='APPROVED', full_source_reviewed=True, reservation_id=reservation_id,
             input_records=inputs, context_history=history)
if source_index is not None:
    entry['source_index_pin'] = source_index
if selected == 'root_settlement':
    entry['acceptances'] = accepted
new_gates = dict(round='R251', status='ONE_ORIGINAL_SLOT_RESERVED', selected=selected,
                 commands=entries, new_slots=0, source_contract=runtime_pin)
gate_raw = encoded(new_gates)
root_role['commands'][selected].update(state='RESERVED_BY_ROOT', used=1, remaining=0,
    reservation_id=reservation_id, gate_pin=pin(D/'script-gate.json', gate_raw))
source_gate = dict(round='R251', status='FULL_SOURCE_AND_INPUTS_APPROVED', selected=selected,
    execution_released=True, only_original_slot=True, new_slots=0, source_contract=runtime_pin,
    check_count=len(checks), before=before_index, T2_complete=False)
activation = dict(round='R251', status='ONE_ORIGINAL_SLOT_RESERVED', selected=selected,
    execution_released=True, actor=command['actor'], reservation_id=reservation_id, new_slots=0)
mutations = {D/'script-gate.json': gate_raw, D/'source-gate.json': encoded(source_gate),
             D/'root-activation.json': encoded(activation), role_paths[0]: encoded(root_role)}
for path, raw in raw_before.items():
    if path.read_bytes() != raw:
        raise ValueError('immediate full five-control CAS differs')
for path, raw in mutations.items():
    temp = D/('.ROOT-reserve-'+selected+'-'+path.name+'.tmp')
    save(temp, raw)
    if path.read_bytes() != raw_before[path]:
        raise ValueError('immediate per-control CAS differs')
    os.replace(temp, path)
for path, raw in raw_before.items():
    if path.read_bytes() != mutations.get(path, raw):
        raise ValueError('exact final five-control transition differs')
receipt = dict(round='R251', command=selected, status='RESERVED_ONE_ORIGINAL_SLOT',
    checks=checks, check_count=len(checks), original_budget_owner=command['budget_owner'],
    reservation_id=reservation_id, source_contract=runtime_pin, before=before_index,
    script_gate=pin(D/'script-gate.json'), ROOT_ledger=pin(role_paths[0]), author_ledger=pin(role_paths[1]),
    transport=transport, source_index_pin=source_index, prior_acceptances=accepted,
    author_consumption_pending=selected != 'root_settlement', new_slots=0, T2_complete=False)
receipt_pin = save(D/('root-'+selected+'-reservation.json'), receipt)
print(json.dumps(dict(status=receipt['status'], command=selected, checks=len(checks),
      receipt=receipt_pin, source_contract=runtime_pin), ensure_ascii=False))
