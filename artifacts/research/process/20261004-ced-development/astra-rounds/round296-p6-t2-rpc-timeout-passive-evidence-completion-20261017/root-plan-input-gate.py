"""ROOT R296 ordinary plan/fullbefore/input applicability gate; no project imports or candidate execution."""
from pathlib import Path
import base64,hashlib,json,signal,stat,time
D=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017')
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('R296 plan metadata120s')
signal.signal(signal.SIGALRM,expired);signal.alarm(120)
checks=[]
def check(ok,label):
 if time.monotonic()>=deadline:expired()
 assert ok,label
 checks.append(label)
def ident(q):return {k:q[k] for k in ('path','bytes','sha256')}
def pin(p,b=None):
 p=Path(p);b=p.read_bytes() if b is None else b
 return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q['path']);b=p.read_bytes()
 check(stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==ident(q),'physical:'+str(p))
 return b
def doc(q):return json.loads(checked(q))
p={'path':str(D/'plan.json'),'bytes':35664,'sha256':'68c41755f5717446324f89d6c2b8b5740e0c47fef351e7846b99d31a966720f9'}
P=doc(p);O=doc(P['input_observation']);M=doc(P['before_manifest'])
checked({'path':str(D/'plan.md'),'bytes':5321,'sha256':'c8cb05b492f4ce789d0ac633e31c5e658d33093c936055e6356206e379b28c8e'})
check(P['round']==O['round']==M['round']=='R296' and P['actual_model']==O['actual_model']=='gpt-6-astra','actual_Astra_round')
check(P['inputs']==O['inputs'] and len(P['inputs'])==30,'exact30inputs')
for q in P['inputs']:checked(q)
check(len(M['files'])==8,'eight_fullbefore')
for row in M['files']:
 b=base64.b64decode(row['base64'],validate=True)
 check(pin(row['original']['path'],b)==ident(row['original']) and checked(row['original'])==checked(row['archive'])==b,'complete_physical_base64')
 check(Path(row['original']['path']).lstat().st_mode==Path(row['archive']['path']).lstat().st_mode==row['mode'],'fullbefore_modes')
R=Path(P['scope']['base_runner']).parent.parent
context=json.loads((R/'root-context-update.json').read_bytes());settle=json.loads((R/'root-dual-first-invalidation-role-settlement.json').read_bytes())
history=[]
for row in context['changes']:history.append(row['before'])
history.append(settle['root_before'])
def current_or_mapped(q):
 mapped=[row for row in history if ident(row['original'])==ident(q)]
 if not mapped:return checked(q)
 check(len(mapped)==1,'single_exact_historical_generation')
 row=mapped[0];b=base64.b64decode(row['base64'],validate=True)
 check(pin(q['path'],b)==ident(q) and checked(row['archive'])==b and Path(row['archive']['path']).lstat().st_mode==row['mode'],'explicit_historical_before_only')
 return b
actual=json.loads((R/'implementation/dual_first_invalidation/result.json').read_bytes())
before=doc(actual['before']);after=doc(actual['after'])
check(len(before['sources'])==27 and len(after['protected'])==211 and before['authority_before']==after,'current27_protected211')
for q in before['sources']:
 b=checked(q);check(b==checked(q['physical'])==base64.b64decode(q['base64'],validate=True) and Path(q['path']).lstat().st_mode==q['mode'],'current_source_wholebytes_mode')
for q in after['protected']:current_or_mapped(q)
for role in ['ROOT','AUTHOR']:
 q=next(q for q in P['inputs'] if q['path']==str(R/('root-command-ledger.json' if role=='ROOT' else 'implementation/command-ledger.json')))
 value=doc(q)
 for key in ['wait_memory','wait_sqlite','dual_first_invalidation']:check(value['commands'][key]['used']==1 and value['commands'][key]['remaining']==0 and value['commands'][key]['state'].startswith('SPENT'),'old_role_spent:'+role+':'+key)
command=P['commands']['dual_rpc_timeout_evidence']
check(list(P['commands'])==['dual_rpc_timeout_evidence'] and command['authorized']==command['remaining']==1 and command['used']==0 and command['kind']=='diagnostic_only','one_new_diagnostic_only')
for path in [*P['scope']['new_sources'],P['runner_contract']['roles']['ROOT'],P['runner_contract']['roles']['AUTHOR']]:
 check(not Path(path).exists() and not Path(path).is_symlink(),'new_target_absent:'+path)
check(not Path(command['output_directory']).exists(),'new_output_absent')
out={'round':'R296','status':'PLAN_FULLBEFORE_FINITE_INPUTS_APPLICABLE_SOURCE_PREPARATION_ONLY','plan':p,'input_observation':P['input_observation'],'before_manifest':P['before_manifest'],'checks_passed':len(checks),'checks':checks,'source_preparation_released':True,'runtime_released':False,'new_runtime':0,'T2_complete':False}
raw=(json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode();dest=D/'root-plan-applicability.json'
with dest.open('xb') as stream:stream.write(raw)
summary=json.dumps({k:v for k,v in out.items() if k!='checks'},ensure_ascii=False)
check(len((summary+'\n').encode())<=6000,'console6000');print(summary);signal.alarm(0)
