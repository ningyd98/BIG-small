"""ROOT independent acceptance of the actual R289 partial dual diagnostic; original factual accounting only, zero repairs."""
from pathlib import Path
from collections import Counter
import base64,copy,hashlib,json,os,signal,stat,time,xml.etree.ElementTree as ET
D=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017')
RUN=D/'implementation/dual_first_invalidation';name='dual_first_invalidation'
FROZEN=json.loads(r'''{"result":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/implementation/dual_first_invalidation/result.json","bytes":451744,"sha256":"5d4e8be30cbf6b6d3fe1ebaaa5799c20a2240da4e879442af19776a16e5b408a"},"actual_tool_return":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/implementation/dual_first_invalidation/actual-tool-return.json","bytes":5973,"sha256":"60d4193797d3ed3a6876bafc21785fd47343fa75290a4aa79162141aca992ca4"},"reservation":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/root-reservations/dual_first_invalidation.json","bytes":100223,"sha256":"f31e850d2c88f75bd79108d0d80ac670ea37df9378d8901ffea13472e8c24222"}}''')
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('ROOT dual factual metadata total120s')
signal.signal(signal.SIGALRM,expired);signal.alarm(120)
checks=[]
def check(ok,label):
 if time.monotonic()>=deadline:expired()
 assert ok,label
 checks.append(label)
def identity(q):return {k:q[k] for k in ('path','bytes','sha256')}
def pin(path,raw=None):
 p=Path(path);raw=p.read_bytes() if raw is None else raw
 return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def checked(q):
 p=Path(q['path']);raw=p.read_bytes()
 check(stat.S_ISREG(p.lstat().st_mode) and pin(p,raw)==identity(q),'physical:'+str(p))
 return raw
def doc(q):return json.loads(checked(q))
def encode(v):return (json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
def absent(path):check(not Path(path).exists() and not Path(path).is_symlink(),'absent:'+str(path))
def save(path,raw,mode=33204):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 p.chmod(stat.S_IMODE(mode));check(p.read_bytes()==raw and p.lstat().st_mode==mode,'exclusive_readback:'+str(p))
 return pin(p,raw)
def full(row):
 raw=base64.b64decode(row['base64'],validate=True)
 check(pin(row['original']['path'],raw)==identity(row['original']) and checked(row['archive'])==raw,'complete_before:'+row['original']['path'])
 if 'mode' in row:check(Path(row['archive']['path']).lstat().st_mode==row['mode'],'before_mode')
 return raw
r=doc(FROZEN['result']);t=doc(FROZEN['actual_tool_return']);res=doc(FROZEN['reservation'])
SG=doc(res['source_gate']);JG=doc(res['script_gate']);context=doc(res['context_manifest'])
check(r['round']==t['round']==res['round']=='R289' and r['command_id']==t['command_id']==res['command_id']==name,'actual_round_command')
check(r['attempt']==t['attempt']==1 and r['retry']==t['retry']==0 and r['child_exit']==1 and r['wrapper_exit']==0 and r['started'] is True and type(r['pid']) is int,'direct_once_child_wrapper0')
check(r['capture_integrity_complete'] is True and r['behavior_accepted'] is False and r['errors']==[] and r['legal_RED'] is r['GREEN'] is r['T2_complete'] is False,'behavior_only_no_T2_promotion')
check(r['timed_out'] is r['interrupted'] is r['output_limited'] is False and 0<r['elapsed_seconds']<615 and r['raw_size_observations']==[],'bounded_normal_run')
check(r['final_assessment']=={'status':'completed','error':None} and r['evidence_may_be_partial'] is True,'complete_failclosed_assessment')
check(t['invocation']==res['exact_tool_arguments']==res['command']['tool_arguments'],'literal_actual_transport')
final=t['final'];check(t['actual_tool_return']==final and final['exit_code']==0,'actual_tool_numeric_exit0')
if 'session_id' in t['initial']:
 sid=t['initial']['session_id']
 check(len(t['polls'])==len(t['poll_invocations'])>0 and t['polls'][-1]==t['completion']==final,'actual_same_session_completion')
 for args in t['poll_invocations']:check(args['session_id']==sid and args.get('chars','')=='' and 0<args['yield_time_ms']<=60000,'bounded_same_session_poll')
else:check(t['initial']==final and not t['polls'],'direct_actual_completion')
check(t['independent_stdout'] is None and t['independent_stderr'] is None,'no_fabricated_independent_streams')
check(len(final['output'].encode())<=6000 and 'truncated output' not in final['output'],'uncapped_bounded_actual_summary')
display=json.loads(final['output'])
check(display['result']==FROZEN['result'] and all(display[k]==r[k] for k in ['child_exit','wrapper_exit','timed_out','output_limited','capture_integrity_complete','behavior_accepted']),'actual_summary_result_join')
cleanup=r['cleanup']
check(cleanup['leader_reaped'] is True and cleanup['group_remaining'] is False and cleanup['cleanup_errors']==[] and cleanup['cleanup_seconds_bound']==15,'owned_group_cleanup')
inv=doc(pin(RUN/'invocation.json'))
check(inv['command']==res['command'] and inv['argv']==res['command']['child_argv'] and inv['actual_environment']==res['command']['child_env'] and inv['exact_tool_arguments']==t['invocation'] and inv['shell'] is False and inv['start_new_session'] is True and inv['stdin']=='DEVNULL','actual_child_argv_env_process')
for row in r['streams'].values():checked(row)
check(all(row['bytes']<=33554432 for row in r['streams'].values()) and r['faulthandler_raw_markers']['timeout_text_marker'] is False and r['faulthandler_raw_markers']['thread_text_marker'] is False,'raw_streams_no_timeout')
xml=ET.fromstring(checked(r['JUnit']['pin']));xml_cases=list(xml.iter('testcase'))
check(len(xml_cases)==1 and len(list(xml.iter('failure')))==1 and not list(xml.iter('error')) and not list(xml.iter('skipped')),'actual_one_JUnit_FAIL_diagnostic_only')
check(xml_cases[0].attrib['classname'].replace('.','/')+'.py::'+xml_cases[0].attrib['name']==res['command']['node'],'exact_selected_JUnit_node')
before=doc(r['before']);after=doc(r['after'])
check(before['authority_before']==after and len(before['sources'])==27 and len(after['protected'])==211 and after['history_reaudited_as_current'] is False,'full_before_after_authority')
for row in before['sources']:
 raw=checked(row);check(raw==checked(row['physical'])==base64.b64decode(row['base64'],validate=True) and Path(row['path']).stat().st_mode==row['mode'],'current27_full_source_bytes_mode')
for row in after['protected']+SG['fixed_inputs']+list(SG['sources'].values()):checked(row)
resource=doc(r['resources'])
check(resource['all_records_valid'] is True and resource['complete_sidecar_set'] is True and resource['validation_errors']==[] and len(resource['records'])==1 and resource['actual_node_counts']=={res['command']['node']:1},'one_actual_complete_sidecar')
counts=Counter();markers=[];observed_peak=0
for row in resource['records']:
 data=doc(row['pin'])
 check(data==row['data'] and row['error'] is None and data['pid']==r['pid'] and data['nodeid']==res['command']['node'] and data['schema_version']=='bigsmall.r158-t2-resource.v1' and data['command_id']=='t2_green','raw_sidecar_provenance')
 obs=data['observations'];check(data['entered_contract_guard'] is True and data['entered_behavior'] is True and obs['observers_restored'] is True and obs['method_restoration'] is True and data['cleanup_errors']==[],'nested_completion_and_restoration')
 markers.append({'top_level_present':'assertions_completed' in data,'top_level_value':data.get('assertions_completed'),'nested_present':'assertions_completed' in obs,'nested_type':type(obs.get('assertions_completed')).__name__,'nested_value':obs.get('assertions_completed')})
 objects=data['resources'];polls=data['worker_lifecycles'];by_id={q['resource_id']:q for q in objects}
 check(len(by_id)==len(objects)==data['allocation_attempts'] and len(polls)==1,'actual_object_denominator_two_polls')
 intervals=[];sequences=set()
 for ordinal,poll in enumerate(polls,1):
  worker=by_id[poll['worker_resource_id']]
  check(poll['poll_id']==ordinal and worker['kind']=='worker' and ordinal in worker['poll_ids'] and poll['attempted'] is True and poll['entered'] is True and poll['returned_normally'] is True and type(poll['return_value']) is bool and poll['exception'] is None,'normal_poll_ownership')
  start,entry,end=(poll[k] for k in ['start_sequence','entry_sequence','end_sequence'])
  check(all(type(q) is int for q in [start,entry,end,poll['thread_id'],poll['native_thread_id']]) and 0<start<entry<end and not (set([start,entry,end])&sequences),'actual_poll_sequence_threads')
  sequences.update([start,entry,end]);intervals.extend([(entry,1),(end,-1)])
  for key in ['attempted_poll_lifecycles','entered_poll_lifecycles','normally_returned_poll_lifecycles']:counts[key]+=1
 active=peak=0
 for _,delta in sorted(intervals):active+=delta;check(active>=0,'poll_intervals_nonnegative');peak=max(peak,active)
 check(active==0 and peak<=2,'poll_concurrency_cap');observed_peak=max(observed_peak,peak)
 counts['allocation_attempts']+=len(objects)
 for obj in objects:
  check(type(obj['resource_id']) is int and obj['resource_id']>0 and obj['pid']==r['pid'] and obj['initialization_attempted'] is True and type(obj['initialized']) is bool and obj['cleanup_observed'] is True,'actual_resource_attempt_cleanup')
  counts['initialized']+=int(obj['initialized']);counts['kind:'+obj['kind']]+=1;counts['cleanup_observed']+=1
  if obj['kind']=='worker':
   counts['constructed_worker_attempts']+=1;counts['initialized_workers']+=int(obj['initialized'])
   actual_ids=[p['poll_id'] for p in polls if p['worker_resource_id']==obj['resource_id']]
   check(obj['poll_ids']==actual_ids and obj['final_active_job_id']=='','actual_worker_poll_and_idle')
   sessions=obj['session_resource_ids'];check(len(set(sessions))==len(sessions),'unique_worker_sessions')
   for session_id in sessions:
    session=by_id[session_id];check(session['kind']=='lease_session' and session['worker_resource_id']==obj['resource_id'] and session['broker_alive'] is False and session['cleanup_observed'] is True,'actual_worker_session_released')
   for field,kind,peakfield in [('broker_resource_ids','broker_thread','broker_peak_alive'),('heartbeat_resource_ids','heartbeat_thread','heartbeat_peak_alive')]:
    ids=obj[field];check(len(set(ids))==len(ids) and type(obj[peakfield]) is int and 0<=obj[peakfield]<=1,'worker_thread_count_cap')
    for rid in ids:
     thread=by_id[rid];check(thread['kind']==kind and thread['worker_resource_id']==obj['resource_id'] and thread['session_resource_id'] in sessions and thread['alive_after_join'] is False and thread['cleanup_observed'] is True and type(thread['thread_ident']) is type(thread['native_thread_id']) is int,'thread_owner_and_join')
   check(type(obj['session_observed']) is type(obj['heartbeat_observed']) is bool and obj['session_observed']==bool(sessions) and obj['heartbeat_observed']==bool(obj['heartbeat_resource_ids']),'worker_presence_links')
   if not actual_ids:
    counts['never_polled_workers']+=1
    check(obj['cleanup_basis']=='never_polled_no_owned_runtime' and obj['initial_active_job_id']=='' and not sessions and not obj['broker_resource_ids'] and not obj['heartbeat_resource_ids'] and obj['close_attempts']==[],'unpolled_worker_no_invented_runtime')
   else:check(obj['cleanup_basis']=='poll_finished_runtime_released','polled_worker_cleanup_basis')
  if obj['kind'] in ['broker_thread','heartbeat_thread']:
   owner=by_id[obj['worker_resource_id']];field='broker_resource_ids' if obj['kind']=='broker_thread' else 'heartbeat_resource_ids'
   check(owner['kind']=='worker' and obj['resource_id'] in owner[field],'thread_reverse_owner')
  if obj['kind']=='helper_thread':check(obj['alive_after_join'] is False,'helper_thread_join')
check(dict(counts)==resource['counts'] and resource['whole_run_allocation_denominator']==counts['allocation_attempts'] and resource['peak_active_polls_per_node']==observed_peak,'independent_actual_resource_counts')
check(r['completion_marker_assessment']['eligible'] is False,'failed_body_no_behavior_completion')
check(r['passive'] is not None and r['diagnostic_complete'] is False,'partial_diagnostic_original_status')
prereq=doc(r['prerequisite']['pin']);check(r['prerequisite']['accepted'] is True and prereq['accepted_prerequisite'] is True and prereq['pid']==r['pid'],'actual_startup_prerequisite')
cases=doc(r['cases']);index=doc(r['index'])
check(cases['expected_node']==res['command']['node'] and cases['whole_run_resource_completeness'] is True and index['round']=='R289' and index['command_id']==name and index['SQL_executed'] is False and index['old_missing_recovered'] is False,'cases_index_provenance')
for row in cases['scenario_files']:
 check(checked(row['pin'])==base64.b64decode(row['base64'],validate=True),'actual_scenario_whole_bytes')
 if row['actual_owner'] is not None:check(row['actual_owner']=={'nodeid':res['command']['node'],'pid':r['pid']},'scenario_actual_owner')
paths={row['path']:row for row in index['records']};root=Path(index['root'])
check(len(paths)==len(index['records']) and root==RUN/'persistent-basetemp' and root.is_dir() and not root.is_symlink(),'persistent_nofollow_index')
for path,row in paths.items():
 p=Path(path);info=p.lstat();check(info.st_mode==row['mode'] and info.st_size==row['bytes'] and info.st_ino==row['inode'],'persistent_actual_lstat')
 if stat.S_ISREG(info.st_mode):check(row['symlink'] is False and pin(p)==identity(row),'regular_own_file_hash')
 elif stat.S_ISDIR(info.st_mode):check(row['symlink'] is False and 'sha256' not in row,'directory_no_hash')
 elif stat.S_ISLNK(info.st_mode):
  target=os.readlink(p);check(row['symlink'] is True and row['link_target']==target and 'sha256' not in row,'symlink_own_text')
  destination=Path(os.path.abspath(os.path.join(str(p.parent),target)))
  check(destination.is_relative_to(root) and str(destination) in paths and paths[str(destination)]['symlink'] is False,'exact_contained_symlink_target')
 else:check(False,'unexpected_special_persistent_file')
check(r['new_retained_databases']==index['new_retained_databases'],'new_DB_result_index_exact')
def pairs(rows):
 for row in rows:
  check(checked(row['pin'])==checked(row['archive']) and len(row['sidecars'])==3,'DB_original_archive_three_sides')
  for side in row['sidecars']:
   check(side['is_symlink'] is False,'sidecar_not_symlink')
   if side['exists']:check(checked(side['pin'])==checked(side['archive']),'present_sidecar_full')
   else:check(side['pin'] is None,'absent_sidecar_null');absent(side['path'])
pairs(r['new_retained_databases'])
for group in [after['R258_retained_DB_pairs'],*after['R268_R276_retained_DB_pairs'].values(),after['R285_retained_DB_pairs']]:pairs(group)
for group in after['old_retained_groups'].values():
 for row in group:
  checked(row['pin'])
  for side in row['sidecars']:check(side['exists'] is False and side['pin'] is None,'old30_sidecar_absent');absent(side['path'])
check(len(after['missing_registry35'])==35 and len(after['old_absent_sidecars90'])==90,'old_loss_bounds')
for row in after['missing_registry35']:check(all(row[k] is None for k in ['current_bytes','current_sha256','hash_match']),'old_loss_null');absent(row['original']['path'])
for row in after['old_absent_sidecars90']:absent(row['path'])
prior_selected=doc(res['prior_runs_supplement'])
check(prior_selected['round']=='R289' and prior_selected['command_id']==name and prior_selected['plan']==res['plan'] and prior_selected['observation']==SG['observation'] and [q['command_id'] for q in prior_selected['prior_receipts']]==['wait_memory','wait_sqlite'],'one_exact_preceding_memory_receipt')
for prior_row in prior_selected['prior_receipts']:
 check(set(prior_row)=={'command_id','acceptance','result','actual_tool_return','persistent_index','new_retained_databases'},'finite_prior_receipt_six_fields')
 accepted=doc(prior_row['acceptance']);previous=doc(prior_row['result']);previous_tool=doc(prior_row['actual_tool_return']);previous_index=doc(prior_row['persistent_index'])
 check(accepted['round']=='R289' and accepted['command_id']==prior_row['command_id'] and accepted['status']=='VERIFIED_COMPLETE_BEHAVIOR_CAPTURE' and accepted['next_command_release']=={'status':'NEXT_INDEPENDENT_COMMAND_ALLOWED','next_key':'wait_sqlite' if prior_row['command_id']=='wait_memory' else name},'preceding_memory_own_next_release_preserved')
 for field in ['result','actual_tool_return','persistent_index','new_retained_databases']:check(prior_row[field]==accepted[field],'prior_receipt_exact_join:'+field)
 check(previous['child_exit']==previous['wrapper_exit']==previous_tool['final']['exit_code']==0 and previous['behavior_accepted'] is True and previous['capture_integrity_complete'] is True and previous['timed_out'] is False and previous['new_retained_databases']==previous_index['new_retained_databases']==prior_row['new_retained_databases'],'prior_actual_complete_memory_result')
 pairs(prior_row['new_retained_databases'])
passive=r['passive'];raw_events={};total=0
check(len(passive['records'])==2,'two_actual_passive_files')
for record in passive['records']:
 raw=checked(record['pin']);value=json.loads(raw);check(value==record['data'],'passive_raw_matches_result')
 check(value['round']=='R289' and value['command_id']==name and value['nodeid']==res['command']['node'] and value['pid']==r['pid'],'passive_actual_node_PID')
 for source in value['sources'].values():checked(source)
 total+=len(raw);raw_events[Path(record['pin']['path']).name]=value
event=raw_events['events.json'];summary=raw_events['summary.json'];events=event['records']
check(total==passive['total_utf8_bytes']==37420 and total<=131072,'actual_two_file_bytes_bound')
check(event['events_count']==len(events)==7 and event['dropped_events']==summary['dropped_events']==passive['dropped_events']==10 and event['cap_hit'] is summary['cap_hit'] is passive['cap_hit'] is True,'original_cap_drop_preserved')
check(event['drops_by_reason']=={'reserved_128KiB_budget':10} and event['incomplete'] is summary['incomplete'] is True and passive['complete'] is False,'incomplete_remains_incomplete')
check(summary['hooks_before']==summary['hooks_after']==[None,None,None,None] and summary['hooks_equal'] is True and summary['call_finally_observed'] is True and summary['normal_sessionfinish_observed'] is True and summary['new_threads_still_live']==[] and summary['observer_errors']==[],'actual_hook_thread_restoration')
check(summary['summary_handle_close_observation'] is None and summary['own_handles'][-1]['closed_observed'] is None,'unobserved_last_close_remains_null')
resource_objects={q['resource_id']:q for row in resource['records'] for q in row['data']['resources']}
threads={(q['thread_ident'],q['native_thread_id']) for q in resource_objects.values() if q['kind'] in ['broker_thread','heartbeat_thread']}
threads.update((q['thread_id'],q['native_thread_id']) for row in resource['records'] for q in row['data']['worker_lifecycles'] if q['entered'])
targets={('__init__',417):{'call','line455','return'},('invalidate',640):{'call'},('_check_ingress',468):{'line471','exception'},('_close_worker_lease_session',982):{'call','line987','return'}}
seen={};first={};invalidations=[]
for ordinal,row in enumerate(events):
 check(row['ordinal']==ordinal and row['pid']==r['pid'] and len(row['stack']['locations'])<=12,'actual_event_ordinal_pid_stack')
 category='line'+str(row['trace_lineno']) if row['trace_event']=='line' else row['trace_event']
 check((row['code_name'],row['code_firstlineno']) in targets and category in targets[(row['code_name'],row['code_firstlineno'])] and row['category']==row['code_name']+':'+category,'original_exact_target_event')
 sid=row['snapshot']['session_id'];session_obj=resource_objects[sid]
 check(session_obj['kind']=='lease_session' and session_obj['worker_resource_id']==row['snapshot']['worker_object_id'] and (row['thread_id'],row['native_thread_id']) in threads,'event_real_resource_worker_thread_witness')
 seen[sid]=seen.get(sid,0)+1;first.setdefault(sid,{}).setdefault(row['category'],ordinal)
 check(seen[sid]<=64,'per_session_event_bound')
 if row['category']=='invalidate:call':invalidations.append({'ordinal':ordinal,'session_id':sid,'original_reason':row['original_reason'],'thread_id':row['thread_id'],'native_thread_id':row['native_thread_id'],'stack':row['stack']})
check(len(event['first_observed'])==1 and event['first_observed']==summary['first_observed'],'one_actual_session')
for session in event['first_observed']:
 sid=session['session_id'];check(session['event_count']==seen[sid] and session['first_observed']==first[sid],'first_observed_event_map_exact')
 ordinal=first[sid]['invalidate:call'];check(session['first_observed_invalidate']=={'ordinal':ordinal,'original_reason':events[ordinal]['original_reason']},'original_first_reason_not_overwritten')
check(invalidations[0]['ordinal']==3 and invalidations[0]['original_reason']=='RPC wait cap exceeded' and invalidations[1]['original_reason']=='late broker reply' and passive['unavailable_witnesses']==[],'limited_first_observed_RPC_then_late_reply')
check(passive['first_cause']=='UNKNOWN_REQUIRES_ROOT_EVENT_INTERPRETATION','full_root_cause_remains_unknown')
author_path=Path(res['author_role_before']['path']);author_record=next(q for q in res['role_before'] if q['original']['path']==str(author_path))
author_before=full(author_record);continuation={k:res[k] for k in ['reservation_id','plan','source_gate','script_gate','sources','command','prior_runs_supplement']}
expected_author=json.loads(author_before);entry=expected_author['commands'][name]
entry.update(state='RESERVED',used=1,remaining=0,reservation_id=res['reservation_id']);entry.setdefault('continuation',{})['R289']=continuation
reserved_author=encode(expected_author);entry.update(state='SPENT',result_path=str(RUN/'result.json'));spent_author=encode(expected_author)
check(pin(author_path,reserved_author)==identity(r['author_reserved']) and reserved_author==base64.b64decode(r['known_author_generations']['reserved']['base64'],validate=True) and author_before==base64.b64decode(r['known_author_generations']['before']['base64'],validate=True),'AUTHOR_full_before_reserved_identity')
check(checked(r['author_spent'])==spent_author==base64.b64decode(r['known_author_generations']['spent']['base64'],validate=True) and author_path.lstat().st_mode==author_record['mode'],'only_selected_AUTHOR_spent')
check(checked(pin(RUN/'before/author-reserved.json'))==reserved_author and checked(pin(RUN/'author-spent.json'))==spent_author,'AUTHOR_physical_reserved_spent')
for row in before['control_before']:
 raw=full(row)
 if row['original']['path']==str(author_path):check(raw==author_before,'snapshot_AUTHOR_exact_before')
 else:check(checked(row['original'])==raw,'snapshot_stable_control')
root_path=Path(res['root_role_after']['path']);root_raw=checked(res['root_role_after']);root_mode=root_path.lstat().st_mode;root=json.loads(root_raw)
check(root['commands'][name]['state']=='RESERVED_BY_ROOT' and root['commands'][name]['used']==1 and root['commands'][name]['remaining']==0,'ROOT_selected_reserved_once')
for row in res['role_before']:full(row)
check(context['round']=='R287' and context['T2_complete'] is False,'frozen_factual_context')
receipt_path=D/'root-dual-first-invalidation-independent-assessment.json'
settlement_path=D/'root-dual-first-invalidation-role-settlement.json'
for path in [receipt_path,settlement_path]:absent(path)
check(root_path.read_bytes()==root_raw and root_path.lstat().st_mode==root_mode and author_path.read_bytes()==spent_author and author_path.lstat().st_mode==author_record['mode'],'immediate_pre_receipt_roles')
receipt={'round':'R289','command_id':name,'status':'INDEPENDENT_PARTIAL_DIAGNOSTIC_CAPTURE_RECORDED_STOP_NEXT_ASTRA','result':FROZEN['result'],'actual_tool_return':FROZEN['actual_tool_return'],'persistent_index':r['index'],'new_retained_databases':r['new_retained_databases'],'checks_passed':len(checks),'checks':checks,'resource_counts':dict(counts),'completion_markers':markers,'child_exit':1,'wrapper_exit':0,'T2_complete':False,'native_accepted':False,'formal_accepted':False}
receipt.update(diagnostic_complete=False,behavior_accepted=False,capture_integrity_complete=True,first_observed_invalidations=invalidations,passive_pins=[q['pin'] for q in passive['records']],captured_events=7,dropped_events=10,full_first_cause='UNKNOWN_REQUIRES_ROOT_EVENT_INTERPRETATION',new_DB_count=len(r['new_retained_databases']))
receipt_pin=save(receipt_path,encode(receipt))
archive=save(D/'before/settlements/dual_first_invalidation/root-command-ledger.json',root_raw,root_mode)
root_before={'original':pin(root_path,root_raw),'archive':archive,'mode':root_mode,'base64':base64.b64encode(root_raw).decode()}
settled=copy.deepcopy(root);selected=settled['commands'][name]
selected.update(state='SPENT_PARTIAL_DIAGNOSTIC_CAPTURE',result_path=FROZEN['result']['path'],independent_acceptance=receipt_pin,next_command_release={'status':'STOP_NEXT_ASTRA_NO_FURTHER_RUNTIME','independent_acceptance':receipt_pin})
after_raw=encode(settled);after_archive=save(D/'root-settlements/dual_first_invalidation/ROOT-after.json',after_raw,root_mode)
check(root_path.read_bytes()==root_raw and root_path.lstat().st_mode==root_mode and author_path.read_bytes()==spent_author and author_path.lstat().st_mode==author_record['mode'],'immediate_role_bytes_mode_CAS')
fd=os.open(root_path,os.O_RDWR|os.O_NOFOLLOW)
with os.fdopen(fd,'r+b') as stream:
 check(os.fstat(stream.fileno()).st_mode==root_mode and stream.read()==root_raw and author_path.read_bytes()==spent_author,'descriptor_CAS')
 stream.seek(0);stream.write(after_raw);stream.truncate();stream.flush();os.fsync(stream.fileno())
check(root_path.read_bytes()==after_raw and root_path.lstat().st_mode==root_mode and author_path.read_bytes()==spent_author,'settled_role_readback')
settlement=save(settlement_path,encode({'round':'R289','command_id':name,'status':'ROOT_SELECTED_DUAL_SPENT_PARTIAL_DIAGNOSTIC_RECORDED','independent_acceptance':receipt_pin,'root_before':root_before,'root_after':pin(root_path),'after_archive':after_archive,'author_unchanged':r['author_spent'],'runtime':0}))
output=json.dumps({'status':receipt['status'],'acceptance':receipt_pin,'resource_counts':dict(counts),'root_settlement':settlement,'next_runtime_dispatched':False,'T2_complete':False},ensure_ascii=False)
check(len((output+'\n').encode())<=6000,'console6000')
print(output);signal.alarm(0)
