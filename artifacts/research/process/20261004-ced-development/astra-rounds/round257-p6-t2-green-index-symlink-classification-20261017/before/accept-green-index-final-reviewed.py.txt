"""Independent ROOT acceptance of one actual R251 result; metadata bytes only."""
import base64
import hashlib
import json
import os
import re
import signal
import stat
import traceback
from collections import Counter
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

R = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = R/'artifacts/research/process/20261004-ced-development/astra-rounds/round251-p6-t2-event3-entry-fence-continuation-20261017'
E = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round257-p6-t2-green-index-symlink-classification-20261017")
checks = []
tracked = {}
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
    tracked[str(path)] = identity(row)
    return raw
def read(path):
    return json.loads(path.read_bytes())

def signature(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def own_regular_pin(path, before):
    descriptor = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        begin = os.fstat(descriptor)
        check('own_descriptor_initial_identity',stat.S_ISREG(begin.st_mode) and signature(begin)==signature(before))
        digest = hashlib.sha256()
        length = 0
        while True:
            block = os.read(descriptor,1024*1024)
            if not block:
                break
            digest.update(block)
            length += len(block)
        end = os.fstat(descriptor)
        check('stable_own_regular_descriptor',signature(begin)==signature(end)
              and signature(end)==signature(path.lstat()) and length==begin.st_size)
    finally:
        os.close(descriptor)
    return dict(path=str(path),bytes=length,sha256=digest.hexdigest())

def exact_index(result, observation257):
    base = D/'implementation/green/persistent-basetemp'
    check('real_persistent_root',stat.S_ISDIR(base.lstat().st_mode) and not base.is_symlink())
    index = result['new_run_index']
    check('raw_index_full_equal',read(D/'implementation/green/persistent-file-database-index.json')==index)
    rows = index['files']
    recorded = {row['path']:row for row in rows}
    expected = {row['recorded']['path']:row['recorded'] for row in observation257['all548_records']}
    check('unique_exact548_records',len(rows)==len(recorded)==548 and recorded==expected)
    check('bounded_metadata_record_set',0<len(rows)<=10000)
    def current_set():
        found=set()
        for root,dirs,files in os.walk(base,followlinks=False):
            found.update(str(Path(root)/name) for name in dirs+files)
        return found
    check('complete_nofollow_initial_set',current_set()==set(recorded))
    database_rows = index['databases']
    databases = {row['pin']['path']:row for row in database_rows}
    check('exact18_full_database_authorities',len(databases)==len(database_rows)==18)
    allowed_links = {path:row for path,row in expected.items() if row['kind']=='symlink'}
    check('exact_four_recorded_link_identities',len(allowed_links)==4)
    starts = {}
    actual_pins = []
    kinds = Counter()
    deferred = set()
    for row in rows:
        path = Path(row['path'])
        check('own_path_lexically_inside_base',path.is_absolute() and path.is_relative_to(base)
              and path!=base and '..' not in path.parts)
        if not (path.is_absolute() and path.is_relative_to(base) and path!=base and '..' not in path.parts):
            raise ValueError('index path outside exact persistent root')
        parent = path.parent
        while parent!=base:
            check('no_symlink_ancestor',stat.S_ISDIR(parent.lstat().st_mode) and not parent.is_symlink())
            parent=parent.parent
        before=path.lstat()
        starts[str(path)]=signature(before)
        check('recorded_lstat_mode_and_size',before.st_mode==row['mode'] and before.st_size==row['bytes'])
        kind=row['kind']
        kinds[kind]+=1
        if kind=='directory':
            check('exact_directory_variant',stat.S_ISDIR(before.st_mode) and row['sha256'] is None)
        elif kind=='symlink':
            target=os.readlink(path)
            target_path=Path(os.path.normpath(str(path.parent/target))) if not Path(target).is_absolute() else Path(os.path.normpath(target))
            check('exact_recorded_link_text',str(path) in allowed_links and row==allowed_links[str(path)]
                  and stat.S_ISLNK(before.st_mode) and target==row['target']
                  and len(target.encode())==row['bytes'] and row['sha256'] is None)
            check('exact_same_root_directory_target',target_path.is_relative_to(base) and '..' not in Path(target).parts
                  and str(target_path) in recorded and recorded[str(target_path)]['kind']=='directory'
                  and stat.S_ISDIR(target_path.lstat().st_mode) and not target_path.is_symlink()
                  and target_path.lstat().st_mode==recorded[str(target_path)]['mode']
                  and target_path.lstat().st_size==recorded[str(target_path)]['bytes'])
        elif kind=='regular':
            check('real_own_regular_variant',stat.S_ISREG(before.st_mode))
            actual=own_regular_pin(path,before)
            if row['sha256'] is None:
                check('only_exact_deferred_database_variant',str(path) in databases
                      and row.get('database_bytes_read') is False and path.suffix in ('.db','.sqlite','.sqlite3'))
                authority=databases[str(path)]['pin']
                check('actual_full_deferred_database_pin',actual==identity(authority) and row['bytes']==authority['bytes'])
                deferred.add(str(path))
            else:
                check('strict_own_regular_content_pin',isinstance(row['sha256'],str)
                      and re.fullmatch('[0-9a-f]{64}',row['sha256']) is not None
                      and str(path) not in databases and actual==identity(row))
            actual_pins.append(actual)
        else:
            check('reject_special_index_variant',False)
        check('each_record_stable',signature(path.lstat())==signature(before))
    check('exact_variant_denominators',dict(kinds)==dict(directory=177,symlink=4,regular=367)
          and deferred==set(databases))
    sidecars=[]
    for value in database_rows:
        path=Path(value['pin']['path'])
        check('independent_full_database_pin',own_regular_pin(path,path.lstat())==identity(value['pin']))
        expected_sides={str(path)+suffix for suffix in ('-wal','-shm','-journal')}
        check('three_exact_database_sidecars',{row['path'] for row in value['sidecars']}==expected_sides)
        for row in value['sidecars']:
            check('new_database_sidecar_exact_absence',row['exists'] is False and row['is_symlink'] is False
                  and row['pin'] is None and not os.path.lexists(row['path']))
            sidecars.append(row['path'])
    check('exact54_new_sidecars',len(sidecars)==len(set(sidecars))==54)
    for row in rows:
        path=Path(row['path'])
        check('all_record_lstat_stable_at_end',signature(path.lstat())==starts[str(path)])
        if row['kind']=='symlink':
            target=Path(os.path.normpath(str(path.parent/row['target']))) if not Path(row['target']).is_absolute() else Path(os.path.normpath(row['target']))
            check('recorded_link_text_and_target_stable_at_end',os.readlink(path)==row['target']
                  and str(target) in starts and signature(target.lstat())==starts[str(target)])
    check('complete_nofollow_final_set',current_set()==set(recorded))
    return dict(record_count=len(rows),counts=dict(kinds),deferred_databases=len(deferred),
                sidecars=len(sidecars),own_regular_pins=actual_pins,alias_content_hashes=0)

def main():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('R257 metadata120s')))
    signal.alarm(120)
    plan257 = json.loads(fixed(dict(path=str(E/'plan.json'),bytes=22409,sha256='acca86bd1a4ac8df1f6977eda2625cbacd6115ea23c83dc643d82f0988deff1d')))
    for row in plan257['inputs']:
        fixed(row)
    observation257 = json.loads(fixed(next(row for row in plan257['inputs'] if row['path']==str(E/'input-observation.json'))))
    proof = read(E/'source-input-argv-gate.json')
    check('ROOT_full_saved_source_gate',proof['source']==pin(Path(__file__)) and proof['status']=='APPROVED_ONE_METADATA_ATTEMPT'
          and (proof['authorized'],proof['used'],proof['remaining'])==(1,1,0))
    for row in proof['inputs']:
        fixed(row)
    for row in proof['full_before_controls']:
        check('complete_before_control_bytes',fixed(row)==base64.b64decode(row['base64'],validate=True))
    for name in ('receipt','failure','actual','stdout','stderr'):
        path=Path(plan257['execution']['full_outputs'][name])
        if name not in ('stdout','stderr'):
            check('new_output_absent',not os.path.lexists(path))
    check('exact_ROOT_metadata_execution',sys.argv==plan257['execution']['argv'][1:]
          and Path.cwd()==R and all(os.environ.get(k)==v for k,v in plan257['execution']['finite_env'].items()))
    if len(sys.argv)!=2 or sys.argv[1] != 'green':
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
    for role_path in (Path(plan['budget_continuation']['ROOT_ledger']),Path(plan['budget_continuation']['author_ledger'])):
        held=read(role_path)['commands']['root_settlement']
        check('original_ROOT_settlement_still_held',held['used']==0 and held['remaining']==1 and held['state'].startswith('HELD'))
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
    
    check('old90_sidecar_observations',len(snapshot['sidecar_states'])==90)
    for row in snapshot['sidecar_states']:
        path=Path(row['path'])
        check('strict_old90_sidecar_absence',row['exists'] is False and not os.path.lexists(path))
    check('existing12_DB36_sidecars',len(snapshot['retained_workspace_databases'])==12
          and sum(len(x['sidecars']) for x in snapshot['retained_workspace_databases'])==36)
    for row in snapshot['retained_workspace_databases']:
        fixed(row['pin'])
        for side in row['sidecars']:
            check('strict_existing36_sidecars_absent',side['exists'] is False and side['is_symlink'] is False
                  and not os.path.lexists(side['path']))
    check('legal_RED_lineage',json.loads(fixed(plan['inputs']['legal_RED_acceptance']))['legal_RED'] is True
          and json.loads(fixed(plan['inputs']['legal_RED_receipt']))['legal_RED'] is True)
    green = result
    green_command = next(x for x in plan['commands'] if x['id']=='green')
    expected = green_command['nodeids']
    xml = ET.fromstring((D/'implementation/green/junit.xml').read_bytes())
    nodes = xml.findall('.//testcase')
    nodeids = [x.get('classname','').replace('.','/')+'.py::'+x.get('name','') for x in nodes]
    check('exact9_PASS',nodeids==expected and len(nodes)==9
          and all(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in nodes)
          and green['JUnit']['nodeids']==expected
          and (green['JUnit']['tests'],green['JUnit']['passes'],green['JUnit']['failures'],
               green['JUnit']['errors'],green['JUnit']['skips'])==(9,9,0,0,0))
    case_by_node = {}
    behavior_facts = []
    for row in green['cases']:
        value = json.loads(fixed(row['pin']))
        check('full_case_record',value==row['data'])
        node = next(x for x in expected if hashlib.sha256(x.encode()).hexdigest()+'.json'==Path(row['pin']['path']).name)
        if node in case_by_node:
            raise ValueError('duplicate actual case')
        case_by_node[node]=value
        function = node.split('::',1)[1].split('[',1)[0]
        modes = {'test_late_binding_rejects_public_writer':'race',
                 'test_late_binding_rejects_public_writer_second_connection':'race',
                 'test_writer_committed_before_binding_is_legacy':'before',
                 'test_bound_negative_cancellation_remains_supported':'negative',
                 'test_unbound_legacy_writer_roundtrip':'unbound'}
        mode = modes[function]
        second = function=='test_late_binding_rejects_public_writer_second_connection'
        backend = 'sqlite' if second else node.rsplit('[',1)[1].removesuffix(']')
        check('case_identity_matches_frozen_node',value['mode']==mode and value['backend']==backend
              and (mode=='unbound' or value['second_connection'] is second))
        if mode=='unbound':
            check('unbound_real_legacy_roundtrip',value['binding'] is None and value['polled'] is False
                  and value['worker_active_job_id']=='' and value['before']!=value['first']!=value['after'])
            if value['backend']=='memory':
                check('unbound_memory_RUN_PAUSE',value['first']=={'present':True,'value':'RUNNING'}
                      and value['after']=={'present':True,'value':'PAUSED'})
            else:
                check('unbound_SQLite_RUN_PAUSE',len(value['first'])==len(value['after'])==1
                      and value['first'][0]['current_state']=='RUNNING' and value['after'][0]['current_state']=='PAUSED')
        else:
            bootstrap,receipts = value['bootstrap'],value['complete_receipts']
            transaction = bootstrap['transaction']
            common = ('operation_id','operation_sha256','job_id','attempt','lease_id','epoch',
                      'generation','row_revision','phase','event_record_hash','event_receipt_hash','job_receipt_hash')
            check('genuine_private_binding_dual_COMPLETE',value['bootstrap_complete'] is True
                  and value['binding']==bootstrap['original_time'] and transaction['phase']=='COMPLETE'
                  and set(receipts)=={'event','job'} and len(receipts['event'])==len(receipts['job'])==1
                  and receipts['event']==receipts['job']
                  and all(all(r[k]==transaction[k] for k in common) for group in receipts.values() for r in group))
            order = value['order']
            kinds = [x['kind'] for x in order]
            check('actual_order_identity',all(x['pid']==green['child_pid'] for x in order)
                  and [x['sequence'] for x in order]==list(range(1,len(order)+1)))
            if mode in ('race','before'):
                by_kind = {x['kind']:x for x in order}
                helper = by_kind['WRITER_READY']
                inner = by_kind['ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK']
                main_entry = by_kind['PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK']
                complete = by_kind['DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE']
                check('real_helper_and_storage_identity',
                      helper['thread']==inner['thread'] and helper['native_thread']==inner['native_thread']
                      and helper['repository']==inner['repository']
                      and main_entry['thread']==complete['thread']
                      and main_entry['native_thread']==complete['native_thread']
                      and main_entry['thread']!=helper['thread']
                      and (helper['repository']!=main_entry['repository']) is second
                      and inner['code_name'].endswith('.save_state')
                      and value['exit_exception'] is None)
            if mode=='race':
                error = value['writer']['exception']
                check('late_bound_positive_writer_rejected',value['writer_joined'] is True
                      and value['writer']['attempted'] is True and value['writer']['returned'] is False
                      and isinstance(error,dict) and error['type']=='ValueError'
                      and re.search('private|operational|scope',error['message']) is not None
                      and value['legacy_before']==value['legacy_after']
                      and kinds.index('ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK')
                          <kinds.index('DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE')
                          <kinds.index('ORIGINAL_WRITER_RELEASED_TOWARD_REAL_INNER_LOCK')
                          <kinds.index('WRITER_RAISED'))
            elif mode=='before':
                check('real_writer_before_binding_allowed',value['writer_joined'] is True
                      and value['writer']['returned'] is True and value['writer']['exception'] is None
                      and value['legacy_before']!=value['legacy_after']
                      and kinds.index('LEGACY_WRITER_FINISHED_BEFORE_BINDING')
                          <kinds.index('DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE'))
            elif mode=='negative':
                check('exact_bound_negative_kept',value['negative_state']=='CANCELLED'
                      and value['unchanged_budget']==bootstrap['payload']['state']
                      and value['legacy_before']==value['legacy_after'])
            else:
                raise ValueError('unrecognized frozen scenario')
        behavior_facts.append({'nodeid':node,'mode':mode,'backend':value['backend'],'case':row['pin']})
    check('exact9_case_map',set(case_by_node)==set(expected))
    summary = green['resource_summary']
    counts = Counter()
    resource_nodes = []
    for row in summary['records']:
        value = json.loads(fixed(row['pin']))
        node = value['nodeid']
        resource_nodes.append(node)
        check('full_actual_resource_record',value==row['data'] and row['error'] is None
              and value['pid']==green['child_pid'] and value['command_id']=='R223'
              and value['allocation_attempts']==len(value['resources']) and value['cleanup_errors']==[])
        obs = value['observations']
        check('behavior_and_hooks_restored',obs['assertions_completed'] is True
              and obs['observers_restored'] is True and obs['method_restoration'] is True and obs['exit_exception'] is None)
        check('actual_scenario_raw_match',obs['scenarios']==[case_by_node[node]]
              and all(x is None for x in value['unobserved'].values()))
        by_id = {x['resource_id']:x for x in value['resources']}
        check('unique_actual_resource_ids',len(by_id)==len(value['resources']))
        counts['allocation_attempts']+=len(value['resources'])
        for call in value['worker_lifecycles']:
            counts['attempted_poll_lifecycles']+=1
            counts['entered_poll_lifecycles']+=int(call['entered'])
            counts['normally_returned_poll_lifecycles']+=int(call['returned_normally'])
            check('actual_completed_poll',call['attempted'] is True and call['entered'] is True
                  and call['returned_normally'] is True and call['return_value'] is True and call['exception'] is None
                  and 0<call['start_sequence']<call['entry_sequence']<call['end_sequence'])
        for obj in value['resources']:
            counts['initialized']+=int(obj['initialized'])
            counts['kind:'+obj['kind']]+=1
            counts['cleanup_observed']+=int(obj['cleanup_observed'])
            check('actual_observed_cleanup',obj['initialization_attempted'] is True
                  and obj['cleanup_observed'] is True and obj['pid']==green['child_pid'])
            if obj['kind']=='worker':
                counts['constructed_worker_attempts']+=1
                counts['initialized_workers']+=int(obj['initialized'])
                polls = [x['poll_id'] for x in value['worker_lifecycles'] if x['worker_resource_id']==obj['resource_id']]
                check('actual_worker_poll_links_idle',obj['poll_ids']==polls and obj['final_active_job_id']=='')
                if not polls:
                    counts['never_polled_workers']+=1
                    check('never_polled_no_owned_runtime',obj['cleanup_basis']=='never_polled_no_owned_runtime'
                          and obj['session_resource_ids']==obj['broker_resource_ids']==obj['heartbeat_resource_ids']==[])
                else:
                    check('polled_runtime_released',obj['cleanup_basis']=='poll_finished_runtime_released')
                for field,kind in (('session_resource_ids','lease_session'),('broker_resource_ids','broker_thread'),
                                   ('heartbeat_resource_ids','heartbeat_thread')):
                    for linked in obj[field]:
                        check('real_runtime_owner',by_id[linked]['kind']==kind
                              and by_id[linked]['worker_resource_id']==obj['resource_id'])
            if obj['kind'] in ('helper_thread','broker_thread','heartbeat_thread'):
                check('real_thread_joined',obj['alive_after_join'] is False
                      and type(obj['thread_ident']) is int and type(obj['native_thread_id']) is int)
            if obj['kind']=='lease_session':
                check('real_session_released',obj['broker_alive'] is False)
    check('actual_resource_summary_valid',summary['all_records_valid'] is True
          and summary['validation_errors']==[] and Counter(resource_nodes)==Counter(expected)
          and dict(counts)==summary['counts'] and counts['attempted_poll_lifecycles']<=18)
    prerequisite = json.loads(fixed(green['prerequisite']['pin']))
    check('exact_import_only_prerequisite',prerequisite==green['prerequisite']['data']
          and prerequisite['accepted_prerequisite'] is True and prerequisite['exception'] is None
          and prerequisite['pid']==green['child_pid'] and prerequisite['profile_trace_before']==[None]*4
          and prerequisite['profile_trace_after']==[None]*4 and prerequisite['pre_observer_resource_measurement'] is None)
    fixed(prerequisite['actual_file_pin'])
    for row in green['streams'].values():
        fixed(row)
    
    index_evidence = exact_index(result, observation257)
    for row in list(tracked.values()):
        fixed(row)
    failures = [row for row in checks if not row['ok']]
    receipt = dict(round='R251',command=name,status='STOP' if failures else 'ACCEPTED',
        result=pin(out/'result.json'),actual_tool_return=pin(out/'actual-tool-return.json'),source_index=source_pin,
        checks=checks,check_count=len(checks),failures=failures,outer_streams=streams,
        T2_complete=False,T12_complete=False)
    receipt.update(metadata_round='R257',metadata_plan=pin(E/'plan.json'),metadata_source=pin(Path(__file__)),index_evidence=index_evidence)
    target = E/'implementation'/('failure.json' if failures else 'acceptance.json')
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
    
    signal.alarm(0)

if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        signal.alarm(0)
        target=E/'implementation/failure.json'
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            raw=(json.dumps(dict(round='R257',status='STOP',checks=checks,
                  exception=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())),
                  ensure_ascii=False,indent=2)+'\n').encode()
            with target.open('xb') as stream:
                stream.write(raw)
        traceback.print_exc()
        raise SystemExit(1)
