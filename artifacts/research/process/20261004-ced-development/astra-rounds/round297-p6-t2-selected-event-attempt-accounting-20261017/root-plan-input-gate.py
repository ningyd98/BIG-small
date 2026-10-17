"""ROOT R297 ordinary exact-input/four-edit applicability; source only."""
from pathlib import Path
import base64,hashlib,json,signal,stat,time
D=Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round297-p6-t2-selected-event-attempt-accounting-20261017')
deadline=time.monotonic()+120
def expired(*args):raise TimeoutError('R297 ordinary metadata120s')
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
Ppin={'path':str(D/'plan.json'),'bytes':14838,'sha256':'a3af36272e2e079ef4793050906cb770bed8fa3299eb935e7d5ef219a1d6702e'}
P=json.loads(checked(Ppin));O=json.loads(checked(P['input_observation']));M=json.loads(checked(P['before_manifest']))
checked({'path':str(D/'plan.md'),'bytes':2775,'sha256':'4470e0f9cb3a57b0e2fb86b50c7da7d49844016960d991c355f1631fa2514309'})
check(P['round']==O['round']==M['round']=='R297' and P['actual_model']==O['actual_model']=='gpt-6-astra' and P['inputs']==O['inputs'] and len(P['inputs'])==10,'actual_Astra_exact10inputs')
for q in P['inputs']:checked(q)
check(len(M['files'])==4,'four_fullbefore')
for row in M['files']:
 b=base64.b64decode(row['base64'],validate=True)
 check(pin(row['original']['path'],b)==identity(row['original']) and checked(row['original'])==checked(row['archive'])==b,'fullbefore_physical_base64')
 check(Path(row['original']['path']).lstat().st_mode==Path(row['archive']['path']).lstat().st_mode==row['mode'],'fullbefore_mode')
target=Path(P['scope']['logical_target']);raw=target.read_bytes();text=raw.decode()
check(pin(target)['sha256']=='bca996d6a23a68180fda0c3536cbb4069d65c0d81b31d2116df6deb1cd4da962' and target.lstat().st_mode==33204,'exact_unexecuted_bca_target')
for row in P['scope']['exact_replacements']:
 check(text.count(row['before'])==row['original_occurrences']==1,'unique_four_edit:'+row['id'])
 text=text.replace(row['before'],row['after'],1)
derived=text.encode();expected=P['scope']['expected_after']
check(len(derived)==expected['bytes']==30429 and hashlib.sha256(derived).hexdigest()==expected['sha256']=='e6c2858afae2928bb5db279d82ac2a87465ccca6d0a6e5a7a46208bdb4059cc3' and len(derived.splitlines())==608,'exact_derived_after_not_written')
R=target.parent.parent
for p in [Path(P['scope']['new_candidate']),Path(P['scope']['after_archive']),*[Path(q) for q in P['outputs'].values()],R/'root-command-ledger.json',R/'implementation/command-ledger.json',R/'implementation/dual_rpc_timeout_evidence']:
 check(not p.exists() and not p.is_symlink(),'not_yet_created:'+str(p))
check(P['budget']['R296.dual_rpc_timeout_evidence']['used']==0 and P['budget']['R296.dual_rpc_timeout_evidence']['remaining']==1 and P['budget']['R297_new_runtime']==0,'single_original_slot_held_no_added_runtime')
out={'round':'R297','status':'EXACT_FOUR_SOURCE_EDITS_APPLICABLE_NO_RUNTIME','plan':Ppin,'checks_passed':len(checks),'checks':checks,'derived_after':expected,'source_edit_released':True,'runtime_released':False,'T2_complete':False}
dest=D/'root-plan-applicability.json';raw=(json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode()
with dest.open('xb') as f:f.write(raw)
summary=json.dumps({k:v for k,v in out.items() if k!='checks'},ensure_ascii=False)
check(len((summary+'\n').encode())<=6000,'console6000');print(summary);signal.alarm(0)
