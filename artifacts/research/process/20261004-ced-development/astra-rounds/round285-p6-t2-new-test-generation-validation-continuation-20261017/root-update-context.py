from pathlib import Path
import base64,copy,hashlib,json,os,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round285-p6-t2-new-test-generation-validation-continuation-20261017")
def require(ok,message):
 if not ok:raise RuntimeError(message)
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes()
 require(stat.S_ISREG(p.lstat().st_mode) and pin(p,b)=={k:q[k] for k in ("path","bytes","sha256")},"exact current input differs")
 return b
def save(path,b,mode=33204):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(stat.S_IMODE(mode));require(p.read_bytes()==b and p.lstat().st_mode==mode,"exclusive full archive differs")
 return pin(p,b)
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
P=json.loads(checked({"path":str(D/"plan.json"),"bytes":47877,"sha256":"22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0"}))
for q in P["inputs"]:checked(q)
state_q,phase_q=P["context_update"]["before_inputs"]
state_raw,phase_raw=checked(state_q),checked(phase_q)
state_path,phase_path=Path(state_q["path"]),Path(phase_q["path"])
state_mode,phase_mode=state_path.lstat().st_mode,phase_path.lstat().st_mode
require(state_mode==phase_mode==33204,"context regular modes differ")
old=json.loads(state_raw);new=copy.deepcopy(old);planning=new["planning"]
cap_q=next(q for q in P["inputs"] if q["path"].endswith("/root-wait-memory-independent-acceptance.json"))
cap=json.loads(checked(cap_q))
result_q=next(q for q in P["inputs"] if q["path"].endswith("/implementation/wait_memory/result.json"))
result=json.loads(checked(result_q))
actual_q=next(q for q in P["inputs"] if q["path"].endswith("/implementation/wait_memory/actual-tool-return.json"))
historical=copy.deepcopy(planning["R276"])
planning["R276"]={"status":"WAIT_MEMORY_FAILED_CAPTURE_ACCEPTED_OTHER_OLD_IDENTITIES_UNRELEASED","previous_planning_snapshot":historical,"actual_wait_memory":{"result":result_q,"actual_tool_return":actual_q,"child_exit":result["child_exit"],"wrapper_exit":result["wrapper_exit"],"timed_out":result["timed_out"],"elapsed_seconds":result["elapsed_seconds"],"capture_integrity_complete":True,"behavior_accepted":False,"independent_acceptance":cap_q,"independent_checks":479,"ROOT_after":cap["root_after"],"AUTHOR_after":cap["author_after"],"counts_observed":{"allocation_attempts":537,"initialized":535,"cleanup_observed":537},"first_invalidation_reason":None},"budgets":{"wait_memory":{"ROOT":"SPENT_UNEXPECTED_FAILURE","AUTHOR":"SPENT","used":1,"remaining":0},"wait_sqlite":{"state":"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE","used":0,"remaining":1,"released_for_193f":False},"dual_first_invalidation":{"state":"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE","used":0,"remaining":1,"released_for_193f":False}},"T2_complete":False}
statuses={"R277":"SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED","R278":"SOURCE_PREPARATION_ACCEPTED_BY_R280_NO_BEHAVIOR_CLAIM","R279":"BOUNDED_PHYSICAL_READ_DISPOSITION_COMPLETE","R280":"SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_BEHAVIOR_UNVERIFIED","R281":"SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED","R282":"ABANDON_OPTIONAL_VIEWER_ZERO_REPLAY","R283":"FAILED_CAPTURE_INTEGRITY_ACCEPTED_SELECTED_ROOT_SPENT","R284":"ABANDON_PLANNER_READER_ZERO_REPLAY"}
for round_name,status in statuses.items():
 ordinal=round_name[1:]
 q=next(q for q in P["inputs"] if "/round"+ordinal+"-" in q["path"] and q["path"].endswith("/step-report.json"))
 step=json.loads(checked(q))
 planning[round_name]={"status":status,"step_report":q,"historical_step_status_as_recorded":step["status"],"runtime_completed_by_this_step":0,"T2_complete":False}
planning["R281"]["source_acceptance"]=P["source_generation"]["acceptance"]
planning["R281"]["current_test"]=P["source_generation"]["current_test"]
planning["R283"]["accepted_checks"]=479
planning["R283"]["raw_marker"]={"present":False,"value":None,"status":"unobserved"}
planning["R285"]={"status":"PLAN_INPUT_ACCEPTED_SOURCE_PREPARATION_PENDING_RUNTIME_HELD","plan":pin(D/"plan.json"),"observation":P["input_observation"],"initial_source_input_review":pin(D/"root-initial-plan-input-review.json"),"source_generation":P["source_generation"],"commands":{k:{"budget_identity":v["budget_identity"],"authorized":1,"used":0,"remaining":1,"state":v["state"],"kind":v["kind"],"node":v["node"]} for k,v in P["commands"].items()},"old_R276_execution_route":"Superseded for193f; historical spent/held counts unchanged and no duplicate release","roles_created":False,"runtime":0,"T2_complete":False}
allowed={q.split(".",1)[1] for q in P["context_update"]["allowed_state_keys"]}
restored=copy.deepcopy(new)
for key in allowed:
 if key in old["planning"]:restored["planning"][key]=copy.deepcopy(old["planning"][key])
 else:restored["planning"].pop(key,None)
require(restored==old,"STATE mutation outside exact allowed planning keys")
state_after=encoded(new)
addition="""

## R276–R285 执行前事实更新（2026-10-17）

R276 的内存等待节点仅实际运行一次：child=1、wrapper=1，181.929099 秒，无超时，JUnit 1 FAIL / 0 ERROR / 0 SKIP。失败位于租约期限推进后的再次 reserve_capture：收到 OperationalLeaseError 的会话拒绝消息，与旧断言正则不匹配。D_app 已保留完整场景，D_lease 已执行此前的真实锁等待、首次拒绝、顺序、预算保持及无 COMPLETE 提交检查；首次被捕获异常及最初失效原因未保存，不能补称已直接观测首因。

R283 经真实 09d017 exit0 / 479 项检查及 ROOT 19adf4 字节重建复核，接受的是失败证据完整性。仅选中 ROOT 额度结算为 SPENT_UNEXPECTED_FAILURE1/0；AUTHOR 原 SPENT1/0 保持。观察到的资源分母是537次分配、535次初始化、537次清理，不能代替未知 OS/native 资源。原 raw 的 assertions_completed 键缺失，明确记为 present=false/value=null/unobserved。四个新数据库原字节及12个 absent sidecar 保留。旧 sqlite/dual 仍 HELD0/1，不释放给新源码世代。

R277–R280 的观察字段、runner 准备、读取和原生补丁归档表示差异均有独立步骤原件。实际 native 参数为权威，归档多一个末尾 LF 的关系逐字证明；native 返回{}的数值退出码和独立流仍为null。R282可选摘要 viewer、R284描述误作路径 reader 均弃用，原失败保留，零更正执行、零重放。

R281 只修改等待测试 nested exercise 的四处源码：保存首次及后续拒绝事实；D_lease 依据已有 counter 记录核对原 session.ttl_ns 跨越，并精确验证后置 OperationalLeaseError 完整消息；D_app 与原锁、预算和无提交断言保留。当前 test255468/193f45147160f52ba53956df506ddbc602b81f2248990eea604366a39e63ef13，经 ROOT 1b7375 exit0 / 567 项源码检查接受，尚无此世代行为通过。

R285 冻结三个新独立 once：内存等待、SQLite等待为行为验证，双库首次会话失效为诊断；逐项 ROOT reservation 和 literal release，当前均 HELD used0/remaining1，尚未创建新角色或运行。每 child600秒、总cleanup15秒、outer900秒；旧预算和失败不覆盖。双库即使 PASS 仍仅为诊断。

T2/T12 尚未完成，native 与正式研究验收状态不提升；当前阶段是准备新世代执行脚本和独立运行门。
"""
phase_after=phase_raw+addition.encode()
rows=[]
for label,path,q,before,after,mode in (("STATE",state_path,state_q,state_raw,state_after,state_mode),("PHASE",phase_path,phase_q,phase_raw,phase_after,phase_mode)):
 archive=save(D/"before/context/generation001"/(label+".before"),before,mode)
 after_archive=save(D/"before/context/generation001"/(label+".after"),after,mode)
 rows.append({"label":label,"before":{"original":q,"archive":archive,"base64":base64.b64encode(before).decode("ascii")},"after":pin(path,after),"after_archive":after_archive,"mode":mode})
proposal={"round":"R285","status":"PROSPECTIVE_CONTEXT_BYTES_BEFORE_CAS","changes":rows,"allowed_state_keys":P["context_update"]["allowed_state_keys"],"runtime":0,"T2_complete":False}
save(D/"root-context-prospective.json",encoded(proposal))
for row in rows:
 path=Path(row["before"]["original"]["path"]);before=base64.b64decode(row["before"]["base64"],validate=True)
 require(path.read_bytes()==before and path.lstat().st_mode==row["mode"],"context group full-byte/mode CAS conflict")
for row in rows:
 path=Path(row["before"]["original"]["path"]);before=base64.b64decode(row["before"]["base64"],validate=True)
 after=Path(row["after_archive"]["path"]).read_bytes()
 fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
 with os.fdopen(fd,"r+b") as f:
  require(os.fstat(f.fileno()).st_mode==row["mode"] and f.read()==before,"context descriptor immediate CAS conflict")
  f.seek(0);f.write(after);f.truncate();f.flush();os.fsync(f.fileno())
 require(pin(path)==row["after"] and path.lstat().st_mode==row["mode"],"context after actual readback differs")
manifest={"round":"R285","status":"FACTUAL_CONTEXT_UPDATED_BEHAVIOR_NOT_PROMOTED","plan":pin(D/"plan.json"),"changes":rows,"allowed_state_keys":P["context_update"]["allowed_state_keys"],"other_STATE_values_unchanged":True,"PHASE_original_prefix_unchanged":True,"runtime":0,"T2_complete":False}
m=save(D/"root-context-update.json",encoded(manifest))
output=json.dumps({"status":manifest["status"],"manifest":m,"after":[q["after"] for q in rows]},ensure_ascii=False)
require(len((output+"\n").encode())<=6000,"bounded context stdout")
print(output)
