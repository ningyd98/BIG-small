"""R287 authorized factual context append after documented source/accounting STOP."""
from pathlib import Path
import base64,copy,hashlib,json,os,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round287-p6-t2-runner-completion-marker-contract-20261017")
ROOT=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
CONTEXT=ROOT/"artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007"
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes();assert stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==q;return b
def encoded(v):return (json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
def save(path,b):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(0o664);assert p.read_bytes()==b and p.lstat().st_mode==33204
 return pin(p,b)
planpin={"path":str(D/"plan.json"),"bytes":24997,"sha256":"c0370315fa34ee474e71d4ec8473b4c4a35c745c95138982cb978925ee675e1d"}
P=json.loads(checked(planpin))
ap={"path":str(D/"root-existing-evidence-assessment.json"),"bytes":369882,"sha256":"8134e69434082b9a4f5bd1bc99b2e94ac4af1f48a2315a3b35b0e1aa1b7d5a85"}
sp={"path":str(D/"root-failure-settlement.json"),"bytes":36617,"sha256":"17e9dab9d71eb9645a8f5f5f9a6095f9cf1a186567aaf3ec4a0fab91afea657f"}
A=json.loads(checked(ap));S=json.loads(checked(sp));STEP=json.loads((D/"step-report.json").read_bytes())
assert STEP["status"].endswith("_STOP") and A["failed"]==[] and A["checks_passed"]==2642 and A["corrected_source_acceptance"]["status"]=="FULL_SOURCE_ONLY_NATIVE_SCOPE_ACCEPTED"
assert S["status"]=="SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE" and S["assessment"]==ap
checked(S["root_after"]);checked(S["author_unchanged"])
statepin={"path":str(CONTEXT/"active-t12-state.json"),"bytes":170595,"sha256":"4ac74739752d78f67d772dd17ca13e44b512acfd4d68bb765e7d650cc72036b7"}
phasepin={"path":str(CONTEXT/"phase-summary.md"),"bytes":100870,"sha256":"e7aaaa868bb9269ea3165a0b9636012db215cbf5f9a5fe3bbd4b85dd88e93059"}
state_before,phase_before=checked(statepin),checked(phasepin)
old=json.loads(state_before);new=copy.deepcopy(old);assert "R287" not in old["planning"]
record=new["planning"]["R285"]
record.update(status="SOURCE_GATE_ACCEPTED_MEMORY_CASE_PASS_WRAPPER_FAILED_SETTLED",roles_created=True,runtime=1,runtime_scope="One original R285 memory wrapper invocation; no sqlite/dual execution")
entry=record["commands"]["wait_memory"]
entry.update(used=1,remaining=0,state="SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE")
record["actual_memory_run"]={"actual_tool_return":A["actual_runtime"],"wrapper_exit_observed":1,"JUnit_one_PASS":True,"original_result_absent":True,"direct_child_exit":None,"direct_process_group_cleanup":None,"source_inferred_child_exit":A["static_child_exit_inference"],"limited_existing_evidence":ap,"full_original_capture_accepted":False,"settlement":sp}
record["roles_current"]={"ROOT":S["root_after"],"AUTHOR":S["author_unchanged"]}
record["other_keys_released"]=False
new["planning"]["R287"]={"status":"SOURCE_ONLY_ACCEPTED_ORIGINAL_WRAPPER_FAILURE_SETTLED_NO_RUNTIME", "plan":planpin,"source":A["corrected_source_acceptance"],"existing_evidence_assessment":ap,"failure_settlement":sp,"actual_metadata":{"path":str(D/"root-metadata-actual-tool-return.json"),"pin":pin(D/"root-metadata-actual-tool-return.json"),"chunk":"dc66b8","exit":0,"checks":2642,"attempt":1,"retry":0},"observed_resource_counts":A["independent_observed_counts"],"marker_locations":A["markers"],"R288_recovery":{"plan":pin(D.parent/"round288-p6-t2-byteproof-assessment-anchor-disposition-20261017/plan.json"),"actual":pin(D.parent/"round288-p6-t2-byteproof-assessment-anchor-disposition-20261017/implementation/actual-tool-return.json"),"new_metadata_once_exit":0,"original_966fc6_failure_retained":True},"step_report":pin(D/"step-report.json"),"corrected_runner_executed":False,"new_runtime":0,"new_static":0,"new_review":0,"new_Git":0,"T2_complete":False,"T12_complete":False,"native_accepted":False,"formal_accepted":False,"next":"Actual Astra continuation must bind this source and actual new context generation and explicitly authorize finite execution; old memory remains spent, held sqlite/dual not released."}
left,right=copy.deepcopy(old),copy.deepcopy(new)
for key in ("R285","R287"):left["planning"].pop(key,None);right["planning"].pop(key,None)
assert left==right
for key in ("wait_sqlite","dual_first_invalidation"):assert old["planning"]["R285"]["commands"][key]==new["planning"]["R285"]["commands"][key]
state_after=encoded(new)
appendix=("\n\n## R285–R288：memory 实际证据、收尾修复与结算（2026-10-17）\n\n"
"R285 唯一 memory 运行原回执364b4c exit1保留；原始 JUnit 为1 PASS，pytest181.29秒。完成标记实际位于observations.assertions_completed且为布尔true；原consumer误读顶层，导致无正常result。顶层缺失仍为未观察/null，不补写原件。\n\n"
"R287 新路径runner c4865f0b（86520字节、1447行）修正完成位置并保护derived assessment/result保存；原reservation、启动、清理、AUTHOR spend和资源consumer不变，候选尚未执行。966fc6范围证明失败保留；R288新证明3d2cec exit0只修正唯一anchor，保持完整两region/outside字节重构。\n\n"
"ROOT独立元数据dc66b8 exit0/2642项：实际资源542尝试、540初始化、542清理观察；四个新DB原件/归档、12项侧文件缺失、27当前源、211保护文件及原历史边界均核对。直接child exit及进程组最终清理回执仍未知/null，原正常capture不接受；JUnit与资源记录只作限定独立证据。\n\n"
"原ROOT memory同key结算SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE1/0，AUTHOR仍SPENT；sqlite/dual保持HELD0/1且未放行。完整before/base64/mode、CAS与after见R287/root-failure-settlement.json，源码接受与限定证据见R287/root-existing-evidence-assessment.json。\n\n"
"T2/T12、native及正式研究验收仍未完成。本轮新增行为/静态/审阅/Git次数均0。下一步由实际Astra绑定已接受源码及本次真实上下文新世代，明确后续有界执行预算；不得复用已spent的memory槽。\n")
phase_after=phase_before+appendix.encode()
assert phase_after[:len(phase_before)]==phase_before
changes=[];prepared=[]
for label,q,before,after in (("STATE",statepin,state_before,state_after),("PHASE",phasepin,phase_before,phase_after)):
 path=Path(q["path"]);assert path.lstat().st_mode==33204
 archive=save(D/"before/context/generation001"/(label+".before"),before)
 after_archive=save(D/"before/context/generation001"/(label+".after"),after)
 changes.append({"label":label,"before":{"original":q,"archive":archive,"base64":base64.b64encode(before).decode("ascii")},"after":pin(path,after),"after_archive":after_archive,"mode":33204})
 prepared.append((path,before,after))
prospective={"round":"R287","status":"PROSPECTIVE_FULL_CONTEXT_MAP_BEFORE_CAS","plan":planpin,"changes":changes,"allowed_STATE_keys":["planning.R285","planning.R287"],"other_STATE_values_unchanged":True,"PHASE_original_prefix_unchanged":True,"new_runtime":0,"T2_complete":False}
save(D/"before/context/generation001/prospective-map.json",encoded(prospective))
for path,before,after in prepared:assert path.lstat().st_mode==33204 and path.read_bytes()==before
committed={}
for path,before,after in prepared:
 for other,other_before,other_after in prepared:assert other.lstat().st_mode==33204 and other.read_bytes()==committed.get(str(other),other_before)
 fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
 with os.fdopen(fd,"r+b") as f:
  assert os.fstat(f.fileno()).st_mode==33204 and f.read()==before
  f.seek(0);f.write(after);f.truncate();f.flush();os.fsync(f.fileno())
 assert path.read_bytes()==after and path.lstat().st_mode==33204
 committed[str(path)]=after
manifest={**prospective,"status":"ACTUAL_FACTUAL_CONTEXT_UPDATED_AFTER_DOCUMENTED_STOP"}
mp=save(D/"root-context-update.json",encoded(manifest))
for q in changes:assert checked(q["after"])==checked(q["after_archive"])
output=json.dumps({"status":manifest["status"],"context_manifest":mp,"after":[q["after"] for q in changes],"allowed_STATE_keys":manifest["allowed_STATE_keys"],"other_STATE_values_unchanged":True,"PHASE_original_prefix_unchanged":True,"new_runtime":0,"T2_complete":False},ensure_ascii=False)
assert len((output+"\n").encode())<=6000;print(output)
