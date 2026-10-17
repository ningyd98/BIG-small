from pathlib import Path
import hashlib,json,os,subprocess,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
M=Path('/home/ningyd/文档/ChatGPT/BIGsmall');W=Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall');B=Path('artifacts/research/process/20261004-ced-development');O=B/'t12-sol-handoff-20261007/delivery-p2';R=B/'astra-rounds/round87-p2-git-delivery-20261007';PY=M/'.venv/bin/python'
def pin(b):return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def write(n,d):
 p=M/O/n;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def now():return datetime.now(timezone.utc).isoformat()
def pins():
 ds=json.loads((M/O/'closure.json').read_text())['dependencies'];return [{'path':x['path'],**pin((W/x['path']).read_bytes())} for x in ds]
contract=json.loads((M/R/'candidate4-contract.json').read_text());nodes=contract['nodeids'];tmp=Path('/tmp/bigsmall-p2-delivery-20261007');assert not tmp.exists();assert not (M/O/'candidate4-command.json').exists();tmp.mkdir()
env=os.environ.copy();env.update(PYTHONPATH=str(W/'src')+':'+str(W),PYTHONDONTWRITEBYTECODE='1');argv=[str(PY),'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(tmp/'pytest'),*nodes,'--junitxml='+str(M/O/'candidate4.junit.xml')]
before=pins();start=now();write('candidate4-command.json',{'argv':argv,'cwd':str(W),'env':{k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},'started_utc':start,'new_candidate_budget':1,'fresh_basetemp_parent':str(tmp),'junit':str(M/O/'candidate4.junit.xml'),'before_dependency_pins':before,'prior_candidate4_invocations':0,'purpose':'R87 exported candidate validation; does not rerun or enlarge original94 denominator.'})
t=time.monotonic();q=subprocess.run(argv,cwd=W,env=env,capture_output=True);end=now();elapsed=time.monotonic()-t
for n,b in [('candidate4.stdout.txt',q.stdout),('candidate4.stderr.txt',q.stderr)]:p=M/O/n;assert not p.exists();p.write_bytes(b)
rows=[];parse_error=None
try:
 root=ET.parse(M/O/'candidate4.junit.xml').getroot()
 for c in root.iter('testcase'):
  identity=c.get('classname','').replace('.','/')+'.py::'+c.get('name','');outcome='pass'
  for tag in ['failure','error','skipped']:
   if c.find(tag) is not None:outcome=tag
  rows.append({'nodeid':identity,'classname':c.get('classname'),'name':c.get('name'),'outcome':outcome,'time':c.get('time')})
except Exception as exc:parse_error=repr(exc)
write('test-outcomes.json',{'cases':rows,'unique_nodeids':len({r['nodeid'] for r in rows}),'expected_exact_nodeids':nodes,'parse_error':parse_error})
after=pins();write('before-after-pins.json',{'before':before,'after':after,'identical':before==after,'source5':json.loads((M/R/'root-activation.json').read_text())['source_pins5'],'primary_source_modified':False})
temps=[]
for f in sorted(tmp.rglob('*')):
 if f.is_file():assert not f.is_symlink();temps.append({'path':str(f),'relative':str(f.relative_to(tmp)),**pin(f.read_bytes()),'local_only':True})
write('temp-originals.json',{'parent':str(tmp),'files':temps,'file_count':len(temps),'total_bytes':sum(x['bytes'] for x in temps),'complete_for_this_fresh_temp_directory':True,'copied_to_git':0,'old_transport_raw_read_hash_copy':0})
passed=q.returncode==0 and parse_error is None and len(rows)==4 and len({r['nodeid'] for r in rows})==4 and {r['nodeid'] for r in rows}==set(nodes) and all(r['outcome']=='pass' for r in rows) and before==after
write('candidate4-result.json',{'status':'PASS_EXPORTED_CANDIDATE4' if passed else 'UNEXPECTED_FAILURE_STOP_ASTRA','started_utc':start,'ended_utc':end,'elapsed_seconds':elapsed,'exit_code':q.returncode,'invocations':1,'cases':len(rows),'unique_cases':len({r['nodeid'] for r in rows}),'passed':sum(r['outcome']=='pass' for r in rows),'failed':sum(r['outcome']=='failure' for r in rows),'errors':sum(r['outcome']=='error' for r in rows),'skipped':sum(r['outcome']=='skipped' for r in rows),'pins_unchanged':before==after,'stdout_pin':pin(q.stdout),'stderr_pin':pin(q.stderr),'junit_pin':pin((M/O/'candidate4.junit.xml').read_bytes()) if (M/O/'candidate4.junit.xml').exists() else None,'tmp_file_count':len(temps),'actual':0,'formal_accepted':False,'original_94_history':'93 original passes + one R85 repair pass =94 unique covered, not94 rerun','other_tests_static_actual_runs':0})
print(json.dumps({'passed':passed,'exit':q.returncode,'unique':len(rows),'temporary_originals':len(temps),'seconds':elapsed}));assert passed,'Unexpected candidate4 failure; preserve and stop, no retry'
