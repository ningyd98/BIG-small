from pathlib import Path
import ast,hashlib,json,re,subprocess,datetime,sys
MAIN=Path.cwd();B=Path('artifacts/research/process/20261004-ced-development');H=B/'t12-sol-handoff-20261007';O=H/'delivery-oc2';W=Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall'); HEAD='3daddcc96c1d23e928fb4c9a3d868750b6cc37ec';BASE='4d40a65059ab75292fa1842bacf62653829808e6';USER='34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e';BRANCH='codex/research-20261007-p1-delivery';O.mkdir(exist_ok=False)
def pin(p):
 r=Path(p).read_bytes();return {'sha256':hashlib.sha256(r).hexdigest(),'bytes':len(r)}
def save(n,v):
 with (O/n).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def run(args,cwd=W):
 r=subprocess.run(args,cwd=cwd,capture_output=True);return {'argv':args,'cwd':str(cwd),'exit':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode()}
def must(args,cwd=W,code=0):
 r=run(args,cwd);commands.append(r);assert r['exit']==code,r['argv'];return r['stdout'].strip()
commands=[]
try:
 assert must(['git','rev-parse','HEAD'])==HEAD
 assert must(['git','symbolic-ref','--short','HEAD'])==BRANCH
 assert must(['git','status','--porcelain=v1','-z','--untracked-files=all'])==''
 assert must(['git','rev-parse','@{upstream}'])==HEAD
 must(['git','merge-base','--is-ancestor',BASE,'HEAD']);must(['git','merge-base','--is-ancestor',USER,'HEAD'],code=1)
 assert must(['git','rev-parse','HEAD'],MAIN)==USER
 assert must(['git','rev-parse','@{upstream}'],MAIN)==BASE
 nested=must(['git','status','--short','--untracked-files=no','--','physics/workspace-baseline','physics/workspace-h3'],MAIN)
 remote=must(['git','ls-remote','--heads','origin','refs/heads/'+BRANCH,'refs/heads/research/20261004-continuation'])
 assert set(remote.splitlines())=={HEAD+'\trefs/heads/'+BRANCH,BASE+'\trefs/heads/research/20261004-continuation'}
 urls=[]
 for cwd in [W,MAIN]:
  r=run(['git','remote','get-url','origin'],cwd);assert r['exit']==0;urls.append(r['stdout'].strip())
 assert urls[0]==urls[1]
 repo=run(['gh','repo','view','--json','visibility,nameWithOwner']);assert repo['exit']==0;j=json.loads(repo['stdout']);assert j['visibility']=='PUBLIC'
 origin={'same_destination':True,'visibility':'PUBLIC','host':'github.com','redacted_identity':'github.com/<existing-project>','identity_digest_algorithm':'SHA256 of gh nameWithOwner UTF8','repository_identity_sha256':hashlib.sha256(j['nameWithOwner'].encode()).hexdigest(),'raw_remote_url_not_published':True,'readonly_network_queries':['git ls-remote heads','gh repo view metadata']}
 plans=[]
 for n in ['round77-git-delivery-boundary-20261007','round81-git-verbatim-evidence-20261007','round83-git-policy-prerequisite-20261007']:
  p=B/'astra-rounds'/n/'plan.json';j=json.loads(p.read_text());rows=j['input_pins'];rows=[{'path':s,**e} for s,e in rows.items()] if isinstance(rows,dict) else rows
  for e in rows:assert pin(e['path'])=={k:e[k] for k in ['sha256','bytes']}
  plans.append({'plan':str(p),'pin':pin(p),'verified_inputs':len(rows),'authorization_pin':pin(p.parent/'root-authorization.json')})
 accepted=json.loads((H/'oc2-root-acceptance-round82.json').read_text());sources=accepted['current_source_freeze'];assert len(sources)==9
 for s,e in sources.items():assert pin(s)==e
 save('preflight.json',{'status':'PASS_PREFLIGHT_EXPECTED_RW1_POST_PUSH_HEAD','base':BASE,'increment_parent':HEAD,'branch':BRANCH,'main_head':USER,'main_upstream':BASE,'origin':origin,'plans':plans,'commands':commands,'nested_status':nested,'commit_push_by_preparer':0,'actual':0})
 rounds=[('R67',B/'astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007'),('R74',B/'astra-rounds/round74-oc2-static-typing-20261007/implementation'),('R75',B/'astra-rounds/round75-oc2-residual-type-20261007/implementation'),('R79',B/'astra-rounds/round79-oc2-backend-config-type-20261007/implementation'),('R80',B/'astra-rounds/round80-oc2-review-repair-20261007/implementation'),('R82',B/'astra-rounds/round82-oc2-review-format-20261007/implementation')]
 selected={};excluded=[];poolinfo=[]
 for s in sources:selected[s]=('CURRENT_EXECUTABLE','Complete independent-accepted OC2 source/config; scoped source/static/JUnit proof bound to exact bytes.','ROOT R82 acceptance')
 metadata={'step-report.md','step-report.json','delivery-paths.txt','author-transfer.json','author.json'}
 proofnames={'source-freeze.json','format-equivalence.json','restricted-ast-proof.json','plan-authorization-pins.json','authorization-pins.json','failure-receipt.json','new-static-failure-receipt.json','historical-evidence-before.json','failure-taxonomy.json','test-outcomes.json','red-outcomes.json','targeted-outcomes.json','test-run-absence.json','pre-RED-proof.json','unrun-verifications.json','run-ledger.json','increment-chain.json','report-evidence-pins.json'}
 diffnames={'test_operational_capture_v1.py.round67.diff','operational_capture_v1.py.handoff.diff','operational_prefix_v1.py.round67.diff','operational_capture_v1.py.round67.diff','test_operational_capture_v1.py.handoff.diff','operational_prefix_v1.py.handoff.diff','operational_capture_v1.py.diff','operational_prefix_v1.py.diff','test_operational_prefix_cli_v1.py.diff','worker.py.diff','source.diff','test_operational_capture_v1.py.diff','operational_prefix_v1.py.R80-R82-combined.diff','test_operational_capture_v1.py.R80-R82-combined.diff'}
 # Raw file manifests are necessary denominator records; references remain explicitly local-only.
 denomnames={'cpu-originals-denominator.json','red-cpu-originals.json','targeted-cpu-originals.json','R03-cpu-originals.json'}
 phases={'full_GREEN','ruff_check','ruff_format_check','mypy','format_write','config_RED','targeted_CPU','R03_regression','review_RED','review_GREEN','formatter'}
 rawcommands={phase+'.'+suffix for phase in phases for suffix in ['command-start.json','command-result.json','stdout.txt','stderr.txt','junit.xml']}
 for label,p in rounds:
  pool=(p/'delivery-paths.txt').read_text().splitlines();poolinfo.append({'round':label,'path':str(p/'delivery-paths.txt'),'pin':pin(p/'delivery-paths.txt'),'files':len(pool)})
  # The table itself has frozen metadata value even when its own author list omitted it.
  selected[str(p/'delivery-paths.txt')]=('NEW_PROSE_OR_METADATA','Original bounded author candidate pool; chosen subset explicitly recorded, references do not assert publication.','Explicit '+label+' pool')
  for s in pool:
   if s in sources:continue
   name=Path(s).name
   snapshot='/source-before/' in s or '/source-after/' in s or '/round67-source-before/' in s
   allowed=name in metadata|proofnames|diffnames|denomnames|rawcommands or snapshot
   if not allowed:
    excluded.append({'path':s,'reason':'Procedural duplicate, historical non-reused executable, transient progress/precheck or local-only path list not necessary to reproduce this scoped review.','pin':pin(s)});continue
   if snapshot:
    role='VERBATIM_EVIDENCE';reason='Frozen full source audit specimen; not executed/imported as current implementation.'
   elif name in metadata:
    role='NEW_PROSE_OR_METADATA';reason='Original scoped author narrative/delivery provenance; receives strict whitespace check.'
   else:
    role='VERBATIM_EVIDENCE';reason='Frozen raw command/stdout/XML/diff/failure/scope/denominator receipt; preserves exact original bytes, local raw references remain local.'
   selected[s]=(role,reason,'Explicit '+label+' pool')
 for n in ['round60-operational-oc2','round67-oc2-green-partials','round74-oc2-static-typing-20261007','round75-oc2-residual-type-20261007','round79-oc2-backend-config-type-20261007','round80-oc2-review-repair-20261007','round82-oc2-review-format-20261007']:
  p=B/'astra-rounds'/n
  for f in ['plan.md','plan.json','root-authorization.json','activation.json']:
   q=p/f
   if q.exists():selected[str(q)]=('NEW_PROSE_OR_METADATA','Necessary actual scoped behavior/type/repair/format plan and activation/authorization.','Bounded additional planning provenance')
 for s in ['oc2-independent-review/preliminary-review.md','oc2-independent-review/preliminary-review.json','oc2-independent-review/round82-final-review.md','oc2-independent-review/round82-final-review.json','oc2-root-acceptance-round82.json','delivery-rw1/root-delivery.json']:
  selected[str(H/s)]=('NEW_PROSE_OR_METADATA','Final distinct-author review/ROOT software acceptance or prior exact post-push receipt; original commit referenced without amendment.','ROOT authorized signing/post-push provenance')
 # Exact reviewed successful startup source inventory gives old dependency byte basis without consulting active P2.
 R82=rounds[-1][1];denom=json.loads((R82/'cpu-originals-denominator.json').read_text());row=next(r for r in denom['files'] if r['original_path'].endswith('startup-inputs.json'));assert pin(row['original_path'])=={k:row[k] for k in ['sha256','bytes']};inventory=json.loads(Path(row['original_path']).read_text())['source_inventory']
 p2=['src/cloud_edge_robot_arm/vision/native_references.py','src/cloud_edge_robot_arm/vision/native_calibration.py','src/cloud_edge_robot_arm/research/native_geometry_calibration.py','tests/test_native_references.py','tests/test_native_calibration_source.py']
 def virtual(s):return MAIN/s if s in sources else W/s
 dependencies=set(inventory)|set(sources)|{'pyproject.toml','tests/__init__.py','tests/test_native_clock_prefix_worker_v2.py','tests/test_native_clock_publication_v2.py','tests/test_native_reset_capture_v2.py','tests/test_native_clock_prefix_cli_v2.py'}
 queue=list(dependencies);seen=set();external=set();missing=[]
 def modules(name):
  if not name.startswith(('cloud_edge_robot_arm','tests')):external.add(name.split('.')[0]);return []
  root='src/' if name.startswith('cloud_edge_robot_arm') else '';stem=root+name.replace('.','/');found=[]
  for s in [stem+'.py',stem+'/__init__.py']:
   if virtual(s).is_file():found.append(s)
  for i in range(1,len(name.split('.'))):
   s=root+'/'.join(name.split('.')[:i])+'/__init__.py'
   if virtual(s).is_file():found.append(s)
  return found
 while queue:
  s=queue.pop()
  if s in seen:continue
  seen.add(s);q=virtual(s)
  if not q.is_file():missing.append(s);continue
  if q.suffix!='.py':continue
  t=ast.parse(q.read_text(),type_comments=True);module=s.removeprefix('src/').removesuffix('.py').replace('/','.');package=module.removesuffix('.__init__') if module.endswith('.__init__') else module.rsplit('.',1)[0]
  for node in ast.walk(t):
   if isinstance(node,ast.Import):
    for alias in node.names:queue.extend(modules(alias.name))
   elif isinstance(node,ast.ImportFrom):
    mod=node.module or ''
    if node.level:
     pieces=package.split('.');mod='.'.join([*pieces[:len(pieces)-node.level+1],*([mod] if mod else [])])
    queue.extend(modules(mod))
    for alias in node.names:
     if alias.name!='*':queue.extend(modules(mod+'.'+alias.name))
 assert not missing,missing
 expected_tests={e['path']:{k:e[k] for k in ['sha256','bytes']} for e in json.loads((rounds[3][1].parent/'plan.json').read_text())['inputs'] if e['path'].startswith('tests/')}
 closure=[]
 for s in sorted(seen):
  actual=pin(virtual(s));expected=sources.get(s,inventory.get(s,expected_tests.get(s)));old=pin(W/s) if (W/s).is_file() else None
  if expected is not None:assert actual==expected,(s,'reviewed dependency drift')
  if s not in sources:assert old==actual,(s,'candidate old dependency missing')
  closure.append({'path':s,'pin':actual,'HEAD_pin':old,'action':'IMPORT_COMPLETE_FINAL_FILE' if s in sources and actual!=old else 'ALREADY_IN_ACCEPTED_HEAD','reviewed_inventory_pin':expected,'P2_active_source_avoided':s in p2})
 save('closure.json',{'status':'PASS_STATIC_CANDIDATE_CLOSURE','inventory_original_path':row['original_path'],'inventory_original_pin':{k:row[k] for k in ['sha256','bytes']},'dependency_count':len(closure),'dependencies':closure,'external_modules':sorted(external),'P2_active_paths':p2,'P2_imports':0,'not_actual_readiness':True,'test_dependency':'46cases use synthetic CPU inputs from imported tests or already accepted HEAD; no big raw/DB originals needed.'})
 patterns={'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','github_token':rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b','openai_key':rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b','aws_access_key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b','credential_url':rb'https?://[^\s/:]+:[^\s/@]+@'}
 entries=[];reviews=[]
 for s,(role,reason,version) in sorted(selected.items()):
  q=Path(s);assert not q.is_absolute() and '..' not in q.parts and q.is_file();assert not any(x.is_symlink() for x in [q,*q.parents]);assert not any(v in s for v in ['local-cpu-originals/','runtime.db','physics/workspace','.venv/']);assert q.suffix not in ['.png','.gz','.f32','.db']
  raw=q.read_bytes();hits=[k for k,pat in patterns.items() if re.search(pat,raw)]
  if hits:save('sensitive-content-stop.json',{'path':s,'categories':hits,'secret_values_printed':False});raise RuntimeError('Sensitive candidate content; stopped before copy.')
  text=raw.decode('utf-8')
  if q.suffix=='.json':json.loads(text)
  if role=='CURRENT_EXECUTABLE' and q.suffix=='.py':ast.parse(text,type_comments=True)
  mode='100755' if q.stat().st_mode&0o111 else '100644';info=pin(q);old=(W/s).read_bytes() if (W/s).is_file() else None
  entries.append({'path':s,'source':str((MAIN/q).absolute()),'frozenSha256':info['sha256'],'bytes':info['bytes'],'mode':mode,'reason':reason,'semantic_role':role,'source_version':version,'relative_to_HEAD_changed':old!=raw,'change':'M' if old is not None else 'A'})
  reviews.append({'path':s,'utf8':True,'JSON_parsed':q.suffix=='.json','semantic_role':role,'credential_pattern_hits':[],'content_review':'Existing public project source, original CPU paths/machine labels and scoped source/failure/delivery context; no sensitive payload category identified. Candidate-only review.'})
 save('candidate-paths.json',{'status':'FROZEN_OC2_PAYLOAD','base':BASE,'increment_parent':HEAD,'branch':BRANCH,'entries':entries,'path_count':len(entries),'bytes':sum(e['bytes'] for e in entries),'source_pools':poolinfo,'excluded':excluded,'metadata_policy':'Payload excludes new delivery metadata; metadata pinned separately. Final check/tree receipts local-only after last stage, no self-rewriting.','local_only':'Complete /tmp raw/DB/CPU copies, credentials/weights/SDK, P2 activities and global summaries excluded. Frozen original references remain honest, not an assertion of remote presence.'})
 (O/'candidate-paths.nul').open('xb').write(b'\0'.join(e['path'].encode() for e in entries)+b'\0')
 save('content-review.json',{'status':'PASS_SCOPED_CONTENT_REVIEW','files':reviews,'origin':origin,'scope':'Exact candidate-only review; no all-repository claim; original evidence unchanged.'})
 for e in entries:
  q=W/e['path'];q.parent.mkdir(parents=True,exist_ok=True);raw=Path(e['source']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['frozenSha256'];q.write_bytes(raw);q.chmod(0o755 if e['mode']=='100755' else 0o644);assert pin(q)=={'sha256':e['frozenSha256'],'bytes':e['bytes']}
 save('payload-import.json',{'status':'EXACT_BYTES_IMPORTED','files':len(entries),'changed':sum(e['relative_to_HEAD_changed'] for e in entries),'bytes':sum(e['bytes'] for e in entries),'dependencies':len(closure),'stage':0,'commit_push':0,'main_product_writes':0})
 print(json.dumps({'status':'IMPORTED_NOT_STAGED','files':len(entries),'changed':sum(e['relative_to_HEAD_changed'] for e in entries),'bytes':sum(e['bytes'] for e in entries),'dependencies':len(closure)}))
except BaseException as e:
 save('preparation-failure-1.json',{'status':'STOPPED_PLAN_UNEXPECTED_FAILURE','error_type':type(e).__name__,'error':str(e),'commands':commands,'commit_push':0,'no_self_repair':True});raise
