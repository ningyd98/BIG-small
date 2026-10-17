"""ROOT R298 ordinary exact-input/EOF-generation applicability; metadata preparation only."""
from pathlib import Path
import base64,hashlib,json,signal,stat,time
D=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round298-p6-t2-plugin-finalization-eof-byte-generation-20261017')
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('R298 ordinary metadata120s')
signal.signal(signal.SIGALRM,expired);signal.alarm(120)
checks=[]
def check(ok,label):
 if time.monotonic()>=deadline:expired()
 assert ok,label
 checks.append(label)
def identity(q):return {k:q[k] for k in ('path','bytes','sha256')}
def pin(p,b=None):
 p=Path(p);b=p.read_bytes() if b is None else b
 return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q['path']);b=p.read_bytes()
 check(stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==identity(q),'physical:'+str(p));return b
Ppin={'path':str(D/'plan.json'),'bytes':13946,'sha256':'1589f6c4a28aba533517f55b04cbbabbd56a08ea52ec30ecb232b7fdfa62f472'}
P=json.loads(checked(Ppin));O=json.loads(checked(P['observation']));M=json.loads(checked(P['before_manifest']))
checked({'path':str(D/'plan.md'),'bytes':2466,'sha256':'e84b7a06e50dab92359de2c541eff50b4fa1e39084ffe4d279ddd02a7b6be6c7'})
check(P['round']==O['round']==M['round']=='R298' and P['actual_model']==O['actual_model']=='gpt-6-astra' and P['inputs']==O['inputs'] and len(P['inputs'])==11,'actual_Astra_exact11inputs')
for q in P['inputs']:checked(q)
check(type(M['files']) is list and 3<=len(M['files'])<=11,'finite_complete_fullbefore')
for row in M['files']:
 b=base64.b64decode(row['base64'],validate=True)
 check(pin(row['original']['path'],b)==identity(row['original']) and checked(row['original'])==checked(row['archive'])==b,'fullbefore_physical_base64')
 check(Path(row['original']['path']).lstat().st_mode==Path(row['archive']['path']).lstat().st_mode==row['mode'],'fullbefore_mode')
target=checked(P['scope']['target']);candidate=checked(P['scope']['approved_candidate'])
check(target+b'\n'==candidate and target.endswith(b'        raise\n') and len(target)==30428 and len(candidate)==30429 and len(target.splitlines())==607 and len(candidate.splitlines())==608,'one_exact_terminal_0a_generation')
P297=json.loads(checked(P['inputs'][0]));beforepin=next(q for q in P['inputs'] if q['sha256']=='bca996d6a23a68180fda0c3536cbb4069d65c0d81b31d2116df6deb1cd4da962')
old=checked(beforepin);derived=old.decode()
for row in P297['scope']['exact_replacements']:
 check(derived.count(row['before'])==1,'unique_original_four_edit:'+row['id']);derived=derived.replace(row['before'],row['after'],1)
check(derived.encode()==candidate and target!=candidate,'original_R297_expected_false_R298_generation_true')
native=json.loads(checked(next(q for q in P['inputs'] if q['path']==P297['outputs']['native_receipt'])))
patch='*** Begin Patch\n*** Update File: '+P297['scope']['logical_target']+'\n'
for row in P297['scope']['exact_replacements']:patch+='@@\n'+''.join('-'+line+'\n' for line in row['before'].splitlines())+''.join('+'+line+'\n' for line in row['after'].splitlines())
patch+='*** End Patch'
check(native['arguments']==patch and native['actual_tool_return']=={} and native['numeric_exit'] is None,'exact_original_native_arguments_object_not_numeric_exit')
for path in [P297['scope']['after_archive'], *(P297['outputs'][key] for key in ('diff','proof','report','root_acceptance')), *(P['recovery_metadata']['outputs'][key] for key in ('after','diff','proof','report','actual')), P['recovery_metadata']['source']]:
 q=Path(path);check(not q.exists() and not q.is_symlink(),'still_absent:'+path)
R=Path(P['scope']['target']['path']).parent.parent
for path in [R/'root-command-ledger.json',R/'implementation/command-ledger.json',R/'implementation/dual_rpc_timeout_evidence']:check(not path.exists() and not path.is_symlink(),'no_new_role_or_runtime:'+str(path))
out={'round':'R298','status':'FINITE_EOF_METADATA_PREPARATION_APPLICABLE_NO_SOURCE_EDIT_NO_RUNTIME','plan':Ppin,'checks_passed':len(checks),'checks':checks,'original_R297_expected_match':False,'R298_exact_generation_match':True,'metadata_source_preparation_released':True,'metadata_execution_released':False,'runtime_released':False}
dest=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round299-p6-t2-root-existence-selector-disposition-20261017/root-r298-plan-applicability.json')
with dest.open('xb') as f:f.write((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
summary=json.dumps({k:v for k,v in out.items() if k!='checks'},ensure_ascii=False)
check(len((summary+'\n').encode())<=6000,'console6000');print(summary);signal.alarm(0)
