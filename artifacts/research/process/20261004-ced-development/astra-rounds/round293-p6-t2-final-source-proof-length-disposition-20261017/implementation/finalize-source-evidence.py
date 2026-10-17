from pathlib import Path
import json,hashlib,base64,difflib,time,signal
R=Path('/home/ningyd/文档/ChatGPT/BIGsmall');A=R/'artifacts/research/process/20261004-ced-development/astra-rounds';D=A/'round289-p6-t2-accepted-runner-validation-continuation-20261017';I=D/'implementation';J=A/'round291-p6-t2-dual-lease-source-selector-binding-20261017';K=A/'round292-p6-t2-role-envelope-source-binding-20261017'
F=A/'round293-p6-t2-final-source-proof-length-disposition-20261017'
_DEADLINE=time.monotonic()+120
def deadline_check():
 if time.monotonic()>=_DEADLINE:raise TimeoutError('R293 metadata total120s deadline')
def alarm_expired(signum,frame):
 raise TimeoutError('R293 metadata SIGALRM120')
signal.signal(signal.SIGALRM,alarm_expired)
signal.alarm(120)
def bounded_read(path):
 deadline_check();raw=Path(path).read_bytes();deadline_check();return raw
def read_json(path):return json.loads(bounded_read(path))
def pin(p):
 p=Path(p);b=bounded_read(p);return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def ident(r):return {k:r[k] for k in ('path','bytes','sha256')}
def checked(r):
 b=bounded_read(r['path']);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],r['path'];return b
def save(p,b,mode=None):
 deadline_check();assert str(Path(p)) in OUTPUT_PATHS
 with Path(p).open('xb') as f:f.write(b)
 deadline_check()
 if mode is not None:Path(p).chmod(mode & 0o7777)
 return pin(p)
def write(p,v):return save(p,(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
META_PLAN=read_json(F/'plan.json')
assert pin(F/'plan.json')['sha256']=='4fa2ad28c2fe2ae45d51106ab1f81474be750bf6c400444da8de27247b8ba17d'
META_OBS=read_json(META_PLAN['inputs']['complete_manifest']['path'])
checked(META_PLAN['inputs']['complete_manifest'])
assert META_PLAN['inputs']['selector']=='inputs' and len(META_OBS['inputs'])==META_PLAN['inputs']['count']==25
for rec in META_OBS['inputs']:checked(rec)
checked(META_PLAN['inputs']['before_manifest'])
META_BEFORE=read_json(META_PLAN['inputs']['before_manifest']['path'])
assert type(META_BEFORE['records']) is list and len(META_BEFORE['records'])==5
for rec in META_BEFORE['records']:
 raw=checked(rec['original']);assert raw==checked(rec['archive'])==base64.b64decode(rec['base64'],validate=True)
 assert Path(rec['original']['path']).stat().st_mode==Path(rec['archive']['path']).stat().st_mode==rec['mode']
OUTPUT_PATHS=META_PLAN['execution']['outputs']
assert OUTPUT_PATHS==[str(I/name) for name in ['limited.diff','final-source-scope-proof.json','source-index.json','change-report.json']]
for path in OUTPUT_PATHS:
 deadline_check();p=Path(path);assert not p.exists() and not p.is_symlink();deadline_check()
failed_pin=next(r for r in META_OBS['inputs'] if r['path']==str(I/'source-preparation-finalization-failure.json'))
failed=read_json(failed_pin['path']);original_command=failed['invocation']['cmd']
command_prefix="'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' - <<'PY'\n";command_suffix="\nPY"
assert original_command.startswith(command_prefix) and original_command.endswith(command_suffix) and not original_command.endswith('\n')
original_body=original_command[len(command_prefix):-len(command_suffix)]
assert command_prefix+original_body+command_suffix==original_command
assert failed['actual_tool_return']['chunk_id']=='702f9d' and failed['actual_tool_return']['exit_code']==1
recovery={'round':'R293','metadata_source':pin(Path(__file__)),'plan':pin(F/'plan.json'),'observation':pin(F/'input-observation.json'),'original_failure':failed_pin,'original_actual':failed['actual_tool_return'],'original_failure_remains_failed':True,'command_extraction':{'prefix':command_prefix,'suffix':command_suffix,'terminal_LF':False,'body_bytes':len(original_body.encode()),'body_sha256':hashlib.sha256(original_body.encode()).hexdigest(),'exact_reconstruction':True},'metadata_only':True,'runtime_executed':False}
P=read_json(D/'plan.json');O=read_json(D/'input-observation.json');S=read_json(D/'prerequisite-supplement.json');M=read_json(D/'before/manifest.json');N=read_json(I/'actual-native-tool-returns.json')
input_records=[]
for r in P['inputs']+S['inputs']:
 checked(r);input_records.append({'pin':ident(r),'resolution':'CURRENT_EXACT'})
template_pins=[P['source_generation']['accepted_runner'],P['source_generation']['plugin_template']];template_rows=[]
for p in template_pins:
 rows=[r for r in M['records'] if r['original']['path']==p['path']];assert len(rows)==1;r=rows[0];b=checked(p);assert b==checked(r['archive'])==base64.b64decode(r['base64'],validate=True);assert Path(p['path']).stat().st_mode==Path(r['archive']['path']).stat().st_mode==r['mode'];template_rows.append(r)
targets=[I/'run-evidence.py',I/'r289_session_evidence.py'];candidates=[K/'implementation/prepared-run-evidence-source.txt',I/'prepared-session-evidence-source.txt'];source_rows=[];report_sources=[]
for target,candidate,stage,archive_name in zip(targets,candidates,N['stages'],['after-run-evidence.py','after-r289_session_evidence.py']):
 b=bounded_read(target);assert b==bounded_read(candidate) and target.stat().st_mode==candidate.stat().st_mode==33204
 args=stage['arguments'];lines=args.splitlines(keepends=True);assert lines[0]=='*** Begin Patch\n' and lines[1]=='*** Add File: '+str(target)+'\n' and lines[-1]=='*** End Patch';assert all(x.startswith('+') for x in lines[2:-1]);assert ''.join(x[1:] for x in lines[2:-1]).encode()==b;assert stage['actual_tool_return']=={} and stage['numeric_exit'] is None and stage['target_before'] is None
 archive_path=I/archive_name;archive=pin(archive_path);assert checked(archive)==b and archive_path.stat().st_mode==target.stat().st_mode;assert any(ident(r)==archive for r in META_OBS['inputs']);row={**pin(target),'candidate':pin(candidate),'physical':archive,'base64':base64.b64encode(b).decode(),'mode':target.stat().st_mode,'source_lines':len(b.splitlines())};source_rows.append(row);report_sources.append({'pin':pin(target),'candidate':pin(candidate),'physical':archive,'mode':row['mode'],'lines':row['source_lines']})
old=checked(template_pins[0]);new=bounded_read(targets[0]);old_plugin=checked(template_pins[1]);new_plugin=bounded_read(targets[1]);identity_changes=[["round285-p6-t2-new-test-generation-validation-continuation-20261017","round289-p6-t2-accepted-runner-validation-continuation-20261017"],["22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0","4bc64ed58a737cb9f6bbe7386a9937a189b3e1522258e8a85c051bbd8f5fe5fb"],["3af0606bc3b09737f0c744ab7819a9fdfb94b32e7f516045ebd3a66218682508","82c31139a709e11ca78fefaae3bc8df9cda1612a0584e2c391a527b9b1501cf3"],["39b5cae7d0841f2c8901d7a30910018dd312840ecbdb96c4f064641b56db03b8","fc267162c6ad812a056191eef27c727ae2009248c2034c58baeae53562fdfd19"],["r285_session_evidence","r289_session_evidence"],["bigsmall.r285.","bigsmall.r289."],["R285","R289"],[".r258-next",".r289-next"]]
def ns(b):
 for old_id,new_id in identity_changes:b=b.replace(old_id.encode(),new_id.encode())
 return b
assert ns(old_plugin)==new_plugin
old_markers=[b'def _t2_pin(',b'def author_bytes(',b'def authority(context):',b'def preconditions():',b'def save_before(context):',b'def junit_observation(',b'def session_observations(',b'def completion_marker_fact(',b'def main():']
new_markers=old_markers.copy();new_markers[2]=b'def verify_prior_runs(context):'
for m in old_markers:assert old.count(m)==1
for m in new_markers:assert new.count(m)==1
ob=[0]+[old.index(m) for m in old_markers]+[len(old)];nb=[0]+[new.index(m) for m in new_markers]+[len(new)];assert ob==sorted(ob) and nb==sorted(nb)
labels=['header','four_original_t2_helpers','capture_metadata_helpers','finite_authority_and_prior_receipts','preconditions_and_role_binding','before_snapshot_helper','junit_and_case_consumers','session_consumer','C486_completion_helpers','protected_main']
cc=bounded_read(I/'prepared-run-evidence-source.txt');assert hashlib.sha256(cc).hexdigest()=='cc0b192b551deda39433193fe5a723546f517fcbeb11ed33e781a46cb4d2e8b4'
p291=read_json(J/'plan.json');p292=read_json(K/'plan.json');q291=p291['scope']['exact_change'];q292=p292['scope']['exact_change'];portions=[]
for idx,label in enumerate(labels):
 before,after=old[ob[idx]:ob[idx+1]],new[nb[idx]:nb[idx+1]]
 if label=='finite_authority_and_prior_receipts':
  lo=cc.index(new_markers[2]);hi=cc.index(b'def preconditions():');expected=cc[lo:hi].replace(q292['old'].encode(),q292['new'].encode(),1);kind='EXPLICIT_FINITE_AUTHORITY_WITH_R292_ROLE_PIN_BINDING'
 elif label=='preconditions_and_role_binding':
  expected=cc[cc.index(b'def preconditions():'):cc.index(b'def save_before(context):')];kind='EXPLICIT_FINITE_GATE_ROLE_PRIOR_RECEIPT_BINDING'
 elif label=='session_consumer':
  expected=ns(before).replace(q291['old'].encode(),q291['new'].encode(),1);kind='IDENTITY_ONLY_PLUS_EXACT_R291_LEASE_SELECTOR'
 elif label in ('four_original_t2_helpers','C486_completion_helpers'):
  expected=before;kind='WHOLE_UNCHANGED'
 else:expected=ns(before);kind='IDENTITY_ONLY'
 assert after==expected,label
 portions.append({'label':label,'scope':kind,'before':{'start_byte':ob[idx],'end_byte':ob[idx+1],'bytes':len(before),'sha256':hashlib.sha256(before).hexdigest()},'after':{'start_byte':nb[idx],'end_byte':nb[idx+1],'bytes':len(after),'sha256':hashlib.sha256(after).hexdigest()},'exact_expected_bytes':True})
old_helper=old[ob[1]:ob[2]];new_helper=new[nb[1]:nb[2]]
assert (ob[1],ob[2])==(5352,23031) and (nb[1],nb[2])==(5348,23027)
assert old_helper==new_helper
assert len(old_helper)==len(new_helper)==17679
assert hashlib.sha256(old_helper).hexdigest()==hashlib.sha256(new_helper).hexdigest()=='8ef88c6906820c7a82a7c3bddfc2e60dc8335b4c8c3919228aa7938bf37b5af6'
assert b''.join(new[nb[i]:nb[i+1]] for i in range(len(labels)))==new
limited=save(I/'limited.diff',(''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile=template_pins[0]['path'],tofile=str(targets[0])))+''.join(difflib.unified_diff(old_plugin.decode().splitlines(True),new_plugin.decode().splitlines(True),fromfile=template_pins[1]['path'],tofile=str(targets[1])))).encode())
chain=[]
for rd in (J,K):
 records=[pin(rd/name) for name in ['plan.md','plan.json','input-observation.json','before/manifest.json','implementation/prepared-run-evidence-source.txt','implementation/after-prepared-run-evidence-source.txt','implementation/actual-native-tool-return.json','implementation/limited.diff','implementation/source-scope-proof.json','implementation/change-report.json']];chain.append({'round':'R291' if rd==J else 'R292','records':records})
root_acceptance=pin(D/'root-candidate-source-native-acceptance.json');assert root_acceptance['sha256']=='bada18ada634de18d7a0011880644a602b377bc8937b81e5d52fb98c88cc81b1'
scope={'round':'R289','status':'SOURCE_READY_ONLY_BEHAVIOR_UNVERIFIED','templates':template_pins,'sources':[ident(r) for r in source_rows],'runner_portions':portions,'runner_coverage_complete':True,'plugin_scope':'COMPLETE_IDENTITY_ONLY_FROM_FROZEN_1989','plugin_exact_expected_bytes':True,'identity_changes':identity_changes,'four_original_helper_bytes':len(old_helper),'C486_completion_helpers_whole_unchanged':True,'protected_main_identity_only':True,'session_consumer_identity_plus_R291_only':True,'native_reconstruction_exact':True,'target_before':[None,None],'supplement_chain':chain,'ROOT_candidate_acceptance':root_acceptance,'limited_diff':limited,'native':pin(I/'actual-native-tool-returns.json'),'runtime_executed':False}
scope['recovery_provenance']=recovery;scope['helper_slice']={'anchors':['def _t2_pin','def author_bytes'],'old_range':[ob[1],ob[2]],'new_range':[nb[1],nb[2]],'bytes':len(old_helper),'sha256':hashlib.sha256(old_helper).hexdigest(),'whole_equal':True,'includes_separator_bytes':True};scope['ten_new_regions_join_whole']=True
qp=write(I/'final-source-scope-proof.json',scope)
container=json.loads(checked(P['authority_contract']['container']));assert len(container['sources'])==27 and len(container['authority_before']['protected'])==211
X={'schema_version':'bigsmall.r289.source-index.v1','round':'R289','status':'SOURCE_READY_ONLY','sources':source_rows,'target_before':[None,None],'templates':template_rows,'template_before_manifest':P['before_manifest'],'input_records':input_records,'supplement_inputs':S['inputs'],'context_manifest':S['context_manifest'],'accepted_authority':P['authority_contract']['container'],'accepted_history_generations':container['authority_before']['accepted_history_generations'],'history_reaudited_as_current':False,'current_sources':O['current_sources'],'protected':container['authority_before']['protected'],'protected_count':211,'native':pin(I/'actual-native-tool-returns.json'),'candidate_native':pin(I/'candidate-native-tool-returns.json'),'scope_proof':qp,'runner_portions':portions,'supplement_chain':chain,'ROOT_candidate_acceptance':root_acceptance,'runtime':False}
X['recovery_provenance']=recovery
xp=write(I/'source-index.json',X)
report={'round':'R289','status':'SOURCE_READY_ONLY_STOP_FOR_ROOT','sources':report_sources,'native':N,'native_pin':pin(I/'actual-native-tool-returns.json'),'candidate_native':pin(I/'candidate-native-tool-returns.json'),'before_manifest':P['before_manifest'],'source_index':xp,'scope_proof':qp,'limited_diff':limited,'input_count':len(input_records),'supplement_chain':chain,'ROOT_candidate_acceptance':root_acceptance,'source_contract':{'runner_template':'accepted C486','plugin_template':'frozen1989','four_helpers':'whole '+str(len(old_helper))+' bytes unchanged from def _t2_pin to def author_bytes including separators; SHA256 '+hashlib.sha256(old_helper).hexdigest(),'completion':'wholeC486helpersunchanged','main':'identityonly; protected reservation/finally and failclosed assessment/persistence unchanged','consumer':'identityonly plus exact R291 lease source binding','authority':'R28932/S8 typed finite authority; R292 explicit ROOT/AUTHOR envelope.pin; accepted68 not recursively current re-audited; R2854DB from actual persistent index; R276result explicit immutable source','prior_receipts':'Only selected exact reservation-bound immutable supplement; ordered0/1/2 and complete independent ROOT accepted preceding receipts'},'old_candidates_native_raw_unchanged':True,'roles_created':False,'roles_context_modified':False,'source_executed':False,'runtime':False}
report['recovery_provenance']=recovery
rp=write(I/'change-report.json',report)
display={'round':'R293','status':'SOURCE_REPORTS_FINALIZED_ONLY_STOP','sources':[{'pin':row['pin'],'lines':row['lines']} for row in report_sources],'pins':{'native':pin(I/'actual-native-tool-returns.json'),'limited_diff':limited,'scope_proof':qp,'source_index':xp,'change_report':rp},'input_count':len(input_records),'roles_created':False,'runtime':False}
deadline_check();rendered=json.dumps(display,ensure_ascii=False);assert len((rendered+'\n').encode())<=6000
print(rendered)
signal.alarm(0)
