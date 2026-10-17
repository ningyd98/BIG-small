from pathlib import Path
import ast, copy, hashlib, json, os, shutil, stat, subprocess, sys
from datetime import datetime, timezone
M=Path('/home/ningyd/文档/ChatGPT/BIGsmall');W=Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
B=Path('artifacts/research/process/20261004-ced-development');H=B/'t12-sol-handoff-20261007';O=H/'delivery-p2';R=B/'astra-rounds/round87-p2-git-delivery-20261007';R89=B/'astra-rounds/round89-activation-compact-receipt-20261007'
PARENT='98b8282138ba61367db526d7d8f52e27085f4f9f';PY=M/'.venv/bin/python'
def pin(b):return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def read(p):return json.loads((M/p).read_text())
def write(name,d):
 p=M/O/name;assert not p.exists(),str(p);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def cmd(argv,cwd=W):
 q=subprocess.run(argv,cwd=cwd,capture_output=True);return {'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}
def checkpin(p,e):
 f=M/p;assert f.is_file() and not f.is_symlink();a=pin(f.read_bytes());assert a=={'sha256':e['sha256'],'bytes':e['bytes']},str(p)
 return a
try:
 # Metadata names fixed before any copy/stage/test. Execution helpers and post-final receipts remain local-only.
 pubs={'metadata-paths.json':'NEW_PROSE_OR_METADATA','candidate-manifest.json':'NEW_PROSE_OR_METADATA','changed-paths.json':'NEW_PROSE_OR_METADATA','closure.json':'NEW_PROSE_OR_METADATA','content-review.json':'NEW_PROSE_OR_METADATA','preflight.json':'NEW_PROSE_OR_METADATA','import-receipt.json':'NEW_PROSE_OR_METADATA','candidate4-command.json':'NEW_PROSE_OR_METADATA','candidate4-result.json':'NEW_PROSE_OR_METADATA','candidate4.stdout.txt':'VERBATIM_EVIDENCE','candidate4.stderr.txt':'VERBATIM_EVIDENCE','candidate4.junit.xml':'VERBATIM_EVIDENCE','test-outcomes.json':'NEW_PROSE_OR_METADATA','temp-originals.json':'NEW_PROSE_OR_METADATA','before-after-pins.json':'NEW_PROSE_OR_METADATA','verbatim-exceptions.json':'NEW_PROSE_OR_METADATA','step-report.md':'NEW_PROSE_OR_METADATA','step-report.json':'NEW_PROSE_OR_METADATA'}
 write('metadata-paths.json',{'status':'FIXED_BEFORE_COPY_STAGE_TEST','published':[{'path':str(O/n),'semantic_role':r,'reason':'Bounded R87 candidate delivery verification evidence'} for n,r in pubs.items()],'local_only':['activation-size-observation.json','payload-parent-pre-review.json','prepare-r87.py','run-candidate4.py','finalize-r87.py','whole-check.json','strict-check.json','final-check.json','final-stage.json','commit-paths.json','commit-paths.nul','final-review.md'],'self_reference':'Metadata manifest lists names/roles without claiming its own hash. Final stage receipt local-only binds all final blobs.'})
 oldp=R89/'original/root-activation.verbatim.json';old=read(oldp);a=read(R/'root-activation.json');assert checkpin(oldp,{'bytes':10005801,'sha256':'39376d5386e9944b6fcf3e737b65862887659514e9698b5fecb217d95a7b8e74'})
 assert checkpin(R/'root-activation.json',{'bytes':10702,'sha256':'6c448fe7deec7de3145a8a7e61b53005cf15274cb11aac15c7cfe488e9855407'})
 restored=copy.deepcopy(a);digests=[]
 for pointer in a['derivation']['fields']:
  parts=pointer.strip('/').split('/');v=old;cur=restored
  for key in parts[:-1]:key=int(key) if isinstance(v,list) else key;v=v[key];cur=cur[key]
  key=parts[-1];v=v[key];d=cur[key];assert pin(v.encode())=={'sha256':d['sha256'],'bytes':d['bytes']};assert d['nonempty'] == bool(v);assert d['original']['local_only'];digests.append(d);cur[key]=v
 for key in ['receipt_representation','derived_from','derivation']:restored.pop(key)
 assert restored==old and a['receipt_representation']=='DERIVED_COMPACT_RECEIPT'
 assert a['actual_oc2_parent']==PARENT and a['worktree']==str(W) and a['candidate4_max_new_invocations']==1
 plan=read(R/'plan.json')
 for e in plan['input_pins']:checkpin(Path(e['path']),e)
 for key in ['oc2_push_receipt','plan','plan_md','candidate_manifest','candidate4_contract']:e=a[key];checkpin(Path(e['path']),e)
 payload=read(R/'candidate-input-paths.json')['entries'];assert len(payload)==82 and sum(e['bytes'] for e in payload)==381749
 for e in payload:checkpin(Path(e['path']),e)
 own={e['path'] for e in payload if e['semantic_role']=='CURRENT_EXECUTABLE'};assert len(own)==5
 prereview=read(O/'payload-parent-pre-review.json');assert prereview['missing']==[] and len(prereview['dependencies'])==281
 for d in prereview['dependencies']:
  p=Path(d['path']);root=M if str(p) in own else W;assert pin((root/p).read_bytes())==d['pin'],str(p)
  if str(p) not in own:
   q=subprocess.run(['git','show',PARENT+':'+str(p)],cwd=W,capture_output=True);assert q.returncode==0 and pin(q.stdout)==d['pin'],str(p)
 for f,n in [x.split('::') for x in read(R/'candidate4-contract.json')['nodeids']]:
  nodes=[x for x in ast.parse((M/f).read_text()).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==n];assert len(nodes)==1 and not nodes[0].decorator_list
 checks=[]
 for argv,expected in [(['git','branch','--show-current'],a['branch']),(['git','rev-parse','HEAD'],PARENT),(['git','rev-parse','@{u}'],PARENT),(['git','status','--porcelain=v1','--untracked-files=all'],'')]:
  c=cmd(argv);checks.append(c);assert c['exit_code']==0 and c['stdout'].strip()==expected
 c=cmd(['git','ls-remote','--heads','origin','refs/heads/'+a['branch']]);checks.append(c);assert c['exit_code']==0 and c['stdout'].split()[0]==PARENT
 for commit,code in [('4d40a65059ab75292fa1842bacf62653829808e6',0),('34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e',1)]:
  c=cmd(['git','merge-base','--is-ancestor',commit,'HEAD']);checks.append(c);assert c['exit_code']==code
 for argv,expected in [(['git','rev-parse','HEAD'],'34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e'),(['git','branch','--show-current'],'research/20261004-continuation')]:
  c=cmd(argv,M);checks.append(c);assert c['exit_code']==0 and c['stdout'].strip()==expected
 origins=[cmd(['git','remote','get-url','origin'],root) for root in [M,W]];assert all(c['exit_code']==0 for c in origins) and origins[0]['stdout']==origins[1]['stdout']
 origin_identity=pin(origins[0]['stdout'].strip().encode());audience=cmd(['gh','repo','view','--json','visibility'],W);assert audience['exit_code']==0
 write('preflight.json',{'status':'PASS','activated_parent':PARENT,'compact_activation_pin':pin((M/R/'root-activation.json').read_bytes()),'derived_receipt_verified':True,'four_field_digests_verified':digests,'other_fields_deep_equal':True,'original_local_only':str(oldp),'commands':checks,'origin_same_main_and_candidate':True,'origin_redacted_identity':origin_identity,'audience':json.loads(audience['stdout']),'primary_mutations':0,'nested_workspace_mutations':0,'nested_status_not_rerun':'R89 stored-text digests retained; no giant status repetition'})
 write('closure.json',{'status':'PASS','activated_parent':PARENT,'override_paths':sorted(own),'dependency_count':281,'dependencies':prereview['dependencies'],'fixture_source_read_paths':prereview['fixture_source_read_paths'],'literal_dynamic_import_candidates':prereview['literal_dynamic_import_candidates'],'external_modules':prereview['external_modules'],'missing':[],'parent_bytes_verified':True,'primary_other_source_imports':0,'old_transport_raw_read_hash_copy':0,'review_basis':'Reused completed recursive AST/init/fixture/literal dynamic import pre-review, rechecked every virtual source pin and every non-owned dependency against activated parent Git blob.'})
 entries=[]
 for e in payload:entries.append(dict(e,source=str(M/e['path']),frozenSha=e['sha256'],mode=format(stat.S_IMODE((M/e['path']).stat().st_mode),'04o')))
 for n in ['plan.md','plan.json','input-pins.json','candidate-input-paths.json','readonly-observation.json','candidate4-contract.json','root-activation.json']:
  p=R/n;b=(M/p).read_bytes();b.decode();
  if n.endswith('.json'):json.loads(b)
  entries.append(dict(path=str(p),source=str(M/p),**pin(b),frozenSha=pin(b)['sha256'],mode=format(stat.S_IMODE((M/p).stat().st_mode),'04o'),semantic_role='NEW_PROSE_OR_METADATA',reason='Exact R87 plan/activation metadata; compact activation is a derived receipt, original local-only'))
 assert len(entries)==89
 changed=[];same=[]
 for e in entries:
  p=Path(e['path']);target=W/p;q=subprocess.run(['git','show',PARENT+':'+str(p)],cwd=W,capture_output=True)
  parentpin=pin(q.stdout) if q.returncode==0 else None
  e['parent_pin']=parentpin;e['changed']=parentpin!={'sha256':e['sha256'],'bytes':e['bytes']}
  (changed if e['changed'] else same).append(e['path'])
 write('candidate-manifest.json',{'status':'FROZEN_PAYLOAD_AND_R87_SELECTION','activated_parent':PARENT,'payload_entries':82,'r87_metadata_entries':7,'entries':entries,'metadata_names':str(O/'metadata-paths.json'),'not_complete_remote_reproduction_package':True})
 write('changed-paths.json',{'payload_and_r87_changed':changed,'already_parent_same':same,'new_preparation_metadata_paths':[str(O/n) for n in pubs],'final_staged_bindings':'Written local-only after last stage; no self-hash loop.'})
 write('content-review.json',{'status':'PASS_FINITE_EXPLICIT_SCOPE','payload_entries':prereview['payload_content_review'],'r87_metadata':[{'path':e['path'],'pin':{'sha256':e['sha256'],'bytes':e['bytes']},'role':e['semantic_role'],'review':'UTF8/JSON plans and compact derived receipt; exact seven bounded metadata; original status/large R89 receipt omitted; no actual credential identified.'} for e in entries[82:]],'origin_same':True,'origin_redacted_identity':origin_identity,'audience':json.loads(audience['stdout']),'review_scope':'Only exact 82 payload plus seven R87 files and bounded new evidence; no whole repository sensitive scan.'})
 # Only explicitly enumerated changed payload copied; no directory glob expansion.
 for e in entries:
  if not e['changed']:continue
  p=Path(e['path']);target=W/p;assert not target.is_symlink();target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(M/p,target);assert pin(target.read_bytes())=={'sha256':e['sha256'],'bytes':e['bytes']};assert format(stat.S_IMODE(target.stat().st_mode),'04o')==e['mode']
 env=os.environ.copy();env.update(PYTHONPATH=str(W/'src')+':'+str(W),PYTHONDONTWRITEBYTECODE='1')
 proof="""import importlib,json,pathlib,sys,hashlib
w=pathlib.Path.cwd()
for n in ['cloud_edge_robot_arm.vision.native_references','cloud_edge_robot_arm.vision.native_calibration','cloud_edge_robot_arm.research.native_geometry_calibration','tests.test_native_references','tests.test_native_calibration_source']:importlib.import_module(n)
rows=[]
for n,m in list(sys.modules.items()):
 if not(n=='cloud_edge_robot_arm' or n.startswith('cloud_edge_robot_arm.') or n=='tests' or n.startswith('tests.')):continue
 f=getattr(m,'__file__',None)
 if not f:continue
 p=pathlib.Path(f).resolve();assert p.is_relative_to(w),(n,str(p));b=p.read_bytes();rows.append({'module':n,'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
print(json.dumps({'status':'PASS_CANDIDATE_IMPORT_ORIGINS','sys_path':sys.path,'modules':rows,'candidate':str(w)}))
"""
 q=subprocess.run([str(PY),'-c',proof],cwd=W,env=env,capture_output=True)
 write('import-receipt.json',{'argv':[str(PY),'-c',proof],'cwd':str(W),'env':{k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},'exit_code':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode(),'tests':0})
 assert q.returncode==0,q.stderr.decode()
 imports=json.loads(q.stdout);assert all(str(W) in x['path'] for x in imports['modules'])
 print(json.dumps({'stage':'COPY_AND_IMPORT_READY','payload_and_r87_changed':len(changed),'already_parent_same':len(same),'imported_candidate_modules':len(imports['modules']),'candidate4_invocations':0,'git_stage_commit_push':0}))
except Exception as exc:
 p=M/O/'preparation-failure-resume.json';assert not p.exists();p.write_text(json.dumps({'failure':repr(exc),'phase':'pre-copy/copy/import','candidate4_invocations':0,'no_self_repair':True},indent=2)+'\n');raise
