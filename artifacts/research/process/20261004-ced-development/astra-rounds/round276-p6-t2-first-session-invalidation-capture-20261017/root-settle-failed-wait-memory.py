"""ROOT finite metadata integrity review; settle the actual failed wait once, never rerun."""
from pathlib import Path
import base64,copy,hashlib,json,os,stat,xml.etree.ElementTree as ET
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round276-p6-t2-first-session-invalidation-capture-20261017")
RUN=D/"implementation/wait_memory"
name="wait_memory"
checks=[]
def check(label,ok):
 checks.append({"check":label,"passed":bool(ok)})
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes()
 check("physical "+str(p),stat.S_ISREG(p.lstat().st_mode) and pin(p,b)=={k:q[k] for k in ("path","bytes","sha256")})
 return b
def encoded(v):return (json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
def save(path,b,mode=33204):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(stat.S_IMODE(mode));assert p.read_bytes()==b and p.lstat().st_mode==mode
 return pin(p,b)
def before_bytes(q):
 b=base64.b64decode(q["base64"],validate=True)
 check("full before "+q["original"]["path"],checked(q["archive"])==b and pin(q["original"]["path"],b)=={k:q["original"][k] for k in ("path","bytes","sha256")})
 return b
rp={"path":str(RUN/"result.json"),"bytes":308836,"sha256":"a78917e83f86fe85f3ca3206e4544ede7d5d78a000f3fb602a7269b409245a7b"}
tp={"path":str(RUN/"actual-tool-return.json"),"bytes":4705,"sha256":"629203d2735b1f81a774d38bcc6f95b3ef745bd59e26049c1458759834631d7f"}
respin={"path":str(D/"root-reservations/wait_memory.json"),"bytes":50212,"sha256":"438e6f4ca2dcbc0abd5b62892c8b831e1f2f66aef9826cde4fcc617139c94965"}
r,t,res=(json.loads(checked(q)) for q in (rp,tp,respin))
check("actual once child failure separate capture integrity",r["round"]==t["round"]=="R276" and r["command_id"]==t["command_id"]==name and r["attempt"]==t["attempt"]==1 and r["retry"]==t["retry"]==0 and r["child_exit"]==r["wrapper_exit"]==1 and r["capture_integrity_complete"] is True and r["behavior_accepted"] is False and r["errors"]==[] and r["legal_RED"] is r["GREEN"] is r["T2_complete"] is False)
check("no timeout interruption or output cap",not r["timed_out"] and not r["interrupted"] and not r["output_limited"] and r["elapsed_seconds"]<615)
check("actual invocation and same session final",t["invocation"]==res["exact_tool_arguments"] and t["initial"]["session_id"]==11904 and len(t["polls"])==len(t["poll_invocations"])==3 and t["actual_tool_return"]==t["final"]==t["completion"]==t["polls"][-1] and t["final"]["exit_code"]==1)
check("all exact same session bounded polls",all(q["session_id"]==11904 and q["chars"]=="" and 0<q["yield_time_ms"]<=60000 for q in t["poll_invocations"]))
check("no fabricated independent streams",t["independent_stdout"] is t["independent_stderr"] is None)
message=json.loads(t["final"]["output"])
check("actual final result pin",message["result"]==rp and all(message[k]==r[k] for k in ("child_exit","wrapper_exit","timed_out","output_limited","capture_integrity_complete","behavior_accepted")))
check("owned group fully cleaned",r["cleanup"]["leader_reaped"] is True and r["cleanup"]["group_remaining"] is False and r["cleanup"]["cleanup_errors"]==[])
inv=json.loads(checked(pin(RUN/"invocation.json")))
check("actual child invocation exact",inv["command"]==res["command"] and inv["argv"]==res["command"]["child_argv"] and inv["actual_environment"]==res["command"]["child_env"] and inv["exact_tool_arguments"]==t["invocation"] and inv["shell"] is False and inv["start_new_session"] is True)
for q in r["streams"].values():checked(q)
check("stderr empty no native timeout markers",r["streams"]["stderr"]["bytes"]==0 and r["faulthandler_raw_markers"]["timeout_text_marker"] is False and r["faulthandler_raw_markers"]["thread_text_marker"] is False)
junit=ET.fromstring(checked(r["JUnit"]["pin"]))
cases_xml=list(junit.iter("testcase"));failures=list(junit.iter("failure"))
check("one actual selected JUnit failed assertion",len(cases_xml)==len(failures)==1 and len(list(junit.iter("error")))==len(list(junit.iter("skipped")))==0 and cases_xml[0].attrib["classname"].replace(".","/")+".py::"+cases_xml[0].attrib["name"]==res["command"]["node"])
check("actual session denial regex mismatch retained","Regex pattern did not match" in failures[0].attrib["message"] and "session is closed, revoked or unregistered" in failures[0].attrib["message"] and "tests/test_operational_runtime_closure.py:4339" in failures[0].text and "tests/test_operational_runtime_closure.py:4341" in failures[0].text)
before=json.loads(checked(r["before"]));after=json.loads(checked(r["after"]))
check("full source authority before equals after",before["authority_before"]==after and len(before["sources"])==27 and len(after["protected"])==211)
for row in before["sources"]:
 b=checked(row)
 check("full source archive base64/mode",b==checked(row["physical"])==base64.b64decode(row["base64"],validate=True) and Path(row["path"]).lstat().st_mode==row["mode"])
for q in after["protected"]:checked(q)
sg=json.loads(checked(res["source_gate"]));checked(res["script_gate"]);checked(res["context_manifest"])
for q in sg["fixed_inputs"]+list(sg["sources"].values()):checked(q)
resources=json.loads(checked(r["resources"]))
check("actual completed selected sidecar",resources["all_records_valid"] is True and resources["complete_sidecar_set"] is True and resources["validation_errors"]==[] and len(resources["records"])==1 and resources["actual_node_counts"]=={res["command"]["node"]:1})
objects=[]
for row in resources["records"]:
 data=json.loads(checked(row["pin"]))
 check("raw resource identity matches",data==row["data"] and data["pid"]==r["pid"] and data["nodeid"]==res["command"]["node"] and data["entered_behavior"] is True and data["assertions_completed"] is False)
 objects+=data["resources"]
 check("two actual wait poll lifecycles",len(data["worker_lifecycles"])==2 and all(q["attempted"] is True and q["entered"] is True for q in data["worker_lifecycles"]))
check("actual allocation denominator and cleanup",len(objects)==resources["counts"]["allocation_attempts"]==537 and sum(q["initialized"] is True for q in objects)==resources["counts"]["initialized"]==535 and all(q["cleanup_observed"] is True and q["pid"]==r["pid"] for q in objects) and resources["counts"]["cleanup_observed"]==537)
check("actual workers include unpolled observations",resources["counts"]["constructed_worker_attempts"]==4 and resources["counts"]["never_polled_workers"]==2)
check("wait has no new trace observer",r["passive"] is None and r["diagnostic_complete"] is False)
check("actual prerequisite accepted",r["prerequisite"]["accepted"] is True);checked(r["prerequisite"]["pin"])
cases=json.loads(checked(r["cases"]));index=json.loads(checked(r["index"]))
for q in cases["scenario_files"]:check("actual scenario full bytes",checked(q["pin"])==base64.b64decode(q["base64"],validate=True))
for q in r["new_retained_databases"]:
 check("new raw DB original/archive",checked(q["pin"])==checked(q["archive"]))
 for side in q["sidecars"]:
  if side["exists"]:check("new present sidecar raw pair",checked(side["pin"])==checked(side["archive"]))
  else:
   path=Path(side["path"]);check("actual missing new sidecar",side["pin"] is None and not path.exists() and not path.is_symlink())
author_path=Path(res["author_role_before"]["path"])
author_before_record=next(q for q in res["role_before"] if q["original"]["path"]==str(author_path))
author_before=before_bytes(author_before_record);author_expected=json.loads(author_before)
entry=author_expected["commands"][name]
entry.update(state="RESERVED",used=1,remaining=0,reservation_id=res["reservation_id"])
continuation={k:res[k] for k in ("reservation_id","plan","source_gate","script_gate","sources","command")}
entry.setdefault("continuation",{})["R276"]=continuation
entry.update(state="SPENT",result_path=str(RUN/"result.json"))
expected_author_raw=encoded(author_expected)
check("only selected author exact spent generation",expected_author_raw==checked(r["author_spent"])==base64.b64decode(r["known_author_generations"]["spent"]["base64"],validate=True) and author_path.lstat().st_mode==author_before_record["mode"])
root_path=Path(res["root_role_after"]["path"]);root_raw=checked(res["root_role_after"]);mode=root_path.lstat().st_mode
root=json.loads(root_raw)
check("ROOT only selected reserved",root["commands"][name]["state"]=="RESERVED_BY_ROOT" and root["commands"][name]["used"]==1 and root["commands"][name]["remaining"]==0)
for row in before["control_before"]:
 b=before_bytes(row)
 if row["original"]["path"]==str(author_path):check("source snapshot author is exact before",b==author_before)
 else:check("source snapshot stable control unchanged",checked(row["original"])==b)
failed=[q for q in checks if not q["passed"]]
if failed:
 report=save(D/"root-wait-memory-integrity-failed.json",encoded({"round":"R276","checks":checks,"failed":failed,"runtime":0,"ROOT_role_unmodified":True}))
 print(json.dumps({"status":"INDEPENDENT_METADATA_INTEGRITY_FAILED_STOP_ASTRA","failed":len(failed),"report":report},ensure_ascii=False));raise SystemExit(2)
archive=save(D/"before/settlements/wait_memory/root-command-ledger.json",root_raw,mode)
root_before={"original":pin(root_path,root_raw),"archive":archive,"mode":mode,"base64":base64.b64encode(root_raw).decode("ascii")}
settled=copy.deepcopy(root)
settled["commands"][name].update(state="SPENT_UNEXPECTED_FAILURE",result_path=rp["path"],outcome={"result":rp,"actual_tool_return":tp,"child_exit":1,"wrapper_exit":1,"timed_out":False,"capture_integrity_complete":True,"behavior_accepted":False,"T2_complete":False})
after_raw=encoded(settled);temporary=root_path.with_name(root_path.name+".wait-settled.next")
save(temporary,after_raw,mode)
assert root_path.read_bytes()==root_raw and root_path.lstat().st_mode==mode and author_path.read_bytes()==expected_author_raw and author_path.lstat().st_mode==author_before_record["mode"]
os.replace(temporary,root_path)
assert root_path.read_bytes()==after_raw and root_path.lstat().st_mode==mode
report={"round":"R276","command_id":name,"status":"INDEPENDENT_FAILED_WAIT_CAPTURE_ACCEPTED_SPENT","checks":checks,"checks_passed":len(checks),"result":rp,"actual_tool_return":tp,"root_before":root_before,"root_after":pin(root_path,after_raw),"author_after":r["author_spent"],"child_exit":1,"wrapper_exit":1,"timed_out":False,"capture_integrity_complete":True,"behavior_accepted":False,"failure":"Post-expiry reserve_capture at4339/4341 rejected by session guard but message fails regex; cause/fix await R281 Astra","resource_objects_observed":537,"initialized_observed":535,"cleanup_observed":537,"new_DB_count":len(r["new_retained_databases"]),"other_commands_released":False,"T2_complete":False,"native_accepted":False,"formal_accepted":False}
report_pin=save(D/"root-wait-memory-independent-acceptance.json",encoded(report))
output=json.dumps({"status":report["status"],"checks":len(checks),"acceptance":report_pin,"root_after":report["root_after"],"author_after":r["author_spent"],"behavior_accepted":False,"T2_complete":False},ensure_ascii=False)
assert len((output+"\n").encode())<=6000
print(output)
