"""ROOT independent integrity review and selected dual diagnostic settlement."""
from pathlib import Path
import base64,copy,hashlib,json,os,stat,xml.etree.ElementTree as ET
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round268-p6-t2-targeted-failure-evidence-20261017"); RUN=D/"implementation/dual_progress"; name="dual_progress"
count=0
def pin(path,raw): return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def checked(p):
 global count
 q=Path(p["path"]); info=q.lstat(); assert stat.S_ISREG(info.st_mode)
 raw=q.read_bytes(); assert len(raw)==p["bytes"] and hashlib.sha256(raw).hexdigest()==p["sha256"]
 count+=1; return raw
def encoded(v): return (json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
def save(path,raw,mode=None):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("xb") as h:
  assert h.write(raw)==len(raw); h.flush(); os.fsync(h.fileno())
 if mode is not None: os.chmod(path,stat.S_IMODE(mode))
 assert path.read_bytes()==raw
 return pin(path,raw)
def before_bytes(row):
 raw=base64.b64decode(row["base64"],validate=True)
 assert checked(row["archive"])==raw and pin(row["original"]["path"],raw)=={k:row["original"][k] for k in ("path","bytes","sha256")}
 return raw
rp={"path":str(RUN/"result.json"),"bytes":391184,"sha256":"7a5b5ab1f006991630b243a3036fbe8efa3cd8575184f572c349fd5d851d13c1"}
tp={"path":str(RUN/"actual-tool-return.json"),"bytes":5252,"sha256":"c3fd8ecc5c9e838cf0746e456caa09c62a8a763a21dfec90b579b2a2bc2d511a"}
r=json.loads(checked(rp)); t=json.loads(checked(tp))
reservation_path=D/"root-reservations/dual_progress.json"
res=json.loads(checked({"path":str(reservation_path),"bytes":83974,"sha256":"9dedfec006f0acd6180527b33ca2f41ce754bbaaaca800041cd96faf7a73b0c0"}))
assert t["round"]==r["round"]=="R268" and t["command_id"]==r["command_id"]==name
assert t["attempt"]==r["attempt"]==1 and t["retry"]==r["retry"]==0
assert t["invocation"]==res["exact_tool_arguments"]
assert t["final"]==t["actual_tool_return"]==t["completion"]==t["polls"][-1]
assert len(t["polls"])==len(t["poll_invocations"])==6 and t["initial"]["session_id"]==93243
for args in t["poll_invocations"]:
 assert args["session_id"]==93243 and args["chars"]=="" and 0<args["yield_time_ms"]<=60000
assert t["final"]["exit_code"]==r["wrapper_exit"]==0
message=json.loads(t["final"]["output"]); assert message["result"]==rp
for key in ("child_exit","wrapper_exit","timed_out","output_limited","diagnostic_complete"): assert message[key]==r[key]
assert r["child_exit"]==1 and r["timed_out"] is False and r["output_limited"] is False
assert r["diagnostic_complete"] is True and r["errors"]==[] and r["T2_complete"] is False
assert r["cleanup"]["leader_reaped"] is True and r["cleanup"]["group_remaining"] is False and r["cleanup"]["cleanup_errors"]==[]
invocation=json.loads(checked(pin(RUN/"invocation.json",(RUN/"invocation.json").read_bytes())))
assert invocation["command"]==res["command"] and invocation["exact_tool_arguments"]==t["invocation"]
for value in r["streams"].values(): checked(value)
junit=ET.fromstring(checked(r["JUnit"]["pin"])); assert len(list(junit.iter("testcase")))==1 and len(list(junit.iter("failure")))==1
before=json.loads(checked(r["before"])); after=json.loads(checked(r["after"]))
assert before["authority_before"]==after and len(before["sources"])==27 and len(after["protected"])==211
for row in before["sources"]:
 raw=checked(row)
 assert raw==checked(row["physical"])==base64.b64decode(row["base64"],validate=True)
 assert Path(row["path"]).lstat().st_mode==row["mode"]
for row in after["protected"]: checked(row)
sg=json.loads(checked(res["source_gate"]))
for item in sg["fixed_inputs"]: checked(item)
for item in sg["sources"].values(): checked(item)
resources=json.loads(checked(r["resources"]))
assert resources["all_records_valid"] is True and resources["validation_errors"]==[] and resources["complete_sidecar_set"] is True
assert len(resources["records"])==1 and resources["actual_node_counts"]=={res["command"]["node"]:1}
objects=[]
for row in resources["records"]:
 data=json.loads(checked(row["pin"])); assert data==row["data"] and data["pid"]==r["pid"] and data["nodeid"]==res["command"]["node"]
 objects.extend(data["resources"])
assert len(objects)==resources["counts"]["allocation_attempts"]==357
assert sum(x["initialized"] is True for x in objects)==resources["counts"]["initialized"]==356
assert all(x["cleanup_observed"] is True for x in objects)
assert r["passive"]["observer_errors"]==[] and r["passive"]["summary"]["hooks_equal"] is True
for row in r["passive"]["records"]: assert json.loads(checked(row["pin"]))==row["data"]
assert r["prerequisite"]["accepted"] is True
checked(r["prerequisite"]["pin"])
cases=json.loads(checked(r["cases"])); index=json.loads(checked(r["index"]))
for row in cases["scenario_files"]:
 raw=checked(row["pin"]); assert raw==base64.b64decode(row["base64"],validate=True)
for row in r["new_retained_databases"]:
 assert checked(row["pin"])==checked(row["archive"])
 for side in row["sidecars"]:
  if side["exists"]: assert checked(side["pin"])==checked(side["archive"])
  else:
   q=Path(side["path"]); assert not q.exists() and not q.is_symlink() and side["pin"] is None
author_path=Path(res["author_role_before"]["path"])
old_author=next(row for row in res["role_before"] if row["original"]["path"]==str(author_path))
author_before=before_bytes(old_author); author_expected=json.loads(author_before)
entry=author_expected["commands"][name]
entry.update(state="RESERVED",used=1,remaining=0,reservation_id=res["reservation_id"])
continuation={"reservation_id":res["reservation_id"],"plan":res["plan"],"source_gate":res["source_gate"],"script_gate":res["script_gate"],"sources":res["sources"],"command":res["command"]}
entry.setdefault("continuation",{})["R268"]=continuation
entry.update(state="SPENT",result_path=str(RUN/"result.json"))
expected_author_raw=encoded(author_expected)
assert expected_author_raw==checked(r["author_spent"])==base64.b64decode(r["known_author_generations"]["spent"]["base64"],validate=True)
assert author_path.lstat().st_mode==old_author["mode"]
root_path=Path(res["root_role_after"]["path"]); root_raw=checked(res["root_role_after"]); mode=root_path.lstat().st_mode
root=json.loads(root_raw); assert root["commands"][name]["state"]=="RESERVED_BY_ROOT"
for row in before["control_before"]:
 raw=before_bytes(row)
 if row["original"]["path"]==str(author_path): assert raw==author_before
 else: assert checked(row["original"])==raw
archive=save(D/"before/settlements/dual_progress/root-command-ledger.json",root_raw,mode)
root_before={"original":pin(root_path,root_raw),"archive":archive,"mode":mode,"base64":base64.b64encode(root_raw).decode("ascii")}
settled=copy.deepcopy(root)
settled["commands"][name].update(state="SPENT_DIAGNOSTIC_CAPTURE",result_path=rp["path"],outcome={"result":rp,"actual_tool_return":tp,"child_exit":1,"wrapper_exit":0,"timed_out":False,"diagnostic_complete":True,"T2_complete":False})
after_raw=encoded(settled); temporary=root_path.with_name(root_path.name+".dual-settled.next")
save(temporary,after_raw,mode)
assert root_path.read_bytes()==root_raw and root_path.lstat().st_mode==mode
os.replace(temporary,root_path)
assert root_path.read_bytes()==after_raw and root_path.lstat().st_mode==mode
report={"round":"R268","command_id":name,"status":"INDEPENDENT_DIAGNOSTIC_INTEGRITY_ACCEPTED_SPENT","checks":count,"result":rp,"actual_tool_return":tp,"root_before":root_before,"root_after":pin(root_path,after_raw),"author_after":r["author_spent"],"child_exit":1,"wrapper_exit":0,"timed_out":False,"diagnostic_complete":True,"exception":"OperationalLeaseError: session is closed, revoked or unregistered","test_helper_tb_lineno":4017,"backend":"sqlite","index":0,"phase":"PENDING","unwind_counter_values_are_non_atomic":True,"resource_objects_observed":357,"initialized_observed":356,"cleanup_observed":357,"new_DB_count":len(r["new_retained_databases"]),"T2_complete":False,"native_accepted":False,"formal_accepted":False}
report_pin=save(D/"root-dual-independent-acceptance.json",encoded(report))
print(json.dumps({"checks":count,"acceptance":report_pin,"root_after":report["root_after"],"author_after":r["author_spent"],"child_exit":1,"diagnostic_integrity_accepted":True,"T2_complete":False},ensure_ascii=False))
