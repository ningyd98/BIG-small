"""R289 factual planning.R289 and PHASE suffix update after all three slots stopped; no development or research promotion."""
from pathlib import Path
import base64,copy,hashlib,json,os,signal,stat,time
D=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017')
Q=json.loads(r'''{"plan":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/plan.json","bytes":48642,"sha256":"4bc64ed58a737cb9f6bbe7386a9937a189b3e1522258e8a85c051bbd8f5fe5fb","mode":33204},"step":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/step-report.json","bytes":8269,"sha256":"ef0b69039f3056b730aa6d50f3a7a1fe9d3996f44ef74aca2833e736f1e2eda1","mode":33204},"step_md":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/step-report.md","bytes":1182,"sha256":"9bc3e196293db33ac9699a22b17add182acade2a5152102cdb36237bdf79c80c","mode":33204},"STATE":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/active-t12-state.json","bytes":180405,"sha256":"f854dd7801af2dbd06397820153ce342b161551650c56528a3064409ff08eaba","mode":33204},"PHASE":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/phase-summary.md","bytes":102453,"sha256":"4aeca541d66dd7d93dc1a3029a899108b3e830597f38432ef43eefcfb3e50fc5","mode":33204},"ROOT":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/root-command-ledger.json","bytes":44024,"sha256":"d3082f973ba4193f96554a8ec1885fe573d15f55a4c61442b8a783c3bfcbe80c"},"AUTHOR":{"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/implementation/command-ledger.json","bytes":41233,"sha256":"4580288fcb16223dccc7d9b781019c7e3434ebf59279478ea888ce1bea278249"}}''')
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('R289 factual context metadata120s')
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
 if 'mode' in q:check(p.lstat().st_mode==q['mode'],'mode:'+str(p))
 return raw
def encode(v):return (json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
def save(path,raw,mode=33204):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 p.chmod(stat.S_IMODE(mode));check(p.read_bytes()==raw and p.lstat().st_mode==mode,'exclusive_readback:'+str(p))
 return pin(p,raw)
for path in [D/'root-context-update.json',D/'before/context/generation001/prospective-map.json']:
 check(not path.exists() and not path.is_symlink(),'absent:'+str(path))
P=json.loads(checked(Q['plan']));STEP=json.loads(checked(Q['step']));checked(Q['step_md'])
check(P['round']==STEP['round']=='R289' and STEP['status']=='THREE_ONCE_SLOTS_SPENT_DUAL_PARTIAL_STOP_NEXT_ASTRA' and STEP['runtime_stopped'] is True and STEP['next_runtime_released'] is False,'documented_all_execution_STOP')
check(STEP['runtime_attempts']==3 and STEP['retries']==STEP['new_Git']==0 and STEP['repair_performed'] is False,'only_original_three_once')
for field in ['T2_complete','T12_complete','native_accepted','formal_accepted']:check(STEP[field] is False,'no_promotion:'+field)
role_raw={key:checked(Q[key]) for key in ['ROOT','AUTHOR']}
for role,raw in role_raw.items():
 value=json.loads(raw)
 for key in ['wait_memory','wait_sqlite','dual_first_invalidation']:
  entry=value['commands'][key]
  check(entry['used']==1 and entry['remaining']==0 and entry['state'].startswith('SPENT'),'all_roles_selected_spent:'+role+':'+key)
check(STEP['roles_current']=={key:identity(Q[key]) for key in ['ROOT','AUTHOR']},'actual_step_role_pins')
for key,value in STEP['commands'].items():
 ap=value['independent_assessment'] if key=='dual_first_invalidation' else value['independent_acceptance']
 receipt=json.loads(checked(ap))
 check(receipt['round']=='R289' and receipt['command_id']==key,'actual_receipt:'+key)
 if key=='dual_first_invalidation':
  check(receipt['status']=='INDEPENDENT_PARTIAL_DIAGNOSTIC_CAPTURE_RECORDED_STOP_NEXT_ASTRA' and receipt['diagnostic_complete'] is False and receipt['behavior_accepted'] is False and receipt['captured_events']==7 and receipt['dropped_events']==10 and receipt['full_first_cause']=='UNKNOWN_REQUIRES_ROOT_EVENT_INTERPRETATION','partial_diagnostic_not_promoted')
  settled=json.loads(checked(value['root_settlement']))
  check(settled['root_after']==identity(Q['ROOT']) and settled['author_unchanged']==identity(Q['AUTHOR']),'dual_settlement_actual_roles')
 else:check(receipt['status']=='VERIFIED_COMPLETE_BEHAVIOR_CAPTURE','independent_behavior_acceptance:'+key)
for key in ['source_gate','script_gate']:checked(STEP[key])
SG=json.loads(checked(STEP['source_gate']))
for value in SG['sources'].values():checked(value)
state_before,phase_before=checked(Q['STATE']),checked(Q['PHASE'])
old=json.loads(state_before);new=copy.deepcopy(old)
check('R289' not in old['planning'],'unique_planning_R289')
new['planning']['R289']={**copy.deepcopy(STEP),'plan':identity(Q['plan']),'step_report':identity(Q['step']),'context_before':{key:identity(Q[key]) for key in ['STATE','PHASE']},'all_once_slots_spent':True,'other_runtime_released':False,'fresh_readonly_review_batches_executed':0,'next_required':'Actual Astra R296 plan must bind resulting factual context and settled role generations; repair/diagnostic/runtime unavailable until its explicit finite release.'}
comparison=copy.deepcopy(new);comparison['planning'].pop('R289')
check(comparison==old,'all_other_STATE_values_unchanged')
state_after=encode(new)
appendix=('\n\n## R289：两项等待通过、dual诊断未完整（2026-10-17）\n\n'
'memory与SQLite等待各一次，子测试0/运行器0，ROOT独立复核接受完整行为捕获；各新增4个保留数据库。dual一次414.430299505秒，子测试1/运行器0，在commit-seam-0准备阶段reserve_plan会话入口拒绝，尚未到预定故障注入；尝试365、初始化364、清理观察365，新增2个数据库。\n\n'
'dual被动记录实际37420字节，共7条事件，预算估算导致10条丢弃。已观察heartbeat RPC wait cap exceeded→broker late reply→main入口拒绝；迟回根因仍未知。捕获完整性通过不代表诊断完整或行为通过。原始失败、丢弃与unknown均保留，不补写原件，不修改TTL/wait/产品保护。\n\n'
'三个一次性槽均SPENT1/0；ROOT dual为SPENT_PARTIAL_DIAGNOSTIC_CAPTURE，AUTHOR已SPENT。已停止进一步运行。细节及角色完整before/base64/mode/CAS见R289/step-report.json、root-dual-first-invalidation-independent-assessment.json与root-dual-first-invalidation-role-settlement.json。\n\n'
'27当前源、211保护文件未改；新增共10个数据库证据不恢复原35项丢失文件/90项缺失侧文件。T2、T12、native与正式研究验收仍未完成。新Git次数0，后续12批独立只读审阅仍未执行。下一步实际Astra以本次真实上下文和结算角色世代制定R296有限计划；旧spent槽不得复用。\n')
phase_after=phase_before+appendix.encode()
check(phase_after[:len(phase_before)]==phase_before,'PHASE_original_prefix_unchanged')
changes=[];prepared=[]
for label,before,after in [('STATE',state_before,state_after),('PHASE',phase_before,phase_after)]:
 q=Q[label];p=Path(q['path']);mode=p.lstat().st_mode
 check(mode==q['mode']==33204,'context_mode:'+label)
 archive=save(D/'before/context/generation001'/(label+'.before'),before,mode)
 after_archive=save(D/'before/context/generation001'/(label+'.after'),after,mode)
 changes.append({'label':label,'before':{'original':identity(q),'archive':archive,'base64':base64.b64encode(before).decode(),'mode':mode},'after':pin(p,after),'after_archive':after_archive,'mode':mode})
 prepared.append((p,before,after,mode))
prospective={'round':'R289','status':'PROSPECTIVE_FACTUAL_CONTEXT_MAP_BEFORE_CAS','plan':identity(Q['plan']),'step_report':identity(Q['step']),'roles_current':{key:identity(Q[key]) for key in ['ROOT','AUTHOR']},'changes':changes,'allowed_STATE_keys':['planning.R289'],'all_other_STATE_values_unchanged':True,'PHASE_original_prefix_unchanged':True,'runtime_stopped':True,'new_runtime':0,'new_Git':0,'T2_complete':False,'T12_complete':False,'native_accepted':False,'formal_accepted':False}
save(D/'before/context/generation001/prospective-map.json',encode(prospective))
committed={}
for p,before,after,mode in prepared:
 for other,other_before,other_after,other_mode in prepared:check(other.lstat().st_mode==other_mode and other.read_bytes()==committed.get(str(other),other_before),'immediate_context_CAS')
 for role,raw in role_raw.items():check(checked(Q[role])==raw,'roles_still_STOP:'+role)
 fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
 with os.fdopen(fd,'r+b') as f:
  check(os.fstat(f.fileno()).st_mode==mode and f.read()==before,'descriptor_CAS:'+str(p))
  f.seek(0);f.write(after);f.truncate();f.flush();os.fsync(f.fileno())
 check(p.read_bytes()==after and p.lstat().st_mode==mode,'actual_context_readback:'+str(p))
 committed[str(p)]=after
manifest={**prospective,'status':'ACTUAL_FACTUAL_CONTEXT_UPDATED_AFTER_THREE_SLOTS_STOP'}
mp=save(D/'root-context-update.json',encode(manifest))
for row in changes:check(checked(row['after'])==checked(row['after_archive']),'full_after_archive')
output=json.dumps({'status':manifest['status'],'context_manifest':mp,'after':[row['after'] for row in changes],'roles_current':manifest['roles_current'],'checks_passed':len(checks),'allowed_STATE_keys':['planning.R289'],'all_other_STATE_values_unchanged':True,'PHASE_original_prefix_unchanged':True,'new_runtime':0,'T2_complete':False},ensure_ascii=False)
check(len((output+'\n').encode())<=6000,'console6000');print(output);signal.alarm(0)
