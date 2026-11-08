"""Stage only five artifact directories in a private Git index and audit every blob."""
import hashlib,json,os,re,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[5]; BASE=HERE.parent
CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
NAMES=['round486-taichu-no-think-best-profile-20261108','round487-taichu-config-evidence-serialization-20261108','round488-taichu-json-native-subclasses-20261108','round489-taichu-isolated-jit-headers-20261108','round490-taichu-delivery-frozen-whitespace-20261108']
BRANCH='codex/taichu-no-think-best-profile-20261108'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def git(args,env=None,check=True):return subprocess.run(['git']+args,cwd=ROOT,env=env,capture_output=True,check=check)
def snapshot():
 index=Path(git(['rev-parse','--git-path','index']).stdout.decode().strip()).resolve()
 return {'HEAD':git(['rev-parse','HEAD']).stdout.decode().strip(),'index_path':str(index),'index_sha256':sha(index),'unrelated_service_sha256':sha(ROOT/'src/cloud_edge_robot_arm/model_control/service.py')}
def actual_files():return sorted(str(p.relative_to(ROOT)) for name in NAMES for p in (BASE/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and not p.name.endswith('.local.json'))
state=read(CACHE/'delivery-index-round486.json');parent=state['parent'];assert parent=='8b4a88bde7de996a44a119115dc2f735bdad5807'
env=os.environ.copy();env['GIT_INDEX_FILE']=state['index'];before=snapshot()
assert read(HERE/'final-validation.json')['status']=='PASS_SOFTWARE_AND_EVIDENCE_AUDIT'
exceptions=read(HERE/'plan.json')['exact_frozen_whitespace_exceptions'];allowed={x['path'] for x in exceptions}
for item in exceptions:assert sha(ROOT/item['path'])==item['sha256']
files=actual_files();git(['add','--']+files,env)
def checks(paths,label):
 whole=git(['diff','--cached','--check',parent,'--']+paths,env,False)
 clean_paths=[p for p in paths if p not in allowed]
 clean=git(['diff','--cached','--check',parent,'--']+clean_paths,env,False)
 offenders=set()
 for line in whole.stdout.decode().splitlines():
  match=re.match(r'(.+?):\d+: (?:trailing whitespace|new blank line at EOF)',line)
  if match:offenders.add(match.group(1))
 assert whole.returncode==2 and clean.returncode==0,(whole.returncode,clean.returncode,clean.stdout.decode())
 assert offenders<=allowed,offenders-allowed
 for kind,data in [('unfiltered-stdout',whole.stdout),('unfiltered-stderr',whole.stderr),('scoped-stdout',clean.stdout),('scoped-stderr',clean.stderr)]:
  (CACHE/('delivery-'+label+'-'+kind+'.log')).write_bytes(data)
 return {'full_whitespace_check':'KNOWN_FROZEN_EVIDENCE_FAILURE','full_returncode':whole.returncode,'scoped_default_check_returncode':clean.returncode,'offender_paths':sorted(offenders),'exact_frozen_exception_paths':sorted(allowed),'nonexception_paths':clean_paths,'nonexception_paths_nul_sha256':hashlib.sha256(b'\0'.join(p.encode() for p in clean_paths)+b'\0').hexdigest(),'unfiltered_stdout_sha256':hashlib.sha256(whole.stdout).hexdigest()}
first=checks(files,'initial')
audit_names=['delivery-selection.json','delivery-verification.json','step-report.json','step-report.md','phase-summary.md']
audit_paths={str((HERE/name).relative_to(ROOT)) for name in audit_names}
allpaths=sorted(set(files)|audit_paths)
assert all(any(p.startswith(str((BASE/name).relative_to(ROOT))+'/') for name in NAMES) for p in allpaths)
manifest={'parent':parent,'branch':BRANCH,'selected_paths':allpaths,'selected_file_count':len(allpaths),'scope':NAMES,'payload_files':[{'path':p,'bytes':(ROOT/p).stat().st_size,'sha256':sha(ROOT/p)} for p in files if p not in audit_paths],'manifest_self_reference_rule':'five audit files are listed in selected_paths but excluded from internal SHA list; all staged blobs including them are independently checked and bound by Git tree','excluded_internal_sha_paths':sorted(audit_paths),'full_raw_remote_reproduction_package':False}
save(HERE/'delivery-selection.json',manifest)
verification={'status':'VERIFIED_FOR_LOCAL_COMMIT','parent':parent,'branch':BRANCH,'selected_file_count':len(allpaths),'scope':NAMES,'checks':{k:v for k,v in first.items() if k!='nonexception_paths'},'nonexception_paths':sorted(set(allpaths)-allowed),'final_verification_method':'rerun default full/scoped checks and staged-byte equality after audit files are staged; final tree/commit/push proof stored only in excluded local receipt','shared_state_before':before,'no_product_or_cache_payload':True,'formal_acceptance':'NOT_PERFORMED'}
save(HERE/'delivery-verification.json',verification)
save(HERE/'step-report.json',{'round':'R490','planner':'gpt-6-astra','status':'LOCAL_DELIVERY_VERIFICATION','frozen_byte_exceptions':13,'original_full_git_check':2,'all_other_paths_default_check':0,'selected_files':len(allpaths),'actual_generations':16,'quality_eligible_profiles':0,'new_model_loads':0,'new_generation_calls':0,'parent':parent,'branch':BRANCH,'push_confirmation':'post-commit excluded local receipt, never inferred from this file'})
(HERE/'step-report.md').write_text('# R490 步骤报告\n\n实际 Astra 逐条固定 13 个原字节例外，保留 CSV CRLF、diff context、traceback 与半写 JSON；未清理历史字节，未修改全局 Git whitespace 规则。默认全量检查原 rc2 保留，精确例外之外的全部路径按相同默认检查 rc0。\n\n采用独立临时 index，只加入 R486–R490 五目录；每个 staged blob 与实际文件字节一致，公开载荷不包含模型 raw、权重、SDK、wheel、deb、headers、venv、JIT、数据库或凭据。共享 HEAD/index 与无关 service.py 在交付前后单独核对。\n\nGit 提交以已交付 8b4a88b 为父，新建指定研发分支，不切共享 checkout；推送及本地/上游/实时远端三 SHA 的最终结果保存到 excluded local receipt，避免提交自引用。本文件本身不证明推送完成。\n')
(HERE/'phase-summary.md').write_text('# R486–R490 阶段总结\n\n真实完成 16 次固定双图生成。基础开启/关闭思考 warm 端到端中位数分别 36.412/14.035 秒；FLA-only 分别 34.299/12.169 秒。四种配置严格 JSON 与完整质量均 0/4，故没有质量合格的最佳配置；FLA 关闭思考只是在本静态场景最快。详细方法、首次编译成本及边界见 R486/phase-summary.md。\n\nR487 保留集合证据记录失败与 CPU 修复，R488 保留原生字符串子类/二次日志失败并完成 CPU 门槛后运行 A，R489 隔离补齐头文件、真实 CUDA/JIT 数值检查后运行 B。共 4 次加载，其中 2 次因证据记录失败未生成；16 次生成外无额外模型 warmup。量化权重和原 68 包最终核对通过；正式研究验收未执行。\n\nR490 保留交付默认全量空白检查的已知 rc2，仅对 Astra 固定 SHA 的 13 条原证据使用精确例外，其他所有交付文件默认检查 rc0。阶段交付仅含五目录的计划、脚本、派生结果与清单；完整 raw/权重/SDK/环境仍依既有边界留本地。最终提交和推送三 SHA 见本地 delivery-receipt.local.json。\n')
assert actual_files()==allpaths
(CACHE/'delivery-selected-paths-round486.nul').write_bytes(b'\0'.join(p.encode() for p in allpaths)+b'\0')
git(['add','--']+allpaths,env)
final=checks(allpaths,'final')
changed=git(['diff','--cached','--name-only','-z',parent],env).stdout.decode().split('\0')[:-1];assert sorted(changed)==allpaths
stage=git(['ls-files','--stage','-z'],env).stdout.decode().split('\0');entries={}
for row in stage:
 if row:
  fields,path=row.split('\t',1);mode,oid,number=fields.split();entries[path]=(mode,oid,number)
for p in allpaths:
 body=(ROOT/p).read_bytes();expected=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
 assert entries[p][1]==expected and entries[p][2]=='0',p
for name in NAMES:
 for item in read(BASE/name/'plan.json')['input_sha256']:assert sha(ROOT/item['path'])==item['sha256']
for item in exceptions:assert sha(ROOT/item['path'])==item['sha256']
assert snapshot()==before,'shared HEAD/index/service drift during private-index preparation'
tree=git(['write-tree'],env).stdout.decode().strip()
ready={'status':'READY_TO_COMMIT','tree':tree,'parent':parent,'branch':BRANCH,'index':state['index'],'selected_paths':allpaths,'selected_blob_sha256':{p:sha(ROOT/p) for p in allpaths},'shared_before':before,'final_checks':{k:v for k,v in final.items() if k!='nonexception_paths'},'nonexception_file_count':len(allpaths)-len(allowed),'all_staged_bytes_match':True,'original_scope_unchanged':True}
save(CACHE/'delivery-ready-round486.json',ready)
print(json.dumps({'status':ready['status'],'tree':tree,'selected_files':len(allpaths),'frozen_exceptions':13,'other_files':len(allpaths)-13,'default_full_check':2,'default_scoped_check':0,'shared_HEAD_index_unchanged':True,'all_staged_bytes_match':True},ensure_ascii=False))
