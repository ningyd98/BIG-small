"""Independent ROOT acceptance of one actual R251 result; metadata bytes only."""
import base64
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = R/'artifacts/research/process/20261004-ced-development/astra-rounds/round251-p6-t2-event3-entry-fence-continuation-20261017'
checks = []
def pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
def identity(row):
    return {k:row[k] for k in ('path','bytes','sha256')}
def key(row):
    return tuple(row[k] for k in ('path','bytes','sha256'))
def check(label, ok):
    checks.append(dict(label=label,ok=bool(ok)))
def fixed(row):
    path = Path(row['path'])
    raw = path.read_bytes()
    check('exact_file_bytes',not path.is_symlink() and pin(path,raw)==identity(row))
    return raw
def read(path):
    return json.loads(path.read_bytes())
if len(sys.argv)!=2 or sys.argv[1] not in ('prepare_green','ruff','green'):
    raise ValueError('one original actual author command required')
name = sys.argv[1]
out = D/'implementation'/name
runtime = read(D/'root-runtime-source-contract.json')
plan = json.loads(fixed(runtime['source_plan']))
command = next(row for row in plan['commands'] if row['id']==name)
transport = runtime['transports'][name]
actual = read(out/'actual-tool-return.json')
initial,polls,final = actual['initial'],actual['polls'],actual['final']
check('one_actual_exact_finite_invocation',actual['invocation']==transport['invocation']
      and actual['attempt']==1 and actual['retry']==0
      and final==actual['actual_tool_return']==(polls[-1] if polls else initial)
      and final['exit_code']==0 and actual['independent_stdout'] is None
      and actual['independent_stderr'] is None)
check('same_original_session_only',
      len(actual['poll_invocations'])==len(polls)
      and (not polls or (initial.get('session_id') is not None
           and all(row.get('session_id')==initial['session_id'] for row in polls[:-1])
           and all(row['session_id']==initial['session_id'] and row['chars']==''
                   and 0<row['yield_time_ms']<=60000 for row in actual['poll_invocations']))))
streams = {}
for kind in ('stdout','stderr'):
    path = Path(transport[kind])
    streams[kind] = pin(path)
    check('actual_exclusive_stream_file',path.is_file() and not path.is_symlink())
check('outer_stderr_empty_on_success',streams['stderr']['bytes']==0)
outer_summary = json.loads(Path(transport['stdout']).read_bytes())
check('outer_summary_same_command',outer_summary['command']==name)
result = read(out/'result.json')
check('result_original_once',result['round']=='R251' and result['command']==name
      and result['attempt']==1 and result['retry']==0)
gate_raw = (D/'script-gate.json').read_bytes()
gate = json.loads(gate_raw)['commands'][name]
root = read(Path(plan['budget_continuation']['ROOT_ledger']))['commands'][name]
author = read(Path(plan['budget_continuation']['author_ledger']))['commands'][name]
check('same_reserved_and_consumed_identity',gate['state']=='APPROVED'
      and root['state']=='RESERVED_BY_ROOT' and root['used']==1 and root['remaining']==0
      and root['gate_pin']==pin(D/'script-gate.json',gate_raw)
      and author['state']=='SPENT' and author['used']==1 and author['remaining']==0
      and root['reservation_id']==author['reservation_id']==gate['reservation_id'])
for row in runtime['input_records']+runtime['target_after_pins']+runtime['scripts']+[runtime['prerequisite_source']]:
    fixed(row)
for row in gate['input_records']:
    fixed(row)
if name=='prepare_green':
    check('prepared_without_product_execution',result['exit_code']==0 and result['test_execution'] is False
          and result['product_commands']==0 and result['runtime_evidence'] is None and result['actual_resources'] is None)
    source_pin = result['candidate']
    for row in result['outputs']:
        fixed(row)
    check('full_saved_prepare_invocation',result['invocation']==read(out/'invocation.json'))
else:
    check('actual_child_and_wrapper_success',result['child_exit']==result['wrapper_exit']==0
          and result['accepted_command_outcome'] is True and result['observation_errors']==[]
          and result['timed_out'] is False and result['runner_exception'] is None
          and result['cleanup']==dict(leader_reaped=True,group_remaining=False,cleanup_notes=[]))
    source_pin = result['source_index_pin']
    for row in result['streams'].values():
        fixed(row)
snapshot = json.loads(fixed(source_pin))
baseline = json.loads(fixed(plan['inputs']['legal_RED_baseline']))
observation = json.loads(fixed(plan['inputs']['observation']))
check('exact_new_source_counts',len(snapshot['sources'])==27 and len(snapshot['protected'])==211
      and len(snapshot['scripts'])==4)
check('exact_source_path_set',{row['path'] for row in snapshot['sources']}==
      {row['path'] for row in baseline['sources']})
originals = {row['path']:row for row in baseline['sources']}
after = {row['path']:row for row in runtime['target_after_pins']}
for row in snapshot['sources']:
    raw = fixed(row)
    check('full_current_physical_base64_mode',raw==base64.b64decode(row['base64'],validate=True)
          and raw==fixed(row['physical']) and Path(row['path']).stat().st_mode==row['mode'])
    check('only_three_source_changes',identity(row)==identity(after.get(row['path'],originals[row['path']])))
    check('historical_original_retained',row['historical_original']==identity(originals[row['path']]))
check('exact_protected_sources',snapshot['protected']==baseline['protected'])
for row in snapshot['protected']:
    fixed(row)
check('exact_reviewed_script_set',{row['path'] for row in snapshot['scripts']}==
      {row['path'] for row in runtime['scripts']+[runtime['prerequisite_source']]})
for row in snapshot['scripts']:
    check('full_script_base64',fixed(row)==base64.b64decode(row['base64'],validate=True))
check('same_source_report_inventory',snapshot['target_after_pins']==runtime['target_after_pins']
      and snapshot['source_report_pin']==runtime['source_report_pin']
      and snapshot['fence_inventory_pin']==runtime['fence_inventory_pin'])
registry = {key(row['original']):row for row in observation['known_missing']}
check('declared35_missing_not_recovered',len(registry)==len(snapshot['historical_registry'])==35
      and {key(row['original']) for row in snapshot['historical_registry']}==set(registry)
      and snapshot['all_historical_bytes_available'] is False)
for row in snapshot['historical_registry']:
    path = Path(row['original']['path'])
    check('missing_still_null_and_absent',not path.exists() and not path.is_symlink()
          and row['current_bytes'] is None and row['current_sha256'] is None and row['hash_match'] is None)
for row in snapshot['explicit_maps']:
    raw = fixed(row['archive'])
    check('exact_history_generation',pin(Path(row['original']['path']),raw)==identity(row['original']))
    if 'base64' in row:
        check('history_full_base64',raw==base64.b64decode(row['base64'],validate=True))
for row in snapshot['history_observations']:
    if key(row['original']) in registry:
        check('missing_history_is_not_a_pass',row['hash_match'] is None)
    else:
        raw = fixed(row['resolved'])
        check('all_available_history_full_bytes',row['hash_match'] is True
              and pin(Path(row['original']['path']),raw)==identity(row['original']))
if name=='green':
    expected = command['nodeids']
    xml = ET.fromstring((out/'junit.xml').read_bytes())
    nodes = xml.findall('.//testcase')
    ids = [row.get('classname','').replace('.','/')+'.py::'+row.get('name','') for row in nodes]
    check('nine_exact_PASS',ids==expected and len(nodes)==9
          and all(all(row.find(tag) is None for tag in ('failure','error','skipped')) for row in nodes)
          and result['JUnit']['nodeids']==expected
          and tuple(result['JUnit'][k] for k in ('tests','passes','failures','errors','skips'))==(9,9,0,0,0))
    cases = {}
    for row in result['cases']:
        value = json.loads(fixed(row['pin']))
        check('full_raw_case',value==row['data'])
        node = next(x for x in expected if hashlib.sha256(x.encode()).hexdigest()+'.json'==Path(row['pin']['path']).name)
        check('unique_case',node not in cases)
        cases[node] = value
    check('exact9_case_nodes',set(cases)==set(expected))
    summary = result['resource_summary']
    check('actual_resource_closure',summary['all_records_valid'] is True and summary['validation_errors']==[])
    seen = []
    for row in summary['records']:
        value = json.loads(fixed(row['pin']))
        seen.append(value['nodeid'])
        check('complete_actual_resource_record',value==row['data'] and row['error'] is None
              and value['cleanup_errors']==[] and value['allocation_attempts']==len(value['resources'])
              and value['pid']==result['child_pid'])
        obs = value['observations']
        check('hooks_and_behavior_closed',obs['assertions_completed'] is True
              and obs['observers_restored'] is True and obs['method_restoration'] is True
              and obs['exit_exception'] is None and obs['scenarios']==[cases[value['nodeid']]])
        check('every_actual_allocation_cleaned',all(x['initialization_attempted'] is True
              and x['cleanup_observed'] is True for x in value['resources']))
    check('exact9_resource_nodes',len(seen)==9 and set(seen)==set(expected))
    prerequisite = json.loads(fixed(result['prerequisite']['pin']))
    check('actual_import_only_prerequisite',prerequisite==result['prerequisite']['data']
          and prerequisite['accepted_prerequisite'] is True and prerequisite['exception'] is None
          and prerequisite['pid']==result['child_pid'] and prerequisite['profile_trace_before']==[None]*4
          and prerequisite['profile_trace_after']==[None]*4
          and prerequisite['pre_observer_resource_measurement'] is None)
    for row in result['new_run_index']['files']:
        if row.get('kind')=='regular':
            fixed(row)
        else:
            check('nonregular_index_entry_not_a_file_pin',not Path(row['path']).is_symlink())
    for row in result['new_run_index']['databases']:
        fixed(row['pin'])
        for side in row['sidecars']:
            path=Path(side['path'])
            check('new_closed_database_sidecars_absent',side['exists'] is False and not path.exists() and not path.is_symlink())
failures = [row for row in checks if not row['ok']]
receipt = dict(round='R251',command=name,status='STOP' if failures else 'ACCEPTED',
    result=pin(out/'result.json'),actual_tool_return=pin(out/'actual-tool-return.json'),source_index=source_pin,
    checks=checks,check_count=len(checks),failures=failures,outer_streams=streams,
    T2_complete=False,T12_complete=False)
target = D/('root-'+name+('-acceptance-failure.json' if failures else '-acceptance.json'))
raw = (json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
with target.open('xb') as stream:
    if stream.write(raw)!=len(raw):
        raise OSError('partial ROOT acceptance write')
if target.read_bytes()!=raw:
    raise ValueError('ROOT acceptance readback differs')
print(json.dumps(dict(status=receipt['status'],command=name,checks=len(checks),
      failures=failures[:3],acceptance=pin(target)),ensure_ascii=False))
if failures:
    raise SystemExit(1)
