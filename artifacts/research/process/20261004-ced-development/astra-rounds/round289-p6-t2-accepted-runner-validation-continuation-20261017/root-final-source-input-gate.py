"""ROOT R289 final ordinary metadata gate; no delivered code is imported or executed."""
from pathlib import Path
import base64,difflib,hashlib,json,shlex,signal,stat,time
R=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D=R/'artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017'
A=D.parent;I=D/'implementation'
F=A/'round293-p6-t2-final-source-proof-length-disposition-20261017'
B=A/'round285-p6-t2-new-test-generation-validation-continuation-20261017'
C=A/'round276-p6-t2-first-session-invalidation-capture-20261017'
G=A/'round281-p6-t2-post-expiry-session-denial-assertion-20261017'
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('ROOT R289 ordinary metadata total120s')
signal.signal(signal.SIGALRM,expired);signal.alarm(120)
checks=[];fixed_inputs={};historical={}
def check(ok,label):
 if time.monotonic()>=deadline:expired()
 assert ok,label
 checks.append(label)
def identity(row):return {k:row[k] for k in ('path','bytes','sha256')}
def pin(path,raw=None):
 path=Path(path)
 if raw is None:
  check(stat.S_ISREG(path.lstat().st_mode),'regular:'+str(path));raw=path.read_bytes()
 return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def checked(row):
 q=identity(row);p=Path(q['path']);b=p.read_bytes()
 check(stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==q,'exact:'+str(p))
 check(str(p) not in fixed_inputs or fixed_inputs[str(p)]==q,'one_current_identity:'+str(p))
 fixed_inputs[str(p)]=q;return b
def fixed(path,size,sha):return checked({'path':str(path),'bytes':size,'sha256':sha})
def doc(row):return json.loads(checked(row))
def load(path):return json.loads(Path(path).read_bytes())
def absence(path):check(not Path(path).exists() and not Path(path).is_symlink(),'absent:'+str(path))
def full(row,current=False):
 raw=base64.b64decode(row['base64'],validate=True);q=identity(row['original'])
 check(pin(q['path'],raw)==q and checked(row['archive'])==raw,'full_physical_base64:'+q['path'])
 if 'mode' in row:
  check(Path(row['archive']['path']).lstat().st_mode==row['mode'],'archive_mode:'+q['path'])
  if current:check(Path(q['path']).lstat().st_mode==row['mode'],'current_mode:'+q['path'])
 if current:check(checked(q)==raw,'current_full:'+q['path'])
 historical[(q['path'],q['bytes'],q['sha256'])]=raw
 return raw
def write(path,value):
 with Path(path).open('xb') as stream:stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
 return pin(path)
candidate_pin={'path':str(D/'root-candidate-source-native-acceptance.json'),'bytes':358041,'sha256':'bada18ada634de18d7a0011880644a602b377bc8937b81e5d52fb98c88cc81b1'}
candidate=doc(candidate_pin)
check(candidate['checks_passed']==1341 and candidate['runtime']==0,'prior_full_source1341')
for row in candidate['fixed_inputs']:checked(row)
fixed(D/'plan.json',48642,'4bc64ed58a737cb9f6bbe7386a9937a189b3e1522258e8a85c051bbd8f5fe5fb')
fixed(D/'input-observation.json',371055,'82c31139a709e11ca78fefaae3bc8df9cda1612a0584e2c391a527b9b1501cf3')
fixed(D/'prerequisite-supplement.json',6492,'fc267162c6ad812a056191eef27c727ae2009248c2034c58baeae53562fdfd19')
P=load(D/'plan.json');O=load(D/'input-observation.json');S=load(D/'prerequisite-supplement.json')
check(P['actual_model']=='gpt-6-astra' and len(P['inputs'])==32 and P['inputs']==O['inputs'],'actual_Astra_finite32')
check(S['input_count']==len(S['inputs'])==8 and S['plan']==pin(D/'plan.json') and S['observation']==pin(D/'input-observation.json'),'supplement8')
for row in P['inputs']+S['inputs']:checked(row)
for row in doc(P['before_manifest'])['records']:full(row,True)
fixed(I/'limited.diff',54303,'d0dbfa28d8bfa1887f094e205ee96ed8551f2b47d7a05c8cb2240cad8afe1492')
fixed(I/'final-source-scope-proof.json',18558,'c0390d4722afbfc2b3312a327aab91d4325789a77115ef8588694fe991ba6f6d')
fixed(I/'source-index.json',27261165,'f93bc4bebad91d0ddb4b07975d4dbf422074003cd93f609575ab7da351730b9f')
fixed(I/'change-report.json',142269,'6ef7f7df268fa129406a2afabe978f3fce13434df933f01a0407ac62eaf41426')
Q=load(I/'final-source-scope-proof.json');X=load(I/'source-index.json');V=load(I/'change-report.json')
meta_gate=doc({'path':str(F/'root-metadata-source-native-acceptance.json'),'bytes':41948,'sha256':'1b92b8d3f072052b7a1eb6384d9b24fef84bfeea988300df1368fc218af3ba31'})
for row in meta_gate['inputs']:checked(row)
for key in ['plan','observation','before_manifest','source','candidate','native','limited_diff','scope']:checked(meta_gate[key])
meta_plan=doc(meta_gate['plan'])
for row in doc(meta_gate['before_manifest'])['records']:full(row,True)
actual_path=F/'implementation/actual-tool-return.json';actual_pin=pin(actual_path);actual=doc(actual_pin)
step_path=F/'implementation/step-report.json';step=doc(pin(step_path))
check(actual['invocation']==step['invocation']==meta_plan['execution']['tool_arguments'],'R293_literal_actual')
check(actual['initial']==actual['final']==actual['actual_tool_return']==step['actual_tool_return'] and actual['final']['chunk_id']=='4e6b8c' and actual['final']['exit_code']==0,'R293_new_metadata_exit0')
check(actual['polls']==actual['poll_invocations']==[] and actual['completion'] is None and actual['attempt']==1 and actual['retry']==0,'R293_once_no_replay')
check(actual['independent_stdout'] is None and actual['independent_stderr'] is None and step['original_702f9d_remains_failed'] is True,'R293_truthful_streams_original_failure')
check(step['runtime']==0 and step['T2_complete'] is False and step['roles_context_modified'] is False,'metadata_only')
for row in step['outputs'].values():checked(row)
recovery=Q['recovery_provenance']
check(recovery==X['recovery_provenance']==V['recovery_provenance'] and recovery['round']=='R293' and recovery['metadata_only'] is True and recovery['runtime_executed'] is False,'three_additive_recovery_records')
for key in ['metadata_source','plan','observation','original_failure']:checked(recovery[key])
failure=doc(recovery['original_failure'])
check(recovery['original_actual']==failure['actual_tool_return'] and recovery['original_actual']['chunk_id']=='702f9d' and recovery['original_actual']['exit_code']==1 and recovery['original_failure_remains_failed'] is True,'702f9d_unmodified_failed')
native=doc(V['native_pin'])
check(V['native']==native and X['native']==Q['native']==V['native_pin'] and len(native['stages'])==2,'native_object_distinct_identity')
check(len(X['sources'])==len(V['sources'])==len(Q['sources'])==2 and X['target_before']==Q['target_before']==[None,None],'actual_Add_contract')
source_bytes=[];sources={}
for key,row,report,stage in zip(['runner','plugin'],X['sources'],V['sources'],native['stages']):
 raw=checked(row);check(raw==checked(row['candidate'])==checked(row['physical'])==base64.b64decode(row['base64'],validate=True),'source_candidate_after_base64:'+key)
 check(Path(row['path']).stat().st_mode==Path(row['candidate']['path']).stat().st_mode==Path(row['physical']['path']).stat().st_mode==row['mode']==33204,'source_modes:'+key)
 check(report=={'pin':identity(row),'candidate':row['candidate'],'physical':row['physical'],'mode':row['mode'],'lines':len(raw.splitlines())} and row['source_lines']==report['lines'],'source_report_schema:'+key)
 lines=stage['arguments'].splitlines(keepends=True)
 check(lines[0]=='*** Begin Patch\n' and lines[1]=='*** Add File: '+row['path']+'\n' and lines[-1]=='*** End Patch' and all(line.startswith('+') for line in lines[2:-1]),'exact_native_frame:'+key)
 check(''.join(line[1:] for line in lines[2:-1]).encode()==raw and stage['tool']=='tools.apply_patch' and stage['actual_tool_return']=={} and all(stage[k] is None for k in ['numeric_exit','independent_stdout','independent_stderr','target_before']),'native_whole_actual_nulls:'+key)
 source_bytes.append(raw);sources[key]=identity(row)
check(Q['sources']==list(sources.values()) and V['ROOT_candidate_acceptance']==X['ROOT_candidate_acceptance']==Q['ROOT_candidate_acceptance']==candidate_pin,'full_candidate_to_actual_join')
old=checked(P['source_generation']['accepted_runner']);old_plugin=checked(P['source_generation']['plugin_template'])
p285=load(B/'plan.json')
expected_ids=[[B.name,D.name],[pin(B/'plan.json')['sha256'],pin(D/'plan.json')['sha256']],[pin(B/'input-observation.json')['sha256'],pin(D/'input-observation.json')['sha256']],[pin(B/'prerequisite-supplement.json')['sha256'],pin(D/'prerequisite-supplement.json')['sha256']],['r285_session_evidence','r289_session_evidence'],['bigsmall.r285.','bigsmall.r289.'],['R285','R289'],['.r258-next','.r289-next']]
check(Q['identity_changes']==expected_ids,'only_eight_explicit_identity_transforms')
def ns(data):
 for before,after in expected_ids:data=data.replace(before.encode(),after.encode())
 return data
new,plugin=source_bytes
check(plugin==ns(old_plugin),'plugin_whole_identity_only')
oldbounds=[0,5352,23031,30442,43552,50861,52089,55166,64269,67012,86520]
newbounds=[0,5348,23027,30438,52259,60800,62028,65105,74217,76960,96468]
check(len(Q['runner_portions'])==10 and X['runner_portions']==Q['runner_portions'],'complete_ten_portions')
cc=checked(pin(I/'prepared-run-evidence-source.txt'))
p291=load(A/'round291-p6-t2-dual-lease-source-selector-binding-20261017/plan.json')
p292=load(A/'round292-p6-t2-role-envelope-source-binding-20261017/plan.json')
for i,portion in enumerate(Q['runner_portions']):
 before=old[oldbounds[i]:oldbounds[i+1]];after=new[newbounds[i]:newbounds[i+1]]
 for field,data,bounds in [('before',before,oldbounds),('after',after,newbounds)]:
  check(portion[field]=={'start_byte':bounds[i],'end_byte':bounds[i+1],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},'portion_coordinates:'+str(i)+field)
 expected=before if i in [1,8] else ns(before)
 if i==3:
  fragment=cc[cc.index(b'def verify_prior_runs(context):'):cc.index(b'def preconditions():')];edit=p292['scope']['exact_change']
  check(fragment.count(edit['old'].encode())==1,'R292_unique_role_envelope')
  expected=fragment.replace(edit['old'].encode(),edit['new'].encode(),1)
 if i==4:expected=cc[cc.index(b'def preconditions():'):cc.index(b'def save_before(context):')]
 if i==7:
  edit=p291['scope']['exact_change'];check(expected.count(edit['old'].encode())==1,'R291_unique_lease_selector')
  expected=expected.replace(edit['old'].encode(),edit['new'].encode(),1)
 check(after==expected and portion['exact_expected_bytes'] is True,'independent_expected_region:'+str(i))
check(b''.join(new[newbounds[i]:newbounds[i+1]] for i in range(10))==new and Q['ten_new_regions_join_whole'] is True,'independent_ten_join_whole')
helper=old[5352:23031]
check(helper==new[5348:23027] and len(helper)==Q['four_original_helper_bytes']==17679 and hashlib.sha256(helper).hexdigest()==Q['helper_slice']['sha256']=='8ef88c6906820c7a82a7c3bddfc2e60dc8335b4c8c3919228aa7938bf37b5af6','whole_helper17679')
expected_diff=(''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile=P['source_generation']['accepted_runner']['path'],tofile=sources['runner']['path']))+''.join(difflib.unified_diff(old_plugin.decode().splitlines(True),plugin.decode().splitlines(True),fromfile=P['source_generation']['plugin_template']['path'],tofile=sources['plugin']['path']))).encode()
check(checked(V['limited_diff'])==expected_diff,'complete_diff_exact')
check(X['input_records']==[{'pin':identity(r),'resolution':'CURRENT_EXACT'} for r in P['inputs']+S['inputs']] and V['input_count']==40,'preserved32_plus8_schema')
container=doc(P['authority_contract']['container']);prior=container['authority_before']
check(len(container['sources'])==27 and len(prior['protected'])==211 and len(prior['accepted_history_generations'])==68,'finite27_211_history68')
check(X['current_sources']==O['current_sources'] and X['protected']==prior['protected'] and X['accepted_history_generations']==prior['accepted_history_generations'] and X['history_reaudited_as_current'] is False,'typed_current_history_separation')
for row in container['sources']:
 check(checked(row)==checked(row['physical'])==base64.b64decode(row['base64'],validate=True) and Path(row['path']).stat().st_mode==row['mode'],'current_source_full:'+row['path'])
for row in prior['protected']:checked(row)
check([identity(r) for r in container['sources']]==[identity(r) for r in O['current_sources']],'current27_order')
earlier=load(B/'root-context-update.json');context=doc(S['context_manifest'])
check(context['round']=='R287' and context['T2_complete'] is False and len(context['changes'])==len(earlier['changes'])==2,'context_two_exact_transitions')
for row in context['changes']:
 path=row['before']['original']['path'];first=[q for q in earlier['changes'] if q['after']['path']==path]
 check(len(first)==1,'context_unique:'+path);first=first[0]
 full(first['before']);middle=full(row['before'])
 check(checked(first['after_archive'])==middle and identity(first['after'])==identity(row['before']['original']),'context_middle_physical:'+path)
 check(checked(row['after'])==checked(row['after_archive']) and Path(path).stat().st_mode==row['mode'],'context_current_after:'+path)
 for record in prior['input_records']:
  if record['pin']['path']==path:check(identity(record['pin'])==identity(first['before']['original']),'old_context_exact_pin:'+path)
for row in prior['input_records']:
 q=identity(row['pin']);key=(q['path'],q['bytes'],q['sha256'])
 if key in historical:check(pin(q['path'],historical[key])==q,'explicit_historical_input:'+q['path'])
 else:checked(q)
generation=load(G/'implementation/generation-manifest.json');ebf_manifest=load(G/'before/manifest.json')
ebf=full(ebf_manifest);ed602=full(prior['test_generation']['ed602']['before'])
check(checked(prior['test_generation']['ed602']['after'])==ebf and checked(generation['old']['archive'])==ebf and identity(generation['old']['original'])==identity(ebf_manifest['original']),'ed602_ebf1_generations')
check(full(generation['after'],True)==checked(P['source_generation']['current_test']),'current193f_generation')
r274=load(A/'round274-p6-t2-wait-fixture-clock-scope-20261017/plan.json');expected=ed602
for edit in r274['exact_source_change']['changes']:
 check(expected.count(edit['old'].encode())==1,'unique_R274_edit');expected=expected.replace(edit['old'].encode(),edit['new'].encode(),1)
check(expected==ebf,'R274_accepted_byte_transition')
check(len(prior['missing_registry35'])==35 and len(prior['old_absent_sidecars90'])==90,'missing35_absent90_bounds')
for row in prior['missing_registry35']:
 check(row['disposition']=='HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245' and all(row[k] is None for k in ['current_bytes','current_sha256','hash_match']),'missing_remains_null');absence(row['original']['path'])
for row in prior['old_absent_sidecars90']:
 check(row['exists'] is False and row['is_symlink'] is False,'old_absent_sidecar');absence(row['path'])
groups={key:prior['old_retained_groups'][key] for key in ['R242_R248','R251']}
groups['R258']=prior['R258_retained_DB_pairs'];groups.update(prior['R268_R276_retained_DB_pairs'])
old_index=load(B/'implementation/wait_memory/persistent-file-database-index.json')
groups['R285_wait_memory']=old_index['new_retained_databases']
observed={}
for row in O['known_database_records']:observed.setdefault(row['group'],[]).append(row['record'])
expected_counts={'R242_R248':12,'R251':18,'R258':10,'wait_memory_failure':4,'dual_progress':2,'R276_wait_memory':4,'R285_wait_memory':4}
check(groups==observed and {k:len(v) for k,v in groups.items()}==expected_counts and sum(expected_counts.values())==54,'exact54_seven_DB_groups')
for key,rows in groups.items():
 present=absent=0
 for row in rows:
  raw=checked(row['pin'])
  if key not in ['R242_R248','R251']:check(raw==checked(row['archive']),'DB_original_archive:'+key)
  check(len(row['sidecars'])==3,'three_DB_sidecars:'+key)
  for side in row['sidecars']:
   check(side['is_symlink'] is False,'sidecar_not_symlink')
   if side['exists']:
    present+=1;check(checked(side['pin'])==checked(side['archive']),'present_sidecar_full')
   else:absent+=1;check(side['pin'] is None,'absent_sidecar_null');absence(side['path'])
 if key=='R258':check((present,absent)==(2,28),'R258_sidecar2_28')
 if key in ['R276_wait_memory','R285_wait_memory']:check((present,absent)==(0,12),'newer_sidecar0_12:'+key)
absence(B/'implementation/wait_memory/result.json')
old_result=load(C/'implementation/wait_memory/result.json')
check(groups['R276_wait_memory']==old_result['new_retained_databases'],'R276_result_DB_join')
settled276=load(C/'root-wait-memory-independent-acceptance.json');full(settled276['root_before'])
for row in prior['old_control_generations']+container['control_before']:full(row)
for role in ['ROOT','AUTHOR']:checked(prior['old_role_pins'][role])
known=old_result['known_author_generations']
for key in ['before','reserved','spent']:
 raw=base64.b64decode(known[key]['base64'],validate=True);check(pin(known[key]['pin']['path'],raw)==identity(known[key]['pin']),'R276_AUTHOR_generation:'+key)
 if key in ['reserved','spent']:
  path=C/'implementation/wait_memory'/('before/author-reserved.json' if key=='reserved' else 'author-spent.json')
  check(checked(pin(path))==raw,'R276_AUTHOR_physical:'+key)
settled=load(A/'round287-p6-t2-runner-completion-marker-contract-20261017/root-failure-settlement.json')
root_before=full(settled['root_before']);checked(settled['root_after']);checked(settled['author_unchanged'])
reservation=load(B/'root-reservations/wait_memory.json');invocation=load(B/'implementation/wait_memory/invocation.json')
check(reservation['role_before']==invocation['role_before'],'R285_actual_reservation_invocation_before')
for row in reservation['role_before']:full(row)
for role in ['ROOT','AUTHOR']:
 envelope=O['R285_role_pins'][role];check(set(envelope)=={'pin','commands'},'explicit_R285_envelope:'+role)
 value=doc(envelope['pin']);entry=value['commands']['wait_memory']
 check(entry['used']==1 and entry['remaining']==0 and entry['state'].startswith('SPENT'),'old_memory_spent:'+role)
 for key in ['wait_sqlite','dual_first_invalidation']:check(value['commands'][key]['used']==0 and value['commands'][key]['remaining']==1,'old_held_unchanged:'+role+key)
 check(identity(envelope['pin'])==identity(settled['root_after'] if role=='ROOT' else settled['author_unchanged']),'R285_current_settlement:'+role)
reserved_author=checked(pin(B/'implementation/wait_memory/before/author-reserved.json'))
spent_author=checked(pin(B/'implementation/wait_memory/author-spent.json'))
check(pin(settled['author_unchanged']['path'],spent_author)==identity(settled['author_unchanged']) and pin(invocation['author_reserved']['path'],reserved_author)==identity(invocation['author_reserved']),'R285_AUTHOR_reserved_spent_physical')
roles={k:P['runner_contract']['roles'][k] for k in ['ROOT','AUTHOR']}
for path in roles.values():absence(path)
KEYS=['wait_memory','wait_sqlite','dual_first_invalidation'];check(list(P['commands'])==KEYS,'three_serial_commands')
for key,command in P['commands'].items():
 absence(command['output_directory'])
 exact="env -i 'PATH=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin' LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 /usr/bin/timeout --signal=TERM --kill-after=15s 900s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '"+sources['runner']['path']+"' "+key
 check(command['tool_arguments']=={'cmd':exact,'workdir':str(R),'yield_time_ms':10000,'max_output_tokens':1800},'exact_literal_transport:'+key)
 check(shlex.split(exact)==['env','-i']+[k+'='+v for k,v in command['launcher_env'].items()]+['/usr/bin/timeout','--signal=TERM','--kill-after=15s','900s']+command['runner_argv'],'argv_fields_join:'+key)
 check(command['limits']=={'child_seconds':600,'cleanup_total_seconds':15,'TERM_grace_seconds':5,'outer_total_seconds':900,'outer_KILL_after_seconds':15,'faulthandler_seconds':540,'attempts':1,'retries':0,'raw_stream_threshold_bytes_each':33554432,'stream_monitor_interval_max_seconds':0.1,'console_utf8_max':6000},'resource_process_limits:'+key)
 check((command['authorized'],command['used'],command['remaining'])==(1,0,1) and [q for q in command['child_argv'] if '::' in q]==[command['node']],'unused_one_node:'+key)
 check(('r289_session_evidence' in command['child_argv'])==(key=='dual_first_invalidation'),'passive_only_dual:'+key)
prior_memory=doc({'path':str(D/'root-prior-run-supplements/wait_memory.json'),'bytes':717,'sha256':'b7ee019ffff9be2c4fec59066f71e35b718f90a4d26cc532e6533591f4551c08'})
check(prior_memory['prior_receipts']==[],'empty_prior_for_first_memory')
fixed(D/'root-create-and-reserve-roles.py',11007,'86733fa4992678334ab2ed21356b219c8e8d74d52e21d13a53a8ee1e46138353')
checked(pin(Path(__file__)))
outputs=[F/'root-finalization-acceptance.json',D/'root-final-input-check.json',D/'source-gate.json',D/'script-gate.json',D/'root-final-source-acceptance.json']
for path in outputs:absence(path)
metadata=write(outputs[0],{'round':'R293','status':'ROOT_METADATA_FINALIZATION_VERIFIED_ONLY','actual_tool_return':actual_pin,'outputs':step['outputs'],'original_failure_remains_failed':True,'whole_helper_bytes':17679,'all_ten_expected_regions_verified':True,'targets_after_native_unchanged':True,'runtime':0,'T2_complete':False})
checked(metadata)
input_check=write(outputs[1],{'round':'R289','status':'VERIFIED_FINITE_SOURCE_INPUTS_ONLY','checks_passed':len(checks),'checks':checks,'fixed_inputs':list(fixed_inputs.values()),'database_group_counts':expected_counts,'missing_registry_count':35,'old_absent_sidecars_count':90,'history_reaudited_as_current':False,'roles_created':False,'runtime':0})
SG={'round':'R289','status':'VERIFIED_SOURCE_ONLY','plan':pin(D/'plan.json'),'observation':pin(D/'input-observation.json'),'supplement':pin(D/'prerequisite-supplement.json'),'sources':sources,'input_check':input_check,'native':V['native_pin'],'context_manifest':S['context_manifest'],'fixed_inputs':list(fixed_inputs.values()),'candidate_acceptance':candidate_pin,'recovery_acceptance':metadata,'runtime':0,'T2_complete':False}
source_gate=write(outputs[2],SG)
script_gate=write(outputs[3],{'round':'R289','status':'VERIFIED_BY_ROOT','plan':SG['plan'],'source_gate':source_gate,'sources':sources,'commands':P['commands'],'role_files':roles,'reservation_directory':str(D/'root-reservations'),'runtime':0,'T2_complete':False})
acceptance=write(outputs[4],{'round':'R289','status':'FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH','source_gate':source_gate,'script_gate':script_gate,'input_check':input_check,'metadata_recovery_acceptance':metadata,'sources':sources,'role_helper':pin(D/'root-create-and-reserve-roles.py'),'checks_passed':len(checks),'roles_created':False,'runtime':0,'T2_complete':False})
display=json.dumps({'round':'R289','status':'FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH','checks_passed':len(checks),'acceptance':acceptance,'source_gate':source_gate,'script_gate':script_gate,'runtime':0},ensure_ascii=False)
check(len((display+'\n').encode())<=6000,'console6000')
print(display);signal.alarm(0)
