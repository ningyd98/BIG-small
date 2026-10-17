"""ROOT evidence integrity settlement for unexpected R242 start-barrier failure; no repair."""
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
B = R / 'artifacts/research/process/20261004-ced-development'
A = B / 'astra-rounds'
D = A / 'round242-p6-t2-writer-barrier-condition-synchronization-20261015'
E = A / 'round245-p6-t2-missing-temporary-evidence-continuation-20261015'
O = D / 'implementation/red'
STATE = B / 't12-sol-handoff-20261007/active-t12-state.json'
PHASE = B / 't12-sol-handoff-20261007/phase-summary.md'
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
    check(label, raw is not None and pin(p, raw) == identity(row), expected=identity(row))
    return raw
def encoded(x):
    return (json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def save(p, x):
    raw = x if isinstance(x, bytes) else encoded(x)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as stream:
        stream.write(raw)
    if p.read_bytes() != raw:
        raise ValueError('exclusive evidence preservation differs')
    return pin(p, raw)

actual = json.loads((O / 'actual-tool-return.json').read_bytes())
result = json.loads((O / 'result.json').read_bytes())
invocation = json.loads((O / 'invocation.json').read_bytes())
gate = json.loads((D / 'script-gate.json').read_bytes())
drafts = json.loads((D / 'root-unreserved-literal-transports.json').read_bytes())
baseline = json.loads(fixed(result['source_index_pin'], 'accepted_baseline'))
expected = [x for x in gate['commands']['red']['argv'] if '::' in x]
check('actual_once_original_session', actual['attempt'] == 1 and actual['retry'] == 0
      and actual['initial']['session_id'] == 12220 and len(actual['polls']) == 2
      and actual['polls'][0]['session_id'] == 12220
      and actual['polls'][-1] == actual['completion'] == actual['final'] == actual['actual_tool_return']
      and actual['final']['exit_code'] == 1 and actual['invocation'] == drafts['red']['invocation'])
check('tool_streams_unknown', actual['independent_stdout'] is None and actual['independent_stderr'] is None)
check('unexpected_outcome_preserved', result['child_exit'] == result['wrapper_exit'] == 1
      and result['accepted_command_outcome'] is False and result['timed_out'] is False
      and result['runner_exception'] is None and result['observation_errors'] == [])
check('process_reaped_no_group', result['cleanup'] ==
      {'leader_reaped': True, 'group_remaining': False, 'cleanup_notes': []})
check('actual_invocation', result['invocation'] == invocation
      and invocation['argv'] == gate['commands']['red']['argv']
      and invocation['finite_env'] == gate['commands']['red']['finite_env']
      and invocation['outer_capture'] == gate['commands']['red']['transport'])
for row in baseline['sources']:
    raw = fixed(row, 'current27')
    check('full_current_and_physical', raw == base64.b64decode(row['base64'], validate=True)
          and fixed(row['physical'], 'physical27') == raw
          and Path(row['path']).stat().st_mode == row['mode'])
for row in baseline['protected']:
    fixed(row, 'protected211')
for row in baseline['scripts']:
    check('script_full_bytes', fixed(row, 'frozen_script') == base64.b64decode(row['base64'], validate=True))
for row in baseline['history_observations']:
    if row['hash_match'] is True:
        raw = fixed(row['resolved'], 'available_history')
        check('available_history_equivalence', len(raw) == row['original']['bytes']
              and hashlib.sha256(raw).hexdigest() == row['original']['sha256'])
for row in result['input_records']:
    fixed(row, 'fixed_command_input')
check('exact_input_records', result['input_records'] == gate['commands']['red']['input_records'])
check('source_after_exact', result['source_after'] ==
      {'all_unchanged': True, 'sources': [identity(x) for x in baseline['sources']], 'protected_count': 211}
      and json.loads((O / 'source-after.json').read_bytes()) == result['source_after'])
check('historical_unavailable35_exact', result['historical_unavailable'] == baseline['historical_registry']
      and len(result['historical_unavailable']) == 35 and result['all_historical_bytes_available'] is False)
for row in result['historical_unavailable']:
    p = Path(row['original']['path'])
    check('unavailable_remains_absent', not p.exists() and not p.is_symlink() and row['hash_match'] is None)
for row in baseline['sidecar_states']:
    p = Path(row['path'])
    check('old90_sidecar_absence', row['exists'] is False and not p.exists() and not p.is_symlink())
for row in result['streams'].values():
    fixed(row, 'actual_child_stream')
summary_raw = Path(drafts['red']['stdout_path']).read_bytes()
summary = json.loads(summary_raw)
check('actual_outer_summary', len(summary_raw) <= 6000 and summary['child_exit'] == summary['wrapper_exit'] == 1
      and summary['accepted_command_outcome'] is False and summary['result_pin'] == pin(O / 'result.json'))
check('actual_outer_stderr_empty', Path(drafts['red']['stderr_path']).read_bytes() == b'')
xml = ET.fromstring((O / 'junit.xml').read_bytes())
nodes = xml.findall('.//testcase')
names = [x.get('classname', '').replace('.', '/') + '.py::' + x.get('name', '') for x in nodes]
check('exact_three_actual_JUnit_failures', names == expected and len(nodes) == 3
      and all(x.find('failure') is not None and x.find('error') is None and x.find('skipped') is None for x in nodes))
failure_facts = []
for node, name in zip(nodes, names):
    failure = node.find('failure')
    text = failure.text or ''
    check('actual_failure_is_precondition_not_race_assertion', text.rstrip().endswith(
        'tests/test_local_public_writer_binding_race.py:221: AssertionError')
        and 'original worker poll ended' in failure.get('message', ''))
    failure_facts.append({'nodeid': name, 'message': failure.get('message'), 'trace_tail': text[-1100:]})
check('full_XML_failure_details_exact', result['JUnit']['failure_details'] ==
      [{'nodeid': name, 'text': ET.tostring(node, encoding='unicode')} for node, name in zip(nodes, names)])
cases = {}
for row in result['cases']:
    raw = fixed(row['pin'], 'raw_case')
    c = json.loads(raw)
    check('case_full_embedded_equality', c == row['data'])
    filename = Path(row['pin']['path']).name
    cases[filename] = c
    kinds = [x['kind'] for x in c['order']]
    check('actual_start_timeout_wrong_cause', c['writer']['attempted'] is False
          and c['writer']['returned'] is False and c['writer_joined'] is True
          and c['writer']['exception']['type'] == 'AssertionError'
          and c['writer']['exception']['message'].startswith('R223 writer start barrier timed out')
          and c['bootstrap_complete'] is False and c['binding'] is None
          and c['before'] is None and c['after'] is None
          and 'legacy_after' not in c and 'complete_receipts' not in c
          and kinds == ['WRITER_READY', 'WRITER_RAISED', 'PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK']
          and [x['sequence'] for x in c['order']] == [1, 2, 3]
          and all(x['pid'] == result['child_pid'] for x in c['order']))
check('three_case_exact_map', set(cases) ==
      {hashlib.sha256(x.encode()).hexdigest() + '.json' for x in expected})
resources = result['resource_summary']
check('resource_complete_raw_summary', json.loads((O / 'resource-summary.json').read_bytes()) == resources
      and resources['all_records_valid'] is True and resources['validation_errors'] == [])
counts = Counter()
resource_nodes = []
for row in resources['records']:
    raw = fixed(row['pin'], 'raw_resource')
    value = json.loads(raw)
    node = value['nodeid']
    resource_nodes.append(node)
    case = cases[hashlib.sha256(node.encode()).hexdigest() + '.json']
    check('resource_raw_provenance', value == row['data'] and row['error'] is None
          and value['pid'] == result['child_pid'] and value['command_id'] == 'R223'
          and value['allocation_attempts'] == len(value['resources']) and value['cleanup_errors'] == [])
    observations = value['observations']
    check('actual_observer_restored', observations['observers_restored'] is True
          and observations['method_restoration'] is True and observations['assertions_completed'] is False
          and observations['r223'] == case and observations['scenarios'] == [case])
    check('unknown_coverage_stays_null', all(x is None for x in value['unobserved'].values()))
    by_id = {x['resource_id']: x for x in value['resources']}
    check('per_case_unique_actual_resources', len(by_id) == len(value['resources']))
    counts['allocation_attempts'] += len(value['resources'])
    lifecycles = value['worker_lifecycles']
    for call in lifecycles:
        counts['attempted_poll_lifecycles'] += 1
        counts['entered_poll_lifecycles'] += int(call['entered'])
        counts['normally_returned_poll_lifecycles'] += int(call['returned_normally'])
        check('actual_normal_poll_despite_no_episode', call['attempted'] is True and call['entered'] is True
              and call['returned_normally'] is True and call['return_value'] is True and call['exception'] is None
              and 0 < call['start_sequence'] < call['entry_sequence'] < call['end_sequence']
              and by_id[call['worker_resource_id']]['kind'] == 'worker')
    for obj in value['resources']:
        counts['initialized'] += int(obj['initialized'])
        counts['kind:' + obj['kind']] += 1
        counts['cleanup_observed'] += int(obj['cleanup_observed'])
        check('observed_resource_cleanup_and_identity', obj['cleanup_observed'] is True
              and obj['initialization_attempted'] is True and obj['pid'] == result['child_pid'])
        if obj['kind'] == 'worker':
            counts['constructed_worker_attempts'] += 1
            counts['initialized_workers'] += int(obj['initialized'])
            actual_polls = [x['poll_id'] for x in lifecycles if x['worker_resource_id'] == obj['resource_id']]
            check('worker_exact_poll_links_and_idle', obj['poll_ids'] == actual_polls and obj['final_active_job_id'] == '')
            if not actual_polls:
                counts['never_polled_workers'] += 1
                check('never_polled_no_owned_runtime', obj['cleanup_basis'] == 'never_polled_no_owned_runtime'
                      and obj['session_resource_ids'] == obj['broker_resource_ids'] == obj['heartbeat_resource_ids'] == []
                      and obj['close_attempts'] == [])
            else:
                check('actual_runtime_released', obj['cleanup_basis'] == 'poll_finished_runtime_released')
            for field, kind in [('session_resource_ids', 'lease_session'), ('broker_resource_ids', 'broker_thread'),
                                ('heartbeat_resource_ids', 'heartbeat_thread')]:
                for linked in obj[field]:
                    check('actual_runtime_owner_links', by_id[linked]['kind'] == kind
                          and by_id[linked]['worker_resource_id'] == obj['resource_id'])
        if obj['kind'] in ('helper_thread', 'broker_thread', 'heartbeat_thread'):
            check('real_thread_joined', obj['alive_after_join'] is False
                  and type(obj['thread_ident']) is int and type(obj['native_thread_id']) is int)
            if obj['kind'] == 'helper_thread':
                check('original_writer_identity_matches_raw_case', obj['thread_ident'] == case['order'][0]['thread']
                      and obj['native_thread_id'] == case['order'][0]['native_thread'])
        if obj['kind'] == 'lease_session':
            check('actual_session_broker_stopped', obj['broker_alive'] is False)
check('exact_resource_node_map', Counter(resource_nodes) == Counter(expected))
check('independent_actual_counts', dict(counts) == resources['counts'])
prereq = result['prerequisite']
data = json.loads(fixed(prereq['pin'], 'actual_prerequisite_record'))
check('unchanged_startup_prerequisite', data == prereq['data'] and data['pid'] == result['child_pid']
      and data['accepted_prerequisite'] is True and data['exception'] is None
      and data['expected_pin'] == data['actual_file_pin']
      and data['same_sys_modules_object_after'] is True and data['pre_observer_resource_measurement'] is None
      and data['profile_trace_before'] == data['profile_trace_after'] == [None] * 4)
fixed(data['actual_file_pin'], 'original_preloaded_module')
new_index = result['new_run_index']
check('new_durable_index_exact', new_index == json.loads((O / 'persistent-file-database-index.json').read_bytes())
      and new_index['retained_in_place'] is True and new_index['old_bytes_recovered'] is False
      and new_index['SQL'] is False and len(new_index['databases']) == 6)
for row in new_index['databases']:
    fixed(row['pin'], 'actual_new_DB_bytes_after_process_closure')
    check('new_DB_workspace_path', Path(row['pin']['path']).is_relative_to(O / 'persistent-basetemp'))
    for side in row['sidecars']:
        p = Path(side['path'])
        check('actual_new_sidecar_absence', side['exists'] is False and side['is_symlink'] is False
              and side['pin'] is None and not p.exists() and not p.is_symlink())
check('file_temp_indexes_complete', result['file_index'] == json.loads((O / 'file-index.json').read_bytes())
      and result['temp_index'] == json.loads((O / 'temp-index.json').read_bytes()) == new_index['files'])
for row in result['file_index']:
    if row['kind'] == 'regular':
        p = Path(row['path'])
        check('actual_index_regular_file', p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes'])
        if row['sha256'] is not None:
            fixed(row, 'full_index_file_bytes')
for row in invocation['controls_before']:
    raw = base64.b64decode(row['base64'], validate=True)
    check('complete_before_control_bytes', pin(Path(row['path']), raw) == identity(row))
    if row['path'] == str(D / 'command-ledger.json'):
        obj = json.loads(raw)
        obj['commands']['red'].update(state='SPENT', used=1, remaining=0, reservation_id=invocation['reservation_id'])
        check('exact_author_RED_consumption', Path(row['path']).read_bytes() == encoded(obj))
    else:
        fixed(row, 'other_controls_unchanged_during_RED')
state_before, phase_before = STATE.read_bytes(), PHASE.read_bytes()
check('STATE_before_exact', pin(STATE, state_before) ==
      {'path': str(STATE), 'bytes': 134368, 'sha256': 'f4bfab50b83650d53b148cd39bf0a723a1386c4b6911d50a691772df6fca9407'})
check('PHASE_before_exact', pin(PHASE, phase_before) ==
      {'path': str(PHASE), 'bytes': 88039, 'sha256': '3e2c368198d54f8aa5a3daab4a4170df7b7a419f89cbb5bcf3abfad04ec8c093'})
state = json.loads(state_before)
check('planning_keys_new', 'R242' not in state['planning'] and 'R245' not in state['planning'])
failures = [x for x in checks if not x['ok']]
if failures:
    save(D / 'root-evidence-integrity-failure.json', {'checks': checks, 'failures': failures})
    print(json.dumps({'status': 'STOP', 'failure_count': len(failures), 'failures': failures[:4]}, ensure_ascii=False))
    raise SystemExit(1)
controls = {D / name: (D / name).read_bytes() for name in
            ('source-gate.json', 'script-gate.json', 'root-activation.json',
             'root-command-ledger.json', 'command-ledger.json')}
controls.update({STATE: state_before, PHASE: phase_before})
before = D / 'before/root-final-evidence-settlement'
pairs = []
for path, raw in controls.items():
    archive = before / path.name
    save(archive, raw)
    pairs.append({'original': pin(path, raw), 'archive': pin(archive), 'base64': base64.b64encode(raw).decode()})
before_pin = save(before / 'index.json', {'records': pairs})
evidence_pin = save(D / 'root-evidence-acceptance.json',
    {'status': 'INTEGRITY_ACCEPTED_UNEXPECTED_START_BARRIER_FAILURE_NOT_LEGAL_RED',
     'checks': checks, 'check_count': len(checks), 'actual': pin(O / 'actual-tool-return.json'),
     'result': pin(O / 'result.json'), 'failure_facts': failure_facts,
     'cases': [{'pin': x['pin'], 'data': x['data']} for x in result['cases']],
     'actual_resources': dict(counts), 'new_retained_databases': new_index['databases'],
     'historical_unavailable_count': 35, 'all_historical_bytes_available': False,
     'complete_before': before_pin, 'legal_RED': False, 'GREEN': False,
     'T2_complete': False, 'T12_complete': False, 'native': False, 'formal': False,
     'next': 'STOP for actual R248 start-barrier synchronization plan'})
step_pin = save(D / 'step-report.json',
    {'round': 'R242', 'status': 'BASELINE_RUFF_ACCEPTED_RED_SPENT_UNEXPECTED_NOT_LEGAL',
     'plan': pin(D / 'plan.json'), 'overlay': pin(E / 'plan.json'),
     'baseline': pin(D / 'root-baseline-acceptance.json'), 'Ruff': pin(D / 'root-ruff-acceptance.json'),
     'evidence': evidence_pin, 'fixture': baseline['fixture_after'],
     'source_change': 'Exact two-byte removal of release.wait argument; original assertions/finally preserved',
     'new_failure': 'All three writers timed out at start.wait(10) before genuine private bootstrap entry',
     'actual_resources': dict(counts), 'new_databases': 6, 'historical_missing_DB': 30,
     'historical_missing_raw': 5, 'source_dispositions': ['R244', 'R246', 'R247'],
     'slots': {x: {'used': 1, 'remaining': 0} for x in ('baseline', 'ruff', 'red')},
     'legal_RED': False, 'GREEN': False, 'T2_complete': False, 'T12_complete': False,
     'native': False, 'formal': False, 'Git_commands': 0})
save(D / 'step-report.md', '# R242 结果\n\n基线与窄 Ruff 已独立接受。唯一恢复 RED 的三例均在 writer 启动事件十秒等待超时后才进入真实 bootstrap，未发生目标竞争写入；原221行前置断言失败，不是合法 RED。\n\n564次实际资源尝试、561次初始化、564次观察清理；3次真实正常 poll、6个 worker（3个未 poll）。进程已回收且无残余组。只覆盖冻结观察器实际记录，未知 OS/native/network 保持 null。\n\n六个本次真实数据库在工作区原位留存；旧30数据库与5原回执缺失状态单独保留，不冒充恢复。三槽各一次已花完；等待实际 Astra R248。T2/T12/native/formal 未完成，Git 未放行。\n'.encode())
state['planning']['R242'] = {'status': 'RED_SPENT_UNEXPECTED_START_BARRIER_TIMEOUT_NOT_LEGAL',
                             'plan': pin(D / 'plan.json'), 'step_report': step_pin, 'evidence': evidence_pin,
                             'fixture': baseline['fixture_after'], 'next': 'actual R248 plan pending',
                             'legal_RED': False, 'T2_complete': False, 'T12_complete': False}
state['planning']['R245'] = {'status': 'ACCEPTED_DECLARED_HISTORICAL_EVIDENCE_LOSS',
                             'plan': pin(E / 'plan.json'), 'missing_databases': 30, 'missing_raw': 5,
                             'old_bytes_recovered': False, 'new_R242_DB_retained': 6}
old_state = json.loads(state_before)
compare = json.loads(encoded(state))
del compare['planning']['R242'], compare['planning']['R245']
if compare != old_state:
    raise ValueError('STATE changed outside two authorized planning entries')
new_phase = phase_before + ('\n\n## R242 与 R245（2026-10-15）\n\nR242 两字节条件同步修改、完整基线及窄 Ruff 已验证；三节点恢复 RED 实际3FAIL/0ERROR/0SKIP但均先发生 writer start.wait(10) 超时，bootstrap_complete=false、无实际 legacy 竞争写入，故不是合法 RED。564实际资源尝试/561初始化/564观察清理，3正常 poll、6 workers（3未poll）；进程回收、无残余组。六个本次真实 DB 在工作区原位保存，旧30 DB/5 raw 当前缺失单独隔离，不声称历史完整复验。R244/R246只读展示错误及R247易失store错误原件保留，均按实际Astra计划恢复源码准备，未新增运行槽。\n\n三本轮槽各用1/余0；等待实际 R248 计划。event3/GREEN9、父GREEN7、fresh review12、Git0维持未放行；T2/T12/native/formal未完成。证据：'+str(D / 'root-evidence-acceptance.json')+'\n').encode()
root = json.loads(controls[D / 'root-command-ledger.json'])
root['commands']['red']['state'] = 'SPENT_UNEXPECTED_START_BARRIER_TIMEOUT_NOT_LEGAL'
gate['commands']['red']['state'] = 'SPENT_UNEXPECTED_START_BARRIER_TIMEOUT_NOT_LEGAL'
source_gate = json.loads(controls[D / 'source-gate.json'])
source_gate.update(status='STOP_ASTRA_R248_START_BARRIER_FAILURE', execution_released=False, evidence=evidence_pin)
mutations = {STATE: encoded(state), PHASE: new_phase,
             D / 'root-command-ledger.json': encoded(root), D / 'script-gate.json': encoded(gate),
             D / 'source-gate.json': encoded(source_gate),
             D / 'root-activation.json': encoded({'status': 'STOP_ASTRA_R248', 'execution_released': False,
                                                  'evidence': evidence_pin, 'step_report': step_pin})}
for path, raw in controls.items():
    if path.read_bytes() != raw:
        raise ValueError('immediate full before/CAS differs')
for path, raw in mutations.items():
    temporary = D / ('.root-final-' + path.name + '.tmp')
    save(temporary, raw)
    os.replace(temporary, path)
receipt = {'status': 'R242_SETTLED_UNEXPECTED_NOT_LEGAL_RED', 'checks': len(checks),
           'evidence': evidence_pin, 'step_report': step_pin, 'complete_before': before_pin,
           'STATE': pin(STATE), 'PHASE': pin(PHASE),
           'final_controls': [pin(D / name) for name in ('source-gate.json', 'script-gate.json',
                                'root-activation.json', 'root-command-ledger.json', 'command-ledger.json')],
           'new_retained_databases': new_index['databases'], 'historical_missing_count': 35,
           'legal_RED': False, 'T2_complete': False, 'T12_complete': False}
save(D / 'root-settlement-receipt.json', receipt)
print(json.dumps({k:v for k,v in receipt.items() if k in ('status','checks','STATE','PHASE')}, ensure_ascii=False))
