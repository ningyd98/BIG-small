from pathlib import Path
import base64,copy,hashlib,json,shlex
from collections import Counter
from decimal import Decimal
import xml.etree.ElementTree as ET
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round237-p6-t2-original-verification-budget-intersection-20261015"
O=D/"implementation/red"; checks=[]; records=[]
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
def ident(v):return {k:v[k] for k in ("path","bytes","sha256")}
def pin(p,raw=None):
 p=Path(p);raw=p.read_bytes() if raw is None else raw
 return {"path":str(p),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def ck(v,l):
 checks.append({"check":l,"pass":bool(v)})
 if not v:raise ValueError(l)
def fixed(v):
 p=Path(v["path"]);ck(not p.is_symlink() and pin(p)==ident(v),"fixed "+str(p));records.append(ident(v))
def load(p):return json.loads(Path(p).read_bytes())
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:ck(f.write(b)==len(b),"fullwrite "+str(p))
 ck(p.read_bytes()==b,"readback "+str(p))
def save(p,v):put(p,enc(v))
for p,n,sha in ((O/"result.json",13195863,"2f0553833c8a38a8705e56e7458337798224441323606bd83f49d2442cdbeff2"),(O/"actual-tool-return.json",3394,"bcfb611a13db811276da3756c0d760bd66f3ed5ff78449d715870a1327a586a1"),(O/"junit.xml",6085,"a20c8943054f4446f55228954e2311fe2f6422bf6c7572e814a8932427591078")):
 fixed({"path":str(p),"bytes":n,"sha256":sha})
result=load(O/"result.json");receipt=load(O/"actual-tool-return.json");launch=load(D/"root-red-launch.json");reservation=load(D/"root-red-reservation.json")
fixed(reservation["launcher"]);fixed(reservation["ruff_acceptance"])
ck(receipt["invocation"]==launch["tool_arguments"] and receipt["initial"]["session_id"]==25556,"exact single reserved actual transport/session")
ck(len(receipt["polls"])==5 and all(x["session_id"]==25556 for x in receipt["polls"][:-1]) and receipt["polls"][-1]==receipt["completion"]==receipt["actual_tool_return"] and receipt["completion"]["exit_code"]==1,"one session actual completion1")
ck(receipt["independent_stdout"] is None and receipt["independent_stderr"] is None,"unknown tool streams remain null")
ck((result["round"],result["command"],result["attempt"],result["retry"],result["child_exit"],result["wrapper_exit"])==("R237","red",1,0,1,1),"actual unique RED3 outcome")
ck(result["accepted_command_outcome"] is False and result["timed_out"] is False and result["runner_exception"] is None and result["observation_errors"]==[],"unexpected semantic result with complete collection")
ck(result["cleanup"]=={"leader_reaped":True,"group_remaining":False,"cleanup_notes":[]},"real reap/group cleanup")
for row in result["input_records"]+list(result["streams"].values()):fixed(row)
ck(result["input_records"]==load(D/"script-gate.json")["commands"]["red"]["input_records"],"exact immutable RED gate generation")
fixed(result["source_index_pin"]);index=load(Path(result["source_index_pin"]["path"]))
ck(result["source_index_pin"]==load(D/"root-baseline-acceptance.json")["source_index"],"same accepted full current baseline")
for row in index["sources"]:
 fixed(row);raw=base64.b64decode(row["base64"],validate=True);physical=Path(result["source_index_pin"]["path"]).parent/"sources"/Path(row["path"]).relative_to(R)
 ck(raw==Path(row["path"]).read_bytes()==physical.read_bytes() and Path(row["path"]).stat().st_mode==row["mode"],"complete current source/physical/base64/mode")
for row in index["protected"]+index["scripts"]+index["history"]:fixed(row)
ck(len(index["sources"])==27 and len(index["protected"])==211 and len(index["history"])==321,"all finite current/protected/history sets")
ck(index["resolved_history"]==load(D/"implementation/resolved-history.json") and not index["resolved_history"]["unresolved"],"full historical map unchanged")
for row in index["resolved_history"]["documents"]:fixed(row)
for row in index["absent_sidecars"]:ck(row["exists"] is False and not Path(row["path"]).exists() and not Path(row["path"]).is_symlink(),"old sidecar absence unchanged")
ck(len(index["absent_sidecars"])==54,"54 old sidecar absences")
ck(result["source_after"]["all_unchanged"] is True and result["source_after"]["protected_count"]==211 and result["source_after"]["sources"]==[ident(x) for x in index["sources"]],"actual source-after matches independent bytes")
ck(load(O/"source-after.json")==result["source_after"],"raw actual source-after")
fixed(pin(O/"source-after.json"))
plan=load(D/"plan.json");command=next(x for x in plan["commands"] if x["id"]=="red");expected=[x for x in command["child_argv"] if "::" in x]
inv=result["invocation"];ck(inv==load(O/"invocation.json") and inv["argv"]==command["child_argv"] and inv["launcher_argv"]==command["launcher_argv"] and inv["finite_env"]==command["finite_env"] and inv["outer_capture"]==launch and inv["timeout_seconds"]==600 and inv["cleanup_seconds"]==15,"actual exact original three nodes/env/bounds")
fixed(pin(O/"invocation.json"))
tree=ET.fromstring((O/"junit.xml").read_bytes());nodes=tree.findall(".//testcase")
names=[x.get("classname","").replace(".","/")+".py::"+x.get("name","") for x in nodes]
ck(names==expected and len(nodes)==3 and all(x.find("failure") is not None and x.find("error") is None and x.find("skipped") is None for x in nodes),"raw exact JUnit3 FAIL0ERROR0SKIP")
ck(all("R223 late local binding was not rejected" in (x.find("failure").text or "") for x in nodes),"actual original top-level assertion retained")
facts=[]
ck(len(result["cases"])==3,"three full raw cases")
for case in result["cases"]:
 fixed(case["pin"]);data=load(Path(case["pin"]["path"]));ck(data==case["data"],"complete raw case agrees with result")
 ck(data["bootstrap_complete"] is True and data["writer_joined"] is True and data["writer"]["attempted"] is True and data["writer"]["returned"] is False,"real bootstrap reached but no completed positive writer")
 ck(data["writer"]["exception"]["type"]=="AssertionError" and data["writer"]["exception"]["message"].startswith("R223 original writer release timed out"),"actual writer barrier timeout cause")
 order=data["order"];kinds=[x["kind"] for x in order]
 ck(kinds==["WRITER_READY","PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK","ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK","WRITER_RAISED","DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE"],"all actual ordered stages; writer timeout before episode COMPLETE observation")
 ck([x["sequence"] for x in order]==list(range(1,6)) and all(x["pid"]==result["child_pid"] for x in order),"real actual case sequence/pid")
 ck(order[0]["thread"]==order[2]["thread"]==order[3]["thread"] and order[1]["thread"]==order[4]["thread"] and order[0]["thread"]!=order[1]["thread"],"separate actual writer/main threads")
 ck((order[0]["repository"]!=order[1]["repository"]) is data["second_connection"],"real selected same/second repository")
 original=data["bootstrap"]["original_time"];payload=data["bootstrap"]["payload"];state=payload["state"]
 ck(data["binding"]==original and state["original_budget_reference"]==original["verification_reference"],"real binding and exact immutable original budget reference")
 limits=state["limits"];hard=[x["budget_ns"] for x in original["verification_reference"]["hard_deadlines"]]
 ck(len(hard)==2 and all(type(x) is int and x>0 for x in hard) and int(limits["deadline_s"]*1_000_000_000)<=min(hard) and Decimal(str(limits["deadline_s"]))*Decimal(1_000_000_000)<=min(hard),"actual budget producer stays inside original hard obligations")
 ck(payload["definition"]["payload"]["verification_limits"]==limits,"actual initial definition/state complete policy equality")
 rows=data["complete_receipts"];ck(set(rows)=={"event","job"} and len(rows["event"])==len(rows["job"])==1,"real one event and job receipt")
 event,job=rows["event"][0],rows["job"][0]
 for field in ("operation_id","operation_sha256","job_id","attempt","lease_id","epoch","generation","phase","event_record_hash","event_receipt_hash","job_receipt_hash"):ck(event[field]==job[field],"coherent dual COMPLETE "+field)
 ck(event["phase"]=="COMPLETE" and data["after"] is None and "legacy_after" not in data,"both COMPLETE observed but no positive legacy mutation witness")
 facts.append({"case":case["pin"],"backend":data["backend"],"second_connection":data["second_connection"],"order":order,"writer":data["writer"],"bootstrap_complete":True,"binding_matches_original":True,"limits":limits,"original_hard_budget_ns":hard,"both_receipts":[{k:v for k,v in row.items() if k!="payload_json"} for row in (event,job)],"writer_returned":False,"legal_RED":False})
rs=result["resource_summary"];ck(rs["all_records_valid"] is True and rs["validation_errors"]==[] and len(rs["records"])==3,"raw observer records complete within observer coverage")
attempts=initialized=closed=entered=normal=workers=never=0
for record in rs["records"]:
 fixed(record["pin"]);value=load(Path(record["pin"]["path"]));ck(value==record["data"] and record["error"] is None,"full raw resource sidecar")
 resources=value["resources"];ck(value["allocation_attempts"]==len(resources) and value["cleanup_errors"]==[] and value["observations"]["observers_restored"] is True,"actual denominator/cleanup/restoration")
 ck(value["pid"]==result["child_pid"] and value["nodeid"] in expected,"actual observer pid/node")
 ids=[x["resource_id"] for x in resources];ck(len(ids)==len(set(ids)) and all(type(x) is int and x>0 for x in ids),"real unique per-case resource IDs")
 for resource in resources:
  attempts+=1;initialized+=int(resource["initialized"]);closed+=int(resource["cleanup_observed"])
  ck(resource["cleanup_observed"] is True and resource["pid"]==result["child_pid"],"actual observed resource cleanup/pid")
  if resource["kind"] in ("broker_thread","heartbeat_thread"):ck(resource["alive_after_join"] is False,"real observed thread terminated")
  if resource["kind"]=="worker":workers+=1;never+=int(not resource["poll_ids"])
 for call in value["worker_lifecycles"]:
  entered+=int(call["entered"]);normal+=int(call["returned_normally"])
 ck(len(value["worker_lifecycles"])==1,"one genuine frozen poll per selected case")
ck((attempts,initialized,closed,entered,normal,workers,never)==(rs["counts"]["allocation_attempts"],rs["counts"]["initialized"],rs["counts"]["cleanup_observed"],rs["counts"]["entered_poll_lifecycles"],rs["counts"]["normally_returned_poll_lifecycles"],rs["counts"]["constructed_worker_attempts"],rs["counts"]["never_polled_workers"]),"independent complete observed denominator counts")
fixed(result["prerequisite"]["pin"]);prereq=load(Path(result["prerequisite"]["pin"]["path"]));ck(prereq==result["prerequisite"]["data"],"full original prerequisite record")
ck(prereq["accepted_prerequisite"] is True and prereq["exception"] is None and prereq["same_sys_modules_object_after"] is True and prereq["pre_import_hooks_empty"] is True and prereq["profile_trace_before_after_equal"] is True and prereq["profile_trace_before"]==prereq["profile_trace_after"]==[None]*4 and prereq["pre_observer_resource_measurement"] is None,"real import-only prerequisite and exact hook provenance")
for p in (O/"file-index.json",O/"temp-index.json",O/"resource-summary.json",D/"implementation/red-outer-stdout.txt",D/"implementation/red-outer-stderr.txt"):fixed(pin(p))
ck(load(O/"file-index.json")==result["file_index"] and load(O/"temp-index.json")==result["temp_index"] and load(O/"resource-summary.json")==rs,"complete raw indexes/summary")
new_databases=[]
for row in result["file_index"]+result["temp_index"]:
 if row["kind"]=="regular" and row["sha256"] is not None:fixed(row)
 if row["kind"]=="regular" and Path(row["path"]).suffix==".db":
  p=Path(row["path"]);ck(not p.is_symlink() and p.stat().st_size==row["bytes"],"actual closed new DB size");db={"pin":pin(p),"sidecars":[]}
  for suffix in ("-wal","-shm","-journal"):
   q=Path(str(p)+suffix);side={"path":str(q),"exists":q.exists(),"symlink":q.is_symlink()}
   if q.exists() and q.is_file() and not q.is_symlink():side["pin"]=pin(q)
   db["sidecars"].append(side)
  new_databases.append(db)
ck((D/"implementation/red-outer-stderr.txt").read_bytes()==b"" and len((D/"implementation/red-outer-stdout.txt").read_bytes())<=6000,"actual bounded outer streams")
controls=inv["controls_before"];ck(len(controls)==5,"complete actual current control originals")
originals={}
for row in controls:
 b=base64.b64decode(row["base64"],validate=True);ck(pin(row["path"],b)==ident(row),"complete original control bytes");originals[row["path"]]=b
 if row["path"]!=str(D/"command-ledger.json"):fixed(row)
expected_author=json.loads(originals[str(D/"command-ledger.json")]);expected_author["commands"]["red"].update(state="SPENT",used=1,remaining=0,reservation_id=inv["reservation_id"])
ck((D/"command-ledger.json").read_bytes()==enc(expected_author),"sole exact final author slot consumption")
root=load(D/"root-command-ledger.json")
ck(root["commands"]["red"]["state"]=="RESERVED_BY_ROOT" and all(x["used"]==1 and x["remaining"]==0 for x in root["commands"].values()),"all three original ROOT slots permanently consumed")
B=R/"artifacts/research/process/20261004-ced-development";state_path=B/"t12-sol-handoff-20261007/active-t12-state.json";phase_path=B/"t12-sol-handoff-20261007/phase-summary.md"
for p,n,sha in ((state_path,130968,"1d86a9ffd66ac437c42bfb032baa414b97d1021086730d6147cf469d17b03d2e"),(phase_path,85762,"06d0cd4a16bc3cc6ae051d924b715bd49a6ba8a1830fe50d0d268574799a0abc")):fixed({"path":str(p),"bytes":n,"sha256":sha})
stage=D/"before/root-evidence-settlement";ck(not stage.exists(),"exclusive complete settlement before");snapshots={}
paths=[D/name for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json")]+[state_path,phase_path]
for p in paths:
 b=p.read_bytes();q=stage/p.name;put(q,b);snapshots[str(p)]={"raw":b,"original":pin(p,b),"archive":pin(q)}
save(stage/"index.json",{"records":[{"original":v["original"],"archive":v["archive"],"base64":base64.b64encode(v["raw"]).decode()} for v in snapshots.values()]})
findings={"input_records_as_of_before":[dict(t) for t in {tuple(ident(x).values()):ident(x) for x in records}.values()],"complete_control_before":pin(stage/"index.json"),"schema_version":"bigsmall.r237.root-evidence-acceptance.v1","status":"EVIDENCE_COMPLETE_UNEXPECTED_RECOVERY_RED_NOT_LEGAL","checks":checks.copy(),"all_integrity_checks":all(x["pass"] for x in checks),"actual_tool":pin(O/"actual-tool-return.json"),"result":pin(O/"result.json"),"source_index":result["source_index_pin"],"JUnit":pin(O/"junit.xml"),"cases":facts,"observed_resources":{"attempts":attempts,"initialized_flags":initialized,"cleanup_observed":closed,"entered_polls":entered,"normal_polls":normal,"constructed_workers":workers,"never_polled_workers":never},"resource_coverage":"Observed denominator only; no exhaustive unknown partially-created/native/OS objects claim.","prerequisite":result["prerequisite"]["pin"],"new_retained_databases":new_databases,"legal_RED":False,"GREEN":False,"T2_complete":False,"T12_complete":False,"native":False,"formal":False,"next":"Actual Astra R239 required; no wait/TTL/test/observer/source repair or repeat authorized","display_boundary":"90c78c full stdout/actual receipt uncapped; d2371a prerequisite module-list display capped, raw actual object and all raw files preserved; no complete-display claim."}
save(D/"root-evidence-acceptance.json",findings)
root["commands"]["red"].update(state="SPENT_UNEXPECTED_RECOVERY_RED_NOT_LEGAL",actual_tool=pin(O/"actual-tool-return.json"),result=pin(O/"result.json"),root_findings=pin(D/"root-evidence-acceptance.json"),legal_RED=False)
activation=json.loads(snapshots[str(D/"root-activation.json")]["raw"]);activation.update(status="STOP_ASTRA_R239_REQUIRED",execution_released=False,root_evidence=pin(D/"root-evidence-acceptance.json"),historical_control_resolution=pin(stage/"index.json"))
source_gate=json.loads(snapshots[str(D/"source-gate.json")]["raw"]);source_gate.update(status="RECOVERY_RED_UNEXPECTED_ASTRA_R239_REQUIRED",source_preparation_authorized=False,execution_released=False,last_result=pin(D/"root-evidence-acceptance.json"),historical_control_resolution=pin(stage/"index.json"))
script_gate=json.loads(snapshots[str(D/"script-gate.json")]["raw"]);script_gate["execution_released"]=False
for command_name,command_state in (("baseline","SPENT_ACCEPTED_BASELINE"),("ruff","SPENT_ACCEPTED_RUFF"),("red","SPENT_UNEXPECTED_RECOVERY_RED_NOT_LEGAL")):
 script_gate["commands"][command_name]["state"]=command_state
script_gate["commands"]["red"].update(legal_RED=False,result=pin(O/"result.json"),root_evidence=pin(D/"root-evidence-acceptance.json"))
script_gate["historical_control_resolution"]=pin(stage/"index.json")
for name,value in (("root-command-ledger.json",root),("root-activation.json",activation),("source-gate.json",source_gate),("script-gate.json",script_gate)):
 p=D/name;ck(p.read_bytes()==snapshots[str(p)]["raw"],"immediate role settlement CAS");b=enc(value);ck(p.write_bytes(b)==len(b) and p.read_bytes()==b,"exact ROOT red spent settlement")
state=json.loads(snapshots[str(state_path)]["raw"]);old_state=copy.deepcopy(state);ck("R237" not in state["planning"] and "R238" not in state["planning"],"new factual planning entries only")
state["planning"]["R237"]={"status":"BUDGET_PRODUCER_REPAIRED_BASELINE_RUFF_PASSED_RED_UNEXPECTED_WRITER_TIMEOUT","plan":pin(D/"plan.json"),"root_findings":pin(D/"root-evidence-acceptance.json"),"before_R238_product_edits":0,"slots_used":3,"slots_remaining":0,"all_three_bootstrap_complete":True,"writer_timeouts":3,"legal_RED":False,"T2_complete":False,"next":"Actual Astra R239"}
C=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round238-p6-t2-pure-budget-projection-boundary-20261015"
state["planning"]["R238"]={"status":"PURE_PROJECTION_BOUNDARY_IMPLEMENTED_NO_NEW_EXECUTION_SLOTS","plan":pin(C/"plan.json"),"implementation_source":pin(R/"src/cloud_edge_robot_arm/vision/worker_runtime.py"),"inherited_R237_slots_used":3,"new_slots":0,"T2_complete":False}
other=copy.deepcopy(state);other["planning"].pop("R237");other["planning"].pop("R238");ck(other==old_state,"all other state values unchanged")
phase=snapshots[str(phase_path)]["raw"];addition=("\n\n## R237 / R238（2026-10-15）\n\nR237 初始计划的纯度边界在源准备前发现冲突，未执行产品；实际 Astra R238 明确保留首次唯一导出并采用显式原始引用的静态纯预算投影。仅 worker_runtime.py 的批准区域变更，其他26源码与211保护项完整保持。完整27基线及定向 Ruff 已真实通过；这不构成 T2 验收。\n\n唯一恢复 RED3 均真实完成 bootstrap、原始绑定以及 job/event 双 COMPLETE，但原写入线程在 during_episode 观察之前发生10秒释放等待超时。三个顶层失败仍位于原 late-binding 断言；其原因是写入线程 AssertionError，未产生正向 legacy 写入见证，因此本轮不是合法 RED。原始 stdout/JUnit/cases/resources/工具会话全部保留，738次资源尝试仅为已观察分母。原三槽均已耗尽，下一步交实际 Astra R239；event3、GREEN9、父 GREEN7、fresh review12、Git0 均继续冻结。T2/T12/native/formal 未通过。\n").encode()
new_phase=phase+addition;ck(new_phase.startswith(phase),"exact original phase bytes preserved")
for p,b in ((state_path,enc(state)),(phase_path,new_phase)):
 ck(p.read_bytes()==snapshots[str(p)]["raw"],"immediate state/phase CAS");ck(p.write_bytes(b)==len(b) and p.read_bytes()==b,"exact factual state/phase append")
step={"round":"R237","continuation":"R238","status":"THREE_SLOTS_SPENT_UNEXPECTED_RECOVERY_RED_ASTRA_R239_REQUIRED","root_integrity_checks":len(checks),"all_integrity_checks":all(x["pass"] for x in checks),"baseline":{"actual_exit":0,"acceptance":pin(D/"root-baseline-acceptance.json")},"Ruff":{"child_exit":0,"wrapper_exit":0,"acceptance":pin(D/"root-ruff-acceptance.json")},"RED":{"child_exit":1,"wrapper_exit":1,"cases":3,"bootstrap_complete":3,"dual_COMPLETE":3,"writer_timeouts":3,"legal_RED":False,"root_findings":pin(D/"root-evidence-acceptance.json")},"source":pin(R/"src/cloud_edge_robot_arm/vision/worker_runtime.py"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json"),"STATE_after":pin(state_path),"PHASE_after":pin(phase_path),"new_retained_database_count":len(new_databases),"T2_complete":False,"T12_complete":False,"native":False,"formal":False}
save(D/"step-report.json",step);put(D/"step-report.md",("# R237 / R238 步骤报告\n\n预算生产修复已实施，完整基线与限定 Ruff 通过。三个原场景真实建立 bootstrap、binding 与双 COMPLETE；但原写入线程先发生10秒等待超时，顶层原断言因此失败，未构成合法 RED。三次一次性验证额度已全部使用，未重试；完整失败与资源证据保持。\n\nR238 仅修正纯函数与既有引用取得的边界，新增执行槽为0。下一轮必须由实际 Astra R239 制定有限诊断计划。T2/T12、native、formal 均未通过。完整数值、原始回执与哈希见 step-report.json 和 root-evidence-acceptance.json。\n").encode())
save(C/"step-report.json",{"round":"R238","status":"IMPLEMENTED_SOURCE_BOUNDARY_UNDER_R237_THREE_ORIGINAL_SLOTS","original_R237_seam_before_edits":True,"new_slots":0,"R237_step":pin(D/"step-report.json"),"source":step["source"],"T2_complete":False})
put(C/"step-report.md",("# R238 步骤报告\n\n已依实际 Astra 计划把既有首次引用导出与静态纯预算投影分开，后续只比对既存 canonical 注册描述，不新增数据库/时钟读取或权能缓存。沿用 R237 原三槽，新增槽为0。完整基线与 Ruff 通过；恢复 RED3 出现写入线程等待超时，需实际 Astra R239 下一计划，未通过 T2。\n").encode())
print(json.dumps({"status":step["status"],"integrity_checks":len(checks),"all_pass":all(x["pass"] for x in checks),"bootstrap_COMPLETE":3,"writer_timeouts":3,"legal_RED":False,"new_DBs":len(new_databases),"findings":pin(D/"root-evidence-acceptance.json"),"step":pin(D/"step-report.json"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json"),"STATE":pin(state_path),"PHASE":pin(phase_path)},ensure_ascii=False))
