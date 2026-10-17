from pathlib import Path
import hashlib,json,os,re,shutil,stat,subprocess
M=Path('/home/ningyd/文档/ChatGPT/BIGsmall');W=Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall');B=Path('artifacts/research/process/20261004-ced-development');O=B/'t12-sol-handoff-20261007/delivery-p2';PARENT='98b8282138ba61367db526d7d8f52e27085f4f9f'
def pin(b):return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def read(n):return json.loads((M/O/n).read_text())
def write(n,d):
 p=M/O/n;assert not p.exists();p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def git(args):return subprocess.run(['git',*args],cwd=W,capture_output=True)
def receipt(q,args):return {'argv':['git',*args],'cwd':str(W),'exit_code':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode(),'stdout_pin':pin(q.stdout),'stderr_pin':pin(q.stderr)}
def check(args):q=git(args);return q,receipt(q,args)
def copy_meta(rows):
 for e in rows:
  p=Path(e['path']);f=M/p;assert f.is_file() and not f.is_symlink();t=W/p;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,t);assert f.read_bytes()==t.read_bytes()
try:
 assert read('candidate4-result.json')['status']=='PASS_EXPORTED_CANDIDATE4'
 manifest=read('candidate-manifest.json');decl=read('metadata-paths.json')['published'];assert len(decl)==18
 entries=manifest['entries']+[dict(x,source=str(M/x['path'])) for x in decl];mapping={e['path']:e for e in entries};assert len(mapping)==107
 changed=read('changed-paths.json');expected=sorted(changed['payload_and_r87_changed']+[e['path'] for e in decl]);assert len(expected)==107
 assert git(['rev-parse','HEAD']).stdout.decode().strip()==PARENT and git(['diff','--cached','--name-only','-z']).stdout==b''
 initial_meta=[e for e in decl if Path(e['path']).name not in ['verbatim-exceptions.json','step-report.md','step-report.json']];copy_meta(initial_meta)
 initialpaths=sorted(changed['payload_and_r87_changed']+[e['path'] for e in initial_meta]);q=git(['add','--',*initialpaths]);assert q.returncode==0,q.stderr.decode()
 whole,whole_r=check(['diff','--cached','--check']);write('whole-check.json',whole_r)
 assert whole.returncode in [0,2] and whole.stderr==b''
 strictpaths=sorted(p for p in initialpaths if mapping[p]['semantic_role']!='VERBATIM_EVIDENCE');strict,strict_r=check(['diff','--cached','--check','--',*strictpaths]);write('strict-check.json',dict(strict_r,paths=strictpaths));assert strict.returncode==0
 diagnostics=[];unclassified=[];lines=whole.stdout.decode().splitlines();i=0
 while i<len(lines):
  line=lines[i];match=re.fullmatch(r'(.+):(\d+): (.+)',line)
  if not match:unclassified.append(line);i+=1;continue
  path,num,kind=match.group(1),int(match.group(2)),match.group(3);assert path in mapping,path;e=mapping[path]
  if e['semantic_role']!='VERBATIM_EVIDENCE':unclassified.append(line)
  source=Path(e['source']);src=source.read_bytes();stagedq=git(['show',':'+path]);assert stagedq.returncode==0;staged=stagedq.stdout;assert src==staged
  filelines=staged.splitlines(keepends=True);assert 1<=num<=len(filelines);bline=filelines[num-1];context=None
  if i+1<len(lines) and lines[i+1].startswith('+'):context=lines[i+1];i+=1;assert context[1:]==bline.decode().rstrip('\r\n')
  assert kind in ['trailing whitespace.','new blank line at EOF.','space before tab in indent.'],kind
  diagnostics.append({'diagnostic':line,'diagnostic_kind':kind,'staged_path':path,'staged_line':num,'source':str(source),'semantic_role':e['semantic_role'],'source_pin':pin(src),'staged_pin':pin(staged),'original_staged_line_pin':pin(bline),'git_context':context,'classification':'R81 VERBATIM_EVIDENCE original bytes retained; no stripping or Git attributes/config suppression.'});i+=1
 assert not unclassified,unclassified
 write('verbatim-exceptions.json',{'status':'EXHAUSTIVE_R81_VERBATIM_MAPPING','whole_check_local_receipt':str(O/'whole-check.json'),'whole_exit':whole.returncode,'whole_stdout_pin':pin(whole.stdout),'exception_count':len(diagnostics),'diagnostics':diagnostics,'unclassified':unclassified,'strict_current_executable_and_new_prose_exit':strict.returncode,'strict_initial_path_count':len(strictpaths),'source_original_modified':False})
 report={'status':'PREPARED_FOR_ROOT_FINAL_INDEX_REVIEW','parent':PARENT,'branch':'codex/research-20261007-p1-delivery','worktree':str(W),'payload_paths':82,'r87_metadata_paths':7,'new_metadata_paths':18,'changed_paths_expected':107,'candidate4':read('candidate4-result.json'),'closure_count':281,'current_source_overrides':5,'actual_candidate_imported_modules':145,'whole_check_initial_exit':whole.returncode,'strict_initial_exit':strict.returncode,'verbatim_exceptions':len(diagnostics),'unclassified':0,'git_mutations':'Explicit path stage only; main tree0, commit0, push0','original94_evidence':'93 original pass plus R85 one repaired pass covers94 unique; not94 rerun','local_only':'R88/R89 full rounds, original10MB activation, helper scripts,51CPU temporary files/raw/DB and old transport raw; no complete raw remote package','boundaries':{'GRASP_mutable':'NOT_SUPPORTED/UNKNOWN','full_future_D':'NOT_SUPPORTED/UNKNOWN','native':'UNAVAILABLE','calibration_groups':0,'actual':0,'formal_accepted':False,'nine_groups':'paused'},'final_index_receipts':'Final whole/strict/tree and all per-blob bindings written local-only after final stage, avoiding self-hash cycle. ROOT must independently verify then commit/push.'}
 write('step-report.json',report)
 text=f"""# P2 candidate preparation

Prepared exact R87 scope for ROOT's final index review:82 frozen payload paths, seven R87 metadata files,18 declared preparation evidence files. Parent is `{PARENT}` on `codex/research-20261007-p1-delivery`. R89 compact activation verified against the untouched local-only original; it records stored observations, without rerunning giant nested status commands.

The five accepted sources plus281 recursively reviewed project/test dependencies match the activated parent or exact five overrides. Actual import proof resolves145 project/test modules inside the candidate worktree. The single authorized candidate4 invocation passed4 unique nodes,0 failure/error/skip. Every dependency pin is unchanged afterward;51 temporary original files remain local-only. Original software evidence remains93 original passes plus one R85 repair pass covering94 unique cases, without94 rerun.

Initial whole cached check exit{whole.returncode}; strict current source/new prose subset exit{strict.returncode}. Every {len(diagnostics)} original whitespace diagnostic is bound to its VERBATIM source, staged file and original line hash; unclassified0. Full final checks and exact index tree/blob/path bindings are local-only receipts after final stage to avoid self-reference. ROOT independently verifies and performs commit/non-force push. This preparer commits0/pushes0 and leaves main branch and nested dirty trees untouched.

Only exact listed small evidence is included. R88/R89 full rounds, original10MB activation, runners, CPU originals, raw/DB/weights/SDK and unrelated primary files remain local-only. This is not a complete remote raw reproduction package. GRASP/mutable and full-future D remain NOT_SUPPORTED/UNKNOWN, native UNAVAILABLE, calibration0, actual0, formal=false; the nine dependent groups remain paused.
"""
 (M/O/'step-report.md').write_text(text)
 late=[e for e in decl if e not in initial_meta];copy_meta(late);q=git(['add','--',*[e['path'] for e in late]]);assert q.returncode==0
 actual=sorted(x.decode() for x in git(['diff','--cached','--name-only','-z']).stdout.split(b'\0') if x);assert actual==expected
 finalwhole,fw=check(['diff','--cached','--check']);finalstrictpaths=sorted(p for p in expected if mapping[p]['semantic_role']!='VERBATIM_EVIDENCE');finalstrict,fs=check(['diff','--cached','--check','--',*finalstrictpaths]);assert finalstrict.returncode==0;assert finalwhole.returncode==whole.returncode and finalwhole.stdout==whole.stdout and finalwhole.stderr==whole.stderr
 assert git(['diff','--name-only','-z']).stdout==b'', 'Unstaged candidate edits'
 status=git(['status','--porcelain=v1','--untracked-files=all']);assert status.returncode==0
 assert all(not x.startswith('??') for x in status.stdout.decode().splitlines()),'Unexpected untracked'
 bindings=[]
 for p in expected:
  e=mapping[p];f=Path(e['source']);source=f.read_bytes();staged=git(['show',':'+p]);assert staged.returncode==0 and staged.stdout==source and (W/p).read_bytes()==source
  ls=git(['ls-files','--stage','--',p]);assert ls.returncode==0;mode,blob,stage=ls.stdout.decode().split('\t')[0].split();assert mode in ['100644','100755'] and stage=='0';assert mode==('100755' if f.stat().st_mode&0o111 else '100644');assert not f.is_symlink() and not (W/p).is_symlink()
  if p in {x['path'] for x in manifest['entries']}:assert pin(source)=={'sha256':e['sha256'],'bytes':e['bytes']}
  bindings.append({'path':p,'source':str(f),'frozenSha':pin(source)['sha256'],'bytes':len(source),'mode':mode,'blob':blob,'semantic_role':e['semantic_role'],'reason':e['reason']})
 for d in read('closure.json')['dependencies']:assert pin((W/d['path']).read_bytes())==d['pin']
 tree=git(['write-tree']);assert tree.returncode==0
 write('final-check.json',{'whole':fw,'strict':dict(fs,paths=finalstrictpaths),'same_whole_diagnostics_after_final_stage':True,'exceptions':len(diagnostics),'unclassified':0,'metadata_content_review':'All18 explicitly generated finite JSON/prose or original4-case stdout/stderr/JUnit, no credentials/raw/db copied; CURRENT and NEW strict validated.','candidate_source_dependency_pins_still_match':True,'unstaged_empty':True,'no_untracked':True,'main_mutations':0,'commit_push':0})
 write('commit-paths.json',{'paths':expected,'path_count':len(expected),'parent':PARENT,'tree':tree.stdout.decode().strip()});(M/O/'commit-paths.nul').write_bytes(b'\0'.join(p.encode() for p in expected)+b'\0')
 write('final-stage.json',{'status':'STAGE_READY_FOR_ROOT','parent':PARENT,'branch':'codex/research-20261007-p1-delivery','worktree':str(W),'index_tree':tree.stdout.decode().strip(),'path_count':len(bindings),'logical_blob_bytes':sum(x['bytes'] for x in bindings),'entries':bindings,'whole_exit':finalwhole.returncode,'strict_exit':finalstrict.returncode,'strict_paths':len(finalstrictpaths),'verbatim_exception_count':len(diagnostics),'unclassified':0,'candidate4_invocations':1,'candidate4_unique_passed':4,'commit_push':0,'local_only_after_final_stage':True})
 (M/O/'final-review.md').write_text(f"Stage-ready for ROOT. Parent {PARENT}; index tree {tree.stdout.decode().strip()}; {len(bindings)} explicit changed paths; {sum(x['bytes'] for x in bindings)} logical blob bytes. Candidate4 once:4unique/4pass. Whole exit{finalwhole.returncode}, strict exit{finalstrict.returncode}, {len(diagnostics)} VERBATIM original whitespace exceptions, unclassified0. Final exact path/mode/blob/SHA bindings in final-stage.json and commit-paths.json. No commit/push or main/nested mutations. Post-final receipts local-only.\n")
 print(json.dumps({'status':'STAGE_READY','tree':tree.stdout.decode().strip(),'paths':len(bindings),'bytes':sum(x['bytes'] for x in bindings),'whole_exit':finalwhole.returncode,'strict_exit':finalstrict.returncode,'exceptions':len(diagnostics),'unclassified':0}))
except Exception as exc:
 p=M/O/'finalize-failure.json';assert not p.exists();p.write_text(json.dumps({'failure':repr(exc),'stop_for_astra':True,'no_self_repair':True},indent=2)+'\n');raise
