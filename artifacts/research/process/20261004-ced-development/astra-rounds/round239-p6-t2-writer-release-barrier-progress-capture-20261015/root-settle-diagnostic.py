from pathlib import Path
from collections import Counter
import base64,copy,hashlib,json
import xml.etree.ElementTree as ET
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round239-p6-t2-writer-release-barrier-progress-capture-20261015"
O=D/"implementation/capture";checks=[];records=[]
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
def ident(v):return {k:v[k] for k in ("path","bytes","sha256")}
def pin(p,raw=None):
 p=Path(p);raw=p.read_bytes() if raw is None else raw
 return {"path":str(p),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def ck(v,l):
 checks.append({"check":l,"pass":bool(v)})
 if not v:raise ValueError(l)
def fixed(v):
 q=Path(v["path"]);ck(not q.is_symlink() and pin(q)==ident(v),"fixed "+str(q));records.append(ident(v))
def load(p):return json.loads(Path(p).read_bytes())
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:ck(f.write(b)==len(b),"fullwrite "+str(p))
 ck(p.read_bytes()==b,"readback "+str(p))
def save(p,v):put(p,enc(v))
for p,n,h in ((O/"result.json",16494677,"89ead838fa3ea213cbaf49d0b00cdfdff6bd1f2af879a6f6ee60e54005187f9f"),(O/"actual-tool-return.json",3730,"8049b320c69bc5a08ff489e5c3967609bfffb29f7e25b22a3c28da0c4bd72487"),(D/"root-progress-analysis.json",1374364,"e3ecb5a8b6da46d04f9ee0c7b6742537fc680d771c6a9b888fa1c169623da4ba")):fixed({"path":str(p),"bytes":n,"sha256":h})
r=load(O/"result.json");actual=load(O/"actual-tool-return.json");plan=load(D/"plan.json");launch=load(D/"root-capture-launch.json");analysis=load(D/"root-progress-analysis.json");reservation=load(D/"root-capture-reservation.json")
fixed(reservation["launcher"]);fixed(reservation["source_review"])
ck(actual["invocation"]==launch["tool_arguments"] and actual["initial"]["session_id"]==75126 and len(actual["polls"])==4,"one exact reserved transport/session")
ck(all(x["session_id"]==75126 for x in actual["polls"][:-1]) and actual["polls"][-1]==actual["completion"]==actual["actual_tool_return"] and actual["completion"]["exit_code"]==0,"same session final actual0")
ck(actual["independent_stdout"] is None and actual["independent_stderr"] is None and actual["retry"]==0,"original actual unknown streams and no retry")
ck((r["round"],r["command"],r["attempt"],r["retry"],r["child_exit"],r["wrapper_exit"])==("R239","capture",1,0,1,0),"actual diagnostic child1 wrapper0")
ck(r["diagnostic_complete"] is True and r["accepted_command_outcome"] is True and r["timed_out"] is False and r["runner_exception"] is None and r["observation_errors"]==[],"complete diagnostic collection only")
ck(r["cleanup"]=={"leader_reaped":True,"group_remaining":False,"cleanup_notes":[]} and 0<=r["combined_cleanup_seconds"]<=15,"actual process closure/cleanup bound")
ck(r["legal_RED"] is False and r["GREEN"] is False and r["T2_complete"] is False and r["T12_complete"] is False,"no test/stage promotion")
for row in r["input_records"]+list(r["streams"].values()):fixed(row)
gate=load(D/"script-gate.json")["commands"]["capture"];ck(r["input_records"]==gate["input_records"],"exact immutable invocation inputs")
fixed(r["source_index_pin"]);idx=load(r["source_index_pin"]["path"]);fixed(idx["accepted_baseline"])
ck(idx["accepted_baseline"]==gate["source_index_pin"] and len(idx["sources"])==27 and len(idx["protected"])==211 and len(idx["history"])==321,"fresh full27/protected211/history321")
for row in idx["sources"]:
 fixed(row);fixed(row["physical"]);raw=base64.b64decode(row["base64"],validate=True)
 ck(raw==Path(row["path"]).read_bytes()==Path(row["physical"]["path"]).read_bytes() and Path(row["path"]).stat().st_mode==row["mode"],"complete fresh/current source bytes/base64/mode")
 old=row["physical_original"];fixed(old["archive"]);ck(old["original"]["path"]==row["path"] and all(old["original"][k]==old["archive"][k] for k in ("bytes","sha256")),"separate unchanged historical source generation")
for row in idx["protected"]+idx["scripts"]+idx["history"]+idx["historical_current_physical"]+idx["resolved_history"]["documents"]:fixed(row)
for row in idx["scripts"]:ck(base64.b64decode(row["base64"],validate=True)==Path(row["path"]).read_bytes(),"complete three script bytes")
ck(len(idx["scripts"])==3 and len(idx["retained_databases"])==24 and len(idx["absent_sidecars"])==72 and idx["resolved_history"]["unresolved"]==[],"full finite script/database/history sets")
for row in idx["retained_databases"]:fixed(row["pin"])
for row in idx["absent_sidecars"]:ck(row["exists"] is False and not Path(row["path"]).exists() and not Path(row["path"]).is_symlink(),"old72 absent sidecars unchanged")
inv=r["invocation"];command=plan["command"]
ck(inv==load(O/"spawn-invocation.json") and {k:v for k,v in inv.items() if k!="applied_child_timeout_seconds"}==load(O/"invocation.json"),"exact original and applied spawn invocation generations")
ck(inv["argv"]==command["child_argv"] and inv["launcher_argv"]==command["launcher_argv"] and inv["finite_env"]==command["finite_env"] and inv["outer_capture"]==launch==r["outer_capture"] and inv["timeout_seconds"]==600 and inv["cleanup_total_seconds"]==15 and 0<inv["applied_child_timeout_seconds"]<=600,"exact finite argv/env/applied deadline")
for q in (O/"invocation.json",O/"spawn-invocation.json",O/"junit.xml",O/"source-after.json",O/"file-index.json",O/"temp-index.json",O/"resource-summary.json",O/"progress-summary.json",D/"implementation/capture-outer-stdout.txt",D/"implementation/capture-outer-stderr.txt"):fixed(pin(q))
expected=[x for x in command["child_argv"] if "::" in x];nodes=ET.fromstring((O/"junit.xml").read_bytes()).findall(".//testcase")
names=[x.get("classname","").replace(".","/")+".py::"+x.get("name","") for x in nodes]
ck(names==expected and len(nodes)==3 and all(x.find("failure") is not None and x.find("error") is None and x.find("skipped") is None for x in nodes),"actual original3 FAIL0ERROR0SKIP")
ck(all("R223 late local binding was not rejected" in (x.find("failure").text or "") for x in nodes),"original top-level assertion locations")
case_map={};case_facts=[]
for node in expected:
 name=hashlib.sha256(node.encode()).hexdigest()+".json";case_row=next(x for x in r["cases"] if Path(x["pin"]["path"]).name==name);fixed(case_row["pin"]);data=load(case_row["pin"]["path"]);ck(data==case_row["data"],"complete original case raw/result equality");case_map[node]=data
 ck(data["bootstrap_complete"] is True and data["writer_joined"] is True and data["writer"]["attempted"] is True and data["writer"]["returned"] is False and data["writer"]["exception"]["type"]=="AssertionError" and data["writer"]["exception"]["message"].startswith("R223 original writer release timed out"),"actual complete bootstrap plus original barrier timeout")
 ck([x["kind"] for x in data["order"]]==["WRITER_READY","PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK","ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK","WRITER_RAISED","DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE"],"exact observed original causal order")
 ck([x["sequence"] for x in data["order"]]==list(range(1,6)) and all(x["pid"]==r["child_pid"] for x in data["order"]),"actual case sequence and child PID")
 rows=data["complete_receipts"];ck(len(rows["event"])==len(rows["job"])==1,"real dual receipt rows")
 for field in ("operation_id","operation_sha256","job_id","attempt","lease_id","epoch","generation","phase","event_record_hash","event_receipt_hash","job_receipt_hash"):ck(rows["event"][0][field]==rows["job"][0][field],"coherent dual receipt "+field)
 ck(rows["event"][0]["phase"]=="COMPLETE" and data["binding"]==data["bootstrap"]["original_time"] and data["after"] is None and "legacy_after" not in data,"real original binding/COMPLETE but no positive legacy mutation witness")
 case_facts.append({"nodeid":node,"raw":case_row["pin"],"writer":data["writer"],"bootstrap_complete":True,"dual_COMPLETE":True,"legal_RED":False})
rs=r["resource_summary"];ck(rs==load(O/"resource-summary.json") and rs["all_records_valid"] is True and rs["validation_errors"]==[] and len(rs["records"])==3,"full raw observed resource summary")
attempts=initialized=closed=entered=normal=workers=never=0
for record in rs["records"]:
 fixed(record["pin"]);data=load(record["pin"]["path"]);ck(data==record["data"] and record["error"] is None,"complete frozen resource raw/result equality")
 ck(data["allocation_attempts"]==len(data["resources"]) and data["cleanup_errors"]==[] and data["observations"]["observers_restored"] is True and data["pid"]==r["child_pid"],"actual observed denominator/cleanup/restoration/pid")
 ids=[x["resource_id"] for x in data["resources"]];ck(len(ids)==len(set(ids)),"unique actual per-case resources")
 for obj in data["resources"]:
  attempts+=1;initialized+=int(obj["initialized"]);closed+=int(obj["cleanup_observed"]);ck(obj["cleanup_observed"] is True and obj["pid"]==r["child_pid"],"actual observed resource cleanup")
  if obj["kind"] in ("broker_thread","heartbeat_thread"):ck(obj["alive_after_join"] is False,"observed worker thread ended")
  if obj["kind"]=="worker":workers+=1;never+=int(not obj["poll_ids"])
 for call in data["worker_lifecycles"]:entered+=int(call["entered"]);normal+=int(call["returned_normally"])
ck((attempts,initialized,closed,entered,normal,workers,never)==(738,735,738,3,3,6,3),"independent observed resource counts")
ps=r["progress_summary"];ck(ps==load(O/"progress-summary.json") and ps["all_records_valid"] is True and ps["validation_errors"]==[] and len(ps["records"])==3,"complete separate sampler evidence")
ck(analysis["result"]==pin(O/"result.json") and len(analysis["nodes"])==3,"existing complete ROOT analysis binds exact diagnostic")
ticks=record_count=join_ns=0;window_counts=[];profile_counts=[]
for record in ps["records"]:
 fixed(record["pin"]);data=load(record["pin"]["path"]);ck(data==record["data"] and record["error"] is None,"complete original progress raw/result equality")
 node=data["exact_nodeid"];case=case_map[node];entry=next(x for x in analysis["nodes"] if x["nodeid"]==node);ck(entry["raw_progress"]==record["pin"],"preserved ROOT analysis exact raw origin")
 ck(data["complete"] is True and data["observation_errors"]==[] and data["counters"]["dropped"]==0 and data["counters"]["bound_reached"] is False and data["counters"]["records"]==len(data["samples"])<=1024 and record["pin"]["bytes"]<=8388608,"actual bounded complete samples")
 ticks+=data["counters"]["ticks"];record_count+=len(data["samples"]);event,thread=data["sampler_resources"]["event"],data["sampler_resources"]["thread"]
 ck(event["constructor_attempted"] is True and event["initialized"] is True and event["stop_requested"] is True and event["exception"] is None and thread["constructor_attempted"] is True and thread["initialized"] is True and thread["start_attempted"] is True and thread["started"] is True and thread["target_entered"] is True and thread["target_finally_reached"] is True and thread["join_attempted"] is True and thread["joined"] is True and thread["alive_after_join"] is False and thread["exception"] is None,"independent real sampler Event/thread lifecycle")
 ck(type(thread["ident"]) is int and type(thread["native_id"]) is int and type(event["id"]) is int and type(thread["id"]) is int and 0<=thread["join_elapsed_ns"]<=2000000000,"actual sampler identity and bounded join")
 join_ns+=thread["join_elapsed_ns"];hooks=data["inherited_hooks"];ck(hooks["main_before_setup"]==hooks["main_after_teardown"]==dict.fromkeys(("sys_profile","sys_trace","threading_profile","threading_trace")) and all(hooks["sys_hooks_match_original_thread_hooks"].values()) and hooks["sampler_start"]["sys_profile"] is None and hooks["sampler_start"]["sys_trace"] is None and hooks["sampler_end"]["sys_profile"] is None and hooks["sampler_end"]["sys_trace"] is None and data["final_hook_comparison"]=={"main_before_equals_after":True,"hooks_modified_by_plugin":False},"actual inherited/restored hooks without plugin mutation")
 ck(data["main_thread"]["ident"]==case["order"][1]["thread"] and data["main_thread"]["native_id"]==case["order"][1]["native_thread"] and thread["ident"]!=data["main_thread"]["ident"],"real main/sampler identities linked to exact original case")
 last_ord=0;last_offset=-1;by_ordinal={}
 for sample in data["samples"]:
  ck(type(sample["ordinal"]) is int and sample["ordinal"]>last_ord and type(sample["host_offset_ns"]) is int and sample["host_offset_ns"]>=last_offset and len(sample["main_stack"])<=12 and len(sample["writer_stack"])<=12 and all(type(x) is bool for x in sample["barrier_flags"].values()),"full bounded raw sample coordinates/stacks/flags")
  last_ord=sample["ordinal"];last_offset=sample["host_offset_ns"];by_ordinal[last_ord]=sample
 ck(entry["samples_total"]==len(data["samples"]) and entry["ticks"]==data["counters"]["ticks"] and sum(entry["case_phase_sample_counts"].values())==len(data["samples"]),"all preserved samples remain in analysis denominator")
 selected=entry["strict_actual_writer_wait_samples"];ck(len(selected)==entry["strict_actual_writer_wait_sample_count"],"existing retained strict-window count")
 for sample in selected:
  ck(by_ordinal[sample["ordinal"]]==sample and sample["writer_ident"]==case["order"][0]["thread"] and any(f["qualname"]=="Event.wait" for f in sample["writer_stack"]) and any(f["filename"]==str(R/"tests/test_local_public_writer_binding_race.py") and f["qualname"]=="_r223_run.<locals>.observe_entry" for f in sample["writer_stack"]),"strict retained sample actual identity/original wait frames")
  states=[x for x in sample["primitive_state"] if x.get("order_last8")];state=next((x for x in states if x.get("frame")=="_r223_run"),states[0] if states else {})
  ck(state.get("writer_exception","unavailable") is None and state.get("order_last8",[])[-1]["sequence"]==3 and state["order_last8"][-1]["kind"]=="ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK" and any(k.endswith(".release") and v is False for k,v in sample["barrier_flags"].items()),"all original strict predicates retained; unavailable never inferred")
 window_counts.append(len(selected));profile_counts.append(entry["samples_with_frozen_profile_in_top12"])
ck((ticks,record_count,window_counts,profile_counts)==(582,571,[39,39,38],[26,25,25]) and ticks==ps["ticks"] and join_ns==ps["sampler_join_ns"],"complete bounded evidence totals; no CPU/causal fraction claim")
pr=r["prerequisite"];fixed(pr["pin"]);ck(load(pr["pin"]["path"])==pr["data"],"raw original prerequisite")
v=pr["data"];ck(v["accepted_prerequisite"] is True and v["exception"] is None and v["pid"]==r["child_pid"] and v["same_sys_modules_object_after"] is True and v["pre_import_hooks_empty"] is True and v["profile_trace_before"]==v["profile_trace_after"]==[None]*4 and v["pre_observer_resource_measurement"] is None,"original import-only prerequisite provenance")
ck(r["source_after"]==load(O/"source-after.json") and r["source_after"]["all_unchanged"] is True and r["source_after"]["sources"]==[ident(x) for x in idx["sources"]] and r["source_after"]["retained_DB_count"]==24 and r["source_after"]["absent_sidecar_count"]==72,"actual post-source/database boundaries")
ck(load(O/"file-index.json")==r["file_index"] and load(O/"temp-index.json")==r["temp_index"],"complete raw indexes")
for row in r["file_index"]+r["temp_index"]:
 if row["kind"]=="regular" and row["sha256"] is not None:fixed(row)
new_databases=[]
for row in r["capture_databases"]:
 fixed(row["pin"]);ck(row["bytes_read_after_process_cleanup"] is True,"new DB hashed after actual process closure")
 sides=[]
 for suffix in ("-wal","-shm","-journal"):
  q=Path(row["pin"]["path"]+suffix);ck(not q.exists() and not q.is_symlink(),"new capture sidecar absent");sides.append({"path":str(q),"exists":False,"symlink":False})
 new_databases.append({"pin":row["pin"],"sidecars":sides})
ck(len(new_databases)==6,"six actual new retained databases")
controls=inv["controls_before"];ck(len(controls)==5,"full actual five control originals")
for row in controls:
 b=base64.b64decode(row["base64"],validate=True);ck(pin(row["path"],b)==ident(row),"complete original control bytes")
 if row["path"]==str(D/"command-ledger.json"):
  expected=json.loads(b);expected["commands"]["capture"].update(state="SPENT",used=1,remaining=0,reservation_id=inv["reservation_id"]);ck(Path(row["path"]).read_bytes()==enc(expected),"exact sole author transition")
 else:fixed(row)
root=load(D/"root-command-ledger.json");ck(root["commands"]["capture"]["state"]=="RESERVED_BY_ROOT" and root["commands"]["capture"]["used"]==1 and root["commands"]["capture"]["remaining"]==0,"ROOT slot permanently consumed once")
B=R/"artifacts/research/process/20261004-ced-development";state_path=B/"t12-sol-handoff-20261007/active-t12-state.json";phase_path=B/"t12-sol-handoff-20261007/phase-summary.md"
for q,n,h in ((state_path,132791,"2ddc860e0724f22edbef9fe0f0e85ed63de18636556924c2bb61e9d4f6bd9d70"),(phase_path,86743,"8ad415b06ccb20b6c446b0a44ea5b4a40de5521fa532d81aa5891ecf66137fd8")):fixed({"path":str(q),"bytes":n,"sha256":h})
stage=D/"before/root-diagnostic-settlement";ck(not stage.exists(),"exclusive complete settlement before");paths=[D/name for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json")]+[state_path,phase_path];before={}
for q in paths:
 b=q.read_bytes();s=stage/q.name;put(s,b);before[str(q)]={"raw":b,"original":pin(q,b),"archive":pin(s)}
save(stage/"index.json",{"records":[{"original":x["original"],"archive":x["archive"],"base64":base64.b64encode(x["raw"]).decode()} for x in before.values()]})
findings={"schema_version":"bigsmall.r239.root-diagnostic-findings.v1","status":"DIAGNOSTIC_COMPLETE_ORIGINAL_WRITER_TIMEOUT_NOT_LEGAL_RED","checks":checks.copy(),"check_scope":"Integrity and exact full raw observations through complete settlement before archive; later control/state/report writes have separate actual total.","all_integrity_checks":all(x["pass"] for x in checks),"input_records_as_of_before":list({tuple(x.values()):x for x in records}.values()),"complete_control_STATE_PHASE_before":pin(stage/"index.json"),"actual":pin(O/"actual-tool-return.json"),"result":pin(O/"result.json"),"fresh_source_index":r["source_index_pin"],"analysis":pin(D/"root-progress-analysis.json"),"case_facts":case_facts,"sampler_observations":{"ticks":ticks,"saved_samples":record_count,"strict_wait_samples":window_counts,"profile_in_top12_samples":profile_counts,"threads_constructed_started_joined":3,"own_events_constructed_stopped":3},"frozen_observed_resources":{"attempts":attempts,"initialized_flags":initialized,"cleanup_observed":closed,"entered_polls":entered,"normal_polls":normal,"workers":workers,"never_polled_workers":never},"resource_boundary":"Two separate observed denominators; no exhaustive unknown partial/native/OS coverage claim.","observed_stack_context":"Within strict sampled writer waits main showed original source-inventory reads and nested codec validation, sometimes inside frozen resource profile callbacks. Changing sampled stacks and later COMPLETE are observations; exact causal cost, CPU allocation and all lock behavior remain unproved.","new_retained_databases":new_databases,"display_boundary":"Initial combined scalar/progress overview was capped; complete raw actual preserved. Original stdout and all-sample analysis summary were separately displayed completely. All571 raw samples and retained116 strict samples read and checked; no full aggregate-display claim.","legal_RED":False,"GREEN":False,"T2_complete":False,"T12_complete":False,"native":False,"formal":False,"next":"Actual Astra R242 after accepted R243 metadata disposition; no new source/wait/TTL/observer repair or retry released."}
save(D/"root-diagnostic-findings.json",findings)
root["commands"]["capture"].update(state="SPENT_ACCEPTED_DIAGNOSTIC_ONLY",actual=pin(O/"actual-tool-return.json"),result=pin(O/"result.json"),root_findings=pin(D/"root-diagnostic-findings.json"),legal_RED=False)
sg=json.loads(before[str(D/"source-gate.json")]["raw"]);sg.update(status="DIAGNOSTIC_COMPLETE_STOP_ASTRA_R242",execution_released=False,source_preparation_authorized=False,root_findings=pin(D/"root-diagnostic-findings.json"),historical_control_resolution=pin(stage/"index.json"))
g=json.loads(before[str(D/"script-gate.json")]["raw"]);g["commands"]["capture"].update(state="SPENT_ACCEPTED_DIAGNOSTIC_ONLY",diagnostic_complete=True,result=pin(O/"result.json"),root_findings=pin(D/"root-diagnostic-findings.json"));g["execution_released"]=False;g["historical_control_resolution"]=pin(stage/"index.json")
a=json.loads(before[str(D/"root-activation.json")]["raw"]);a.update(status="DIAGNOSTIC_SPENT_STOP_ASTRA_R242",execution_released=False,root_findings=pin(D/"root-diagnostic-findings.json"),historical_control_resolution=pin(stage/"index.json"))
for name,v in (("root-command-ledger.json",root),("source-gate.json",sg),("script-gate.json",g),("root-activation.json",a)):
 q=D/name;ck(q.read_bytes()==before[str(q)]["raw"],"immediate role/gate settlement CAS");b=enc(v);ck(q.write_bytes(b)==len(b) and q.read_bytes()==b,"exact diagnostic slot settlement")
state=json.loads(before[str(state_path)]["raw"]);old_state=copy.deepcopy(state);ck("R239" not in state["planning"],"new factual R239 entry only")
state["planning"]["R239"]={"status":"BOUNDED_DIAGNOSTIC_COMPLETE_ORIGINAL_WRITER_TIMEOUT","plan":pin(D/"plan.json"),"root_findings":pin(D/"root-diagnostic-findings.json"),"analysis":pin(D/"root-progress-analysis.json"),"source_edits":0,"diagnostic_runs":1,"slots_remaining":0,"saved_samples":571,"strict_writer_wait_samples":window_counts,"observed_profile_context_samples":profile_counts,"causal_cost_unproved":True,"legal_RED":False,"T2_complete":False,"next":"Actual Astra R242 after accepted R243 metadata disposition"}
other=copy.deepcopy(state);other["planning"].pop("R239");ck(other==old_state,"all other state fields unchanged")
phase=before[str(phase_path)]["raw"];append=("\n\n## R239 有界旁观诊断（2026-10-15）\n\nR240 已接受历史归档结构处置；R241 只修 ROOT native 文本重建中已固定的一枚末LF表示差异，原5fc602失败与全部冻结源/补丁保持。R239 原唯一诊断真实完成：child1/wrapper0，三个原节点均FAIL且仍为写线程10秒release超时；三个真实bootstrap/binding与双COMPLETE不替代合法竞争RED。\n\n采样582tick、保存571条且无丢弃，三个新sampler线程及三个自身Event独立记录并完成退出；原738资源尝试/735初始化标记/738清理仅为原观察分母。严格writer等待窗口分别39/39/38条样本，其中26/25/25条top12包含原profile回调；可见source inventory读取与嵌套codec处理。以上是非原子栈观察，不是CPU百分比、精确因果成本或完整死锁结论。新6DB在进程关闭后哈希并保留，旧24DB/72缺省sidecar与27源码/211保护项/321历史保持。\n\n原计划、原始stdout/JUnit/cases/resources/progress及全部actual会话保持，诊断额度耗尽且不重试。R243以零执行槽放弃规划器缺省字段失败聚合，原ff3b64保持；下一步实际Astra R242依据已保存ROOT分析限定修复。event3修复、GREEN9、父GREEN7、fresh12、Git0继续冻结，T2/T12/native/formal未通过。\n").encode()
for q,b in ((state_path,enc(state)),(phase_path,phase+append)):
 ck(q.read_bytes()==before[str(q)]["raw"],"immediate factual STATE/PHASE CAS");ck(q.write_bytes(b)==len(b) and q.read_bytes()==b,"exact factual STATE/PHASE append")
step={"round":"R239","status":"ACCEPTED_DIAGNOSTIC_ONLY_NEXT_ASTRA_R242","check_count_before_step_write":len(checks),"check_scope":"All integrity, before archives, role/gate settlement and STATE/PHASE writes before this step report.","all_checks":all(x["pass"] for x in checks),"root_findings":pin(D/"root-diagnostic-findings.json"),"analysis":pin(D/"root-progress-analysis.json"),"actual":pin(O/"actual-tool-return.json"),"result":pin(O/"result.json"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json"),"STATE_after":pin(state_path),"PHASE_after":pin(phase_path),"new_DBs":6,"diagnostic_runs":1,"T2_complete":False,"T12_complete":False,"native":False,"formal":False}
save(D/"step-report.json",step);put(D/"step-report.md",("# R239 步骤报告\n\n唯一旁观诊断真实完成并完整保留证据；原三个竞争测试仍因写线程机械释放等待超时而失败，未构成合法RED。已完整核对571保存样本，严格等待窗口39/39/38条；可见源码读取、嵌套codec及原profile栈，未作因果CPU或死锁结论。\n\n原观察资源与三个新sampler线程/自身Event分开记录，均按实际证据清理；六新数据库保留，源码/历史和旧数据库字节保持。原始失败不改，诊断额度耗尽。下一步实际Astra R242，T2/T12/native/formal未完成。\n").encode())
print(json.dumps({"status":step["status"],"total_checks_with_report_writes":len(checks),"all_pass":all(x["pass"] for x in checks),"findings":pin(D/"root-diagnostic-findings.json"),"step":pin(D/"step-report.json"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json"),"STATE":pin(state_path),"PHASE":pin(phase_path),"new_DBs":6},ensure_ascii=False))
