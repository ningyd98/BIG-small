"""R287 ROOT one finite existing-evidence assessment; no delivered-source execution."""
from pathlib import Path
import base64,copy,hashlib,json,os,stat,xml.etree.ElementTree as ET
from collections import Counter
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round287-p6-t2-runner-completion-marker-contract-20261017")
OLD=D.parent/"round285-p6-t2-new-test-generation-validation-continuation-20261017"
RUN=OLD/"implementation/wait_memory"
checks=[]
def check(label,ok):checks.append({"check":label,"passed":bool(ok)})
def identity(q):return {k:q[k] for k in ("path","bytes","sha256")}
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes();check("identity "+str(p),stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==identity(q));return b
def load(q):return json.loads(checked(q))
def named(inputs,path):return next(q for q in inputs if q["path"]==str(path))
def encoded(q):return (json.dumps(q,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
def save(path,b,mode=33204):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(stat.S_IMODE(mode));assert p.read_bytes()==b and p.lstat().st_mode==mode
 return pin(p,b)
def full(q):
 b=base64.b64decode(q["base64"],validate=True)
 check("complete physical generation "+q["original"]["path"],checked(q["archive"])==b and pin(q["original"]["path"],b)==identity(q["original"]));return b
def absence(path):
 p=Path(path);check("absence "+str(p),not p.exists() and not p.is_symlink())
def emit(value):
 s=json.dumps(value,ensure_ascii=False);assert len((s+"\n").encode())<=6000;print(s)
P=load({"path":str(D/"plan.json"),"bytes":24997,"sha256":"c0370315fa34ee474e71d4ec8473b4c4a35c745c95138982cb978925ee675e1d"})
O=load(P["observation"]);M=load(P["before_manifest"])
check("actual Astra final29 and260 scope proofs",P["planner"]=="actual gpt-6-astra" and P["inputs"]==O["inputs"] and len(P["inputs"])==29 and O["check_count"]==len(O["checks"])==260 and all(q["passed"] for q in O["checks"]) and O["resource_cleanup_independently_validated_by_planner"] is False)
for q in P["inputs"]:checked(q)
for q in M["records"]:
 b=full(q);check("original before still exact bytes/mode",checked(q["original"])==b and Path(q["original"]["path"]).lstat().st_mode==Path(q["archive"]["path"]).lstat().st_mode==q["mode"]==33204)
rp=lambda path:named(P["inputs"],path)
t=load(rp(RUN/"actual-tool-return.json"));inv=load(rp(RUN/"invocation.json"))
res=load(rp(OLD/"root-reservations/wait_memory.json"))
check("original once/same session preserved failure",t["round"]=="R285" and t["command_id"]=="wait_memory" and t["attempt"]==1 and t["retry"]==0 and t["invocation"]==res["exact_tool_arguments"] and t["initial"]["session_id"]==6082 and len(t["poll_invocations"])==len(t["polls"])==3 and t["actual_tool_return"]==t["completion"]==t["final"]==t["polls"][-1] and t["final"]["exit_code"]==1 and t["final"]["chunk_id"]=="364b4c")
check("bounded same original session polls",all(q["session_id"]==6082 and q["chars"]=="" and 0<q["yield_time_ms"]<=60000 for q in t["poll_invocations"]))
check("original exact KeyError no independent streams","KeyError: 'assertions_completed'" in t["final"]["output"] and 'line 1108' in t["final"]["output"] and 'line 1348' in t["final"]["output"] and t["independent_stdout"] is t["independent_stderr"] is None)
absence(RUN/"result.json")
check("original child invocation identity",inv["command"]==res["command"] and inv["argv"]==res["command"]["child_argv"] and inv["actual_environment"]==res["command"]["child_env"] and inv["exact_tool_arguments"]==t["invocation"] and inv["shell"] is False and inv["start_new_session"] is True)
xml=ET.fromstring(checked(rp(RUN/"junit.xml")));cases_xml=list(xml.iter("testcase"))
check("genuine exact selected JUnit1PASS",len(cases_xml)==1 and not any(list(xml.iter(tag)) for tag in ("failure","error","skipped")) and cases_xml[0].attrib["classname"].replace(".","/")+".py::"+cases_xml[0].attrib["name"]==res["command"]["node"])
check("actual raw pytest result and empty stderr",b"1 passed, 1 warning in 181.29s" in checked(rp(RUN/"stdout.txt")) and checked(rp(RUN/"stderr.txt"))==b"")
resources=load(rp(RUN/"resource-summary.json"))
check("original summary only one genuine sidecar",len(resources["records"])==1 and resources["actual_node_counts"]=={res["command"]["node"]:1} and resources["all_records_valid"] is True and resources["complete_sidecar_set"] is True and resources["validation_errors"]==[])
row=resources["records"][0];raw=load(row["pin"]);pid=raw["pid"]
check("raw full identity equals embedded data",raw==row["data"] and raw["nodeid"]==res["command"]["node"] and type(pid) is int and pid==4 and raw["entered_contract_guard"] is True and raw["entered_behavior"] is True and raw["command_id"]=="t2_green")
obs=raw["observations"]
markers={"top_level":{"present":"assertions_completed" in raw,"value":raw.get("assertions_completed"),"status":"unobserved"},"nested":{"selector":"observations.assertions_completed","present":"assertions_completed" in obs,"type":type(obs.get("assertions_completed")).__name__,"value":obs.get("assertions_completed")}}
check("distinct marker locations genuine nested boolean",markers["top_level"]["present"] is False and markers["top_level"]["value"] is None and markers["nested"]["present"] is True and type(markers["nested"]["value"]) is bool and markers["nested"]["value"] is True)
check("restoration and body exit observed",obs["observers_restored"] is True and obs["method_restoration"] is True and obs["exit_exception"] is None and raw["cleanup_errors"]==[])
objects=raw["resources"];byid={q["resource_id"]:q for q in objects}
check("actual observed denominator and unique objects",len(objects)==raw["allocation_attempts"]==len(byid) and all(type(q["resource_id"]) is int and q["resource_id"]>0 for q in objects))
partial=[];counts=Counter()
for q in objects:
 check("actual resource base observations",q["pid"]==pid and q["initialization_attempted"] is True and type(q["initialized"]) is bool and "cleanup_observed" in q and q["cleanup_observed"] is True)
 counts["allocation_attempts"]+=1;counts["initialized"]+=int(q["initialized"]);counts["cleanup_observed"]+=int(q["cleanup_observed"] is True);counts["kind:"+q["kind"]]+=1
 if not q["initialized"]:partial.append({"resource_id":q["resource_id"],"kind":q["kind"],"initialization_error":q["initialization_error"],"cleanup_observed":q["cleanup_observed"],"close_attempts":q["close_attempts"]})
 if q["kind"] in ("helper_thread","broker_thread","heartbeat_thread"):
  check("actual thread join observed",q["alive_after_join"] is False and type(q["thread_ident"]) is int and type(q["native_thread_id"]) is int)
 if q["kind"]=="lease_session":check("actual session broker no longer alive",q["broker_alive"] is False)
 if q["kind"]=="job_repository":check("actual job TLS released",q["TLS_connection"] is False)
 if q["kind"] in ("memory_repository","event_repository","sqlite_connection") and q["initialized"]:
  check("actual initialized close returned",any(call["returned"] is True and call["error"] is None for call in q["close_attempts"]))
lifecycles=raw["worker_lifecycles"];intervals=[];pollids=set()
for ordinal,q in enumerate(lifecycles,1):
 worker=byid[q["worker_resource_id"]]
 check("actual ordered poll linkage",q["poll_id"]==ordinal and q["poll_id"] not in pollids and worker["kind"]=="worker" and q["poll_id"] in worker["poll_ids"] and q["attempted"] is True and q["entered"] is True and type(q["thread_id"]) is int and type(q["native_thread_id"]) is int and q["start_sequence"]<q["entry_sequence"]<q["end_sequence"])
 check("actual normal poll return",q["returned_normally"] is True and type(q["return_value"]) is bool and q["exception"] is None)
 pollids.add(q["poll_id"]);intervals.extend(((q["entry_sequence"],1),(q["end_sequence"],-1)))
 counts["attempted_poll_lifecycles"]+=1;counts["entered_poll_lifecycles"]+=int(q["entered"]);counts["normally_returned_poll_lifecycles"]+=int(q["returned_normally"])
for q in objects:
 if q["kind"]!="worker":continue
 counts["constructed_worker_attempts"]+=1;counts["initialized_workers"]+=int(q["initialized"])
 calls=[c for c in lifecycles if c["worker_resource_id"]==q["resource_id"]]
 check("real worker poll inventory",q["poll_ids"]==[c["poll_id"] for c in calls] and q["final_active_job_id"]=="")
 if not calls:
  counts["never_polled_workers"]+=1
  check("never-polled runtime genuinely absent",q["cleanup_basis"]=="never_polled_no_owned_runtime" and q["initial_active_job_id"]=="" and q["session_observed"] is False and q["heartbeat_observed"] is False and q["session_resource_ids"]==q["broker_resource_ids"]==q["heartbeat_resource_ids"]==q["close_attempts"]==[])
 else:
  check("polled worker release basis",q["cleanup_basis"]=="poll_finished_runtime_released" and type(q["session_observed"]) is bool and type(q["heartbeat_observed"]) is bool)
 for sid in q["session_resource_ids"]:check("actual session owner",byid[sid]["kind"]=="lease_session" and byid[sid]["worker_resource_id"]==q["resource_id"] and byid[sid]["cleanup_observed"] is True)
 for key,kind in (("broker_resource_ids","broker_thread"),("heartbeat_resource_ids","heartbeat_thread")):
  for tid in q[key]:check("actual thread worker/session owner",byid[tid]["kind"]==kind and byid[tid]["worker_resource_id"]==q["resource_id"] and byid[tid]["session_resource_id"] in q["session_resource_ids"])
active=peak=0
for _,delta in sorted(intervals):active+=delta;peak=max(peak,active);check("bounded actual active polls",0<=active<=2)
check("wait exact observed two finished polls",len(lifecycles)==2 and active==0 and peak<=2)
check("independent actual counts equal reports",dict(counts)==resources["counts"])
casebook=load(rp(RUN/"cases.json"));domains=[]
check("actual two completed case files",len(casebook["scenario_files"])==2 and casebook["expected_node"]==res["command"]["node"])
for q in casebook["scenario_files"]:
 b=checked(q["pin"]);case=json.loads(b);domains.append(case["domain"])
 check("full case base64 and owner",b==base64.b64decode(q["base64"],validate=True) and q["actual_owner"]=={"nodeid":res["command"]["node"],"pid":pid} and bool(q["witnesses"]) and case["backend"]=="memory")
 for witness in q["witnesses"]:
  resource=witness["resource"];check("real case SQLite witness",witness["pid"]==pid and witness["nodeid"]==res["command"]["node"] and witness["sidecar_pin"]==row["pin"] and byid[resource["resource_id"]]==resource and resource["kind"]=="sqlite_connection" and resource["initialized"] is True and resource["path"]==str(Path(q["pin"]["path"]).parent/"events.db"))
 expected=({"type":"OperationalLeaseError","message":"original lease hard-open segment expired"},{"type":"OperationalLeaseError","message":"session is closed, revoked or unregistered"}) if case["domain"]=="D_lease" else ({"type":"OperationalTimeError","message":"original app deadline expired"},)*2
 check("genuine first and subsequent refusal",case["first_denial"]==expected[0] and case["subsequent_denial"]==expected[1])
check("both actual denial domains",sorted(domains)==["D_app","D_lease"])
before=load(rp(RUN/"before/source-index.json"));after=load(rp(RUN/"source-after.json"))
check("original full authority before equals after",before["authority_before"]==after and len(before["sources"])==len(after["sources"])==27 and len(after["protected"])==211 and len(after["accepted_history_generations"])==68)
for q in before["sources"]:
 b=checked(q);check("complete current27 source bytes/base64/mode",b==checked(q["physical"])==base64.b64decode(q["base64"],validate=True) and Path(q["path"]).lstat().st_mode==q["mode"])
for q in after["protected"]+after["fixed_inputs"]+after["context_after"]:checked(q)
checked(after["source_authority"])
for q in after["missing_registry35"]:
 check("historical loss stays null",q["current_bytes"] is q["current_sha256"] is q["hash_match"] is None);absence(q["original"]["path"])
for q in after["old_absent_sidecars90"]:absence(q["path"])
for name,n in (("R242_R248",12),("R251",18)):
 rows=after["old_retained_groups"][name];check("fixed old DB count",len(rows)==n)
 for q in rows:
  checked(q["pin"])
  for side in q["sidecars"]:check("old sidecar absent state",side["exists"] is side["is_symlink"] is False and side["pin"] is None);absence(side["path"])
def pairs(rows,n):
 check("actual DB pair count",len(rows)==n);present=missing=0
 for q in rows:
  check("raw DB original/archive",checked(q["pin"])==checked(q["archive"]));check("three DB sides",len(q["sidecars"])==3)
  for side in q["sidecars"]:
   check("side no symlink",side["is_symlink"] is False)
   if side["exists"]:check("raw sidecar original/archive",checked(side["pin"])==checked(side["archive"]));present+=1
   else:check("missing sidecar pin null",side["pin"] is None);absence(side["path"]);missing+=1
 return present,missing
check("R258 fixed10/2/28",pairs(after["R258_retained_DB_pairs"],10)==(2,28))
for key,n in (("wait_memory_failure",4),("dual_progress",2),("R276_wait_memory",4)):pairs(after["R268_R276_retained_DB_pairs"][key],n)
index=load(rp(RUN/"persistent-file-database-index.json"))
check("actual four new DB and12 absent sides",pairs(index["new_retained_databases"],4)==(0,12) and index["SQL_executed"] is False and index["old_missing_recovered"] is False)
for q in index["records"]:
 p=Path(q["path"]);s=p.lstat()
 check("actual index same own lstat",s.st_mode==q["mode"] and s.st_size==q["bytes"] and s.st_ino==q["inode"])
 if stat.S_ISREG(s.st_mode):checked(q);check("regular owns hash",q["symlink"] is False)
 elif stat.S_ISLNK(s.st_mode):check("link owns only its target",q["symlink"] is True and q["link_target"]==os.readlink(p) and "sha256" not in q)
 else:check("actual directory no file hash",stat.S_ISDIR(s.st_mode) and q["symlink"] is False and "sha256" not in q)
root_path=Path(res["root_role_after"]["path"]);root_raw=checked(res["root_role_after"])
author_path=Path(res["author_role_before"]["path"]);author_raw=checked(rp(author_path))
check("genuine author spent artifact",author_raw==checked(rp(RUN/"author-spent.json")))
author_before=next(q for q in res["role_before"] if q["original"]["path"]==str(author_path))
oldauthor=full(author_before);expected_author=json.loads(oldauthor)
entry=expected_author["commands"]["wait_memory"]
entry.update(state="RESERVED",used=1,remaining=0,reservation_id=res["reservation_id"])
entry.setdefault("continuation",{})["R285"]={k:res[k] for k in ("reservation_id","plan","source_gate","script_gate","sources","command")}
entry.update(state="SPENT",result_path=str(RUN/"result.json"))
check("only selected author exact SPENT full generation",encoded(expected_author)==author_raw)
for q in before["control_before"]:
 b=full(q)
 if q["original"]["path"]==str(author_path):check("source snapshot author exact before",b==oldauthor)
 else:check("stable run controls unchanged",checked(q["original"])==b)
root=json.loads(root_raw)
check("ROOT selected reserved consumed1/0",root["commands"]["wait_memory"]["state"]=="RESERVED_BY_ROOT" and root["commands"]["wait_memory"]["used"]==1 and root["commands"]["wait_memory"]["remaining"]==0)
for key in ("wait_sqlite","dual_first_invalidation"):
 for value in (root,expected_author):check("other key still HELD0/1",value["commands"][key]["state"]=="HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE" and value["commands"][key]["used"]==0 and value["commands"][key]["remaining"]==1)
# Complete corrected-source proof is bytes-only; the candidate is never imported.
delivery=load({"path":str(D/"implementation/change-report.json"),"bytes":117306,"sha256":"4039ceb8578a47cc9b824a8fc3da97fc4824b9ad2369ea85706f50322bb05e4c"})
sourceindex=load(delivery["source_index"]);proof=load(delivery["scope_proof"]);native=load(delivery["native"])
oldsource=checked(delivery["before"]["original"]);candidate=checked(delivery["candidate"])
corrected=checked(delivery["after"])
check("complete original/candidate/corrected source generation",full(delivery["before"])==oldsource and candidate==corrected==checked(delivery["after_archive"]) and len(corrected)==86520 and len(corrected.splitlines())==1447 and hashlib.sha256(corrected).hexdigest()=="c4865f0bea01accbbb5787b38fd790f4af3abfcf10d220384a43f1e15239b6ad")
check("full source index actual physical/base64/mode",checked(sourceindex["candidate"]["pin"])==base64.b64decode(sourceindex["candidate"]["base64"],validate=True)==candidate and checked(sourceindex["after"]["pin"])==checked(sourceindex["after"]["archive"])==base64.b64decode(sourceindex["after"]["base64"],validate=True)==corrected and Path(delivery["after"]["path"]).lstat().st_mode==sourceindex["after"]["mode"]==delivery["mode"]==33204)
check("all source-only records remain unexecuted",delivery["runtime_executed"] is False and sourceindex["runtime_executed"] is False and proof["runtime_executed"] is False and sourceindex["source_count"]==proof["source_count"]==27 and sourceindex["protected_count"]==proof["protected_count"]==211)
check("same explicit source input identities",sourceindex["input_records"]==proof["input_records"]==P["inputs"] and [identity(q) for q in sourceindex["current_sources"]]==[identity(q) for q in after["sources"]] and [identity(q) for q in sourceindex["protected"]]==[identity(q) for q in after["protected"]])
check("exact two reviewed changed regions",len(proof["regions"])==2 and [q["label"] for q in proof["regions"]]==["completion_helper","final_assessment_and_persistence"])
oldbounds=[];newbounds=[]
for q in proof["regions"]:
 for rawbytes,name,bounds in ((oldsource,"before",oldbounds),(corrected,"after",newbounds)):
  v=q[name];s,e=v["start_byte"],v["end_byte"];b=rawbytes[s:e];bounds.append((s,e))
  check("exact changed bytes/hash/line "+q["label"]+" "+name,0<=s<e<=len(rawbytes) and len(b)==v["bytes"] and hashlib.sha256(b).hexdigest()==v["sha256"] and rawbytes[:s].count(b"\n")+1==v["start_line"])
(s1,e1),(s2,e2)=oldbounds;(n1,m1),(n2,m2)=newbounds
check("whole two-region reconstruction and all outside bytes",s1<e1<=s2<e2 and n1<m1<=n2<m2 and oldsource[:s1]==corrected[:n1] and oldsource[e1:s2]==corrected[m1:n2] and oldsource[e2:]==corrected[m2:] and corrected==oldsource[:s1]+corrected[n1:m1]+oldsource[e1:s2]+corrected[n2:m2]+oldsource[e2:])
for q,b in zip(proof["unchanged_regions"],(oldsource[:s1],oldsource[e1:s2],oldsource[e2:])):
 check("independent whole unchanged region "+q["label"],q["exact_before_after"] is True and len(b)==q["bytes"] and hashlib.sha256(b).hexdigest()==q["sha256"])
check("actual limited diff full bytes preserved",checked(delivery["limited_diff"])==checked(proof["limited_diff"]))
check("exact two actual native Add stages",[q["stage"] for q in native["stages"]]==["before_candidate","implementation"])
for stage in native["stages"]:
 check("honest actual native return "+stage["stage"],stage["tool"]=="tools.apply_patch" and stage["actual_tool_return"]=={} and all(stage[k] is None for k in ("numeric_exit","independent_stdout","independent_stderr","target_before")))
 lines=stage["arguments"].splitlines()
 check("native exact frame",lines[0]=="*** Begin Patch" and lines[-1]=="*** End Patch")
 i=1;targets=[]
 while i<len(lines)-1:
  check("only Add native source",lines[i].startswith("*** Add File: "))
  target=lines[i][14:];i+=1;body=[]
  while i<len(lines)-1 and lines[i].startswith("+"):body.append(lines[i][1:]);i+=1
  rebuilt=("\n".join(body)+"\n").encode();targets.append(target)
  check("exact complete native reconstruction "+target,Path(target).read_bytes()==rebuilt)
 check("native stage exact destination",targets==[delivery["candidate"]["path"] if stage["stage"]=="before_candidate" else delivery["after"]["path"]])
D288=D.parent/"round288-p6-t2-byteproof-assessment-anchor-disposition-20261017"
P288=load({"path":str(D288/"plan.json"),"bytes":12327,"sha256":"8f2ce03944fc6301954fbc4bdb8de2d2fe58d0d8634831571193e2d37312dc91"})
for q in P288["inputs"]:checked(q)
r288=load({"path":str(D288/"implementation/actual-tool-return.json"),"bytes":5599,"sha256":"16fb1b8d344d9198bd892bcf99728dc2514613e651e0b4e7be4504135de6a44f"})
check("R288 exact single authorized metadata receipt",r288["attempt"]==1 and r288["retry"]==0 and r288["invocation"]==P288["execution"]["tool_arguments"] and r288["initial"]==r288["final"]==r288["actual_tool_return"] and r288["final"]["chunk_id"]=="3d2cec" and r288["final"]["exit_code"]==0 and r288["completion"] is None and r288["polls"]==r288["poll_invocations"]==[] and r288["independent_stdout"] is r288["independent_stderr"] is None)
source_text_review=json.loads((D/"root-corrected-source-text-review.json").read_bytes())
for row,(lo,hi) in zip(source_text_review["candidate_reads"],((1,480),(481,960),(961,1447))):
 b=b"".join(corrected.splitlines(keepends=True)[lo-1:hi])
 check("complete ROOT source read unchanged",row["actual"]["exit_code"]==0 and row["actual"]["output"].encode()==b and len(b)<=40000 and hi-lo+1<=600)
corrected_source_acceptance={"status":"FULL_SOURCE_ONLY_NATIVE_SCOPE_ACCEPTED" if all(q["passed"] for q in checks) else "FAILED_STOP_ASTRA","candidate":delivery["candidate"],"after":delivery["after"],"after_archive":delivery["after_archive"],"native":delivery["native"],"scope_proof":delivery["scope_proof"],"limited_diff":delivery["limited_diff"],"source_report":pin(D/"implementation/change-report.json"),"runtime_executed":False,"T2_complete":False}
failed=[q for q in checks if not q["passed"]]
assessment={"round":"R287","status":"FAILED_STOP_ASTRA" if failed else "LIMITED_EXISTING_CASE_RESOURCE_EVIDENCE_ACCEPTED_ORIGINAL_WRAPPER_FAILED","checks":checks,"failed":failed,"checks_passed":len(checks)-len(failed),"actual_runtime":rp(RUN/"actual-tool-return.json"),"tool_exit_observed":1,"JUnit_one_PASS":True,"markers":markers,"reported_counts":resources["counts"],"independent_observed_counts":dict(counts),"partial_initializations":partial,"new_DB_count":4,"direct_child_exit":None,"static_child_exit_inference":{"value":0,"basis":"Frozen short circuit reaches behavior_resources_complete; inference only, no separately persisted process receipt"},"direct_process_group_cleanup":None,"original_result_available":False,"original_capture_integrity_accepted":False,"OS_native_model_network":raw["unobserved"],"new_runtime":0,"T2_complete":False,"native_accepted":False,"formal_accepted":False}
assessment["corrected_source_acceptance"]=corrected_source_acceptance
assessmentpin=save(D/"root-existing-evidence-assessment.json",encoded(assessment))
if failed:emit({"status":"FAILED_STOP_ASTRA","failed":len(failed),"assessment":assessmentpin});raise SystemExit(2)
mode=root_path.lstat().st_mode;author_mode=author_path.lstat().st_mode
archive=save(D/"before/settlement/root-command-ledger.json",root_raw,mode)
root_before={"original":pin(root_path,root_raw),"archive":archive,"mode":mode,"base64":base64.b64encode(root_raw).decode("ascii")}
settled=copy.deepcopy(root)
settled["commands"]["wait_memory"].update(state="SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE",result_path=None,outcome={"original_runtime":rp(RUN/"actual-tool-return.json"),"existing_evidence_assessment":assessmentpin,"tool_exit_observed":1,"JUnit_one_PASS":True,"original_result_absent":True,"direct_child_exit":None,"direct_process_cleanup":None,"T2_complete":False})
after_raw=encoded(settled)
prepared=save(D/"before/settlement/prepared-root-command-ledger.json",after_raw,mode)
assert root_path.read_bytes()==root_raw and root_path.lstat().st_mode==mode and author_path.read_bytes()==author_raw and author_path.lstat().st_mode==author_mode
fd=os.open(root_path,os.O_RDWR|os.O_NOFOLLOW)
with os.fdopen(fd,"r+b") as f:
 assert os.fstat(f.fileno()).st_mode==mode and f.read()==root_raw
 assert author_path.read_bytes()==author_raw and author_path.lstat().st_mode==author_mode
 f.seek(0);f.write(after_raw);f.truncate();f.flush();os.fsync(f.fileno())
assert root_path.read_bytes()==after_raw and root_path.lstat().st_mode==mode and author_path.read_bytes()==author_raw
settlement={"round":"R287","status":"SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE","assessment":assessmentpin,"root_before":root_before,"prepared_after":prepared,"root_after":pin(root_path,after_raw),"author_unchanged":pin(author_path,author_raw),"only_selected_key_changed":True,"used":1,"remaining":0,"normal_original_result_absent":True,"new_runtime":0,"other_keys_released":False,"T2_complete":False}
settlementpin=save(D/"root-failure-settlement.json",encoded(settlement))
emit({"status":settlement["status"],"checks":len(checks),"assessment":assessmentpin,"settlement":settlementpin,"root_after":settlement["root_after"],"author_unchanged":settlement["author_unchanged"],"T2_complete":False})
