from pathlib import Path
import base64,copy,hashlib,json,shlex
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round237-p6-t2-original-verification-budget-intersection-20261015"
O=D/"implementation/ruff"; checks=[]; records=[]
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
for p,n,sha in ((O/"result.json",1046144,"521390ea8dddb879486bb208a21a583de4c67d5e31b3bb4f23ef4a7c813703bb"),(O/"actual-tool-return.json",1586,"9c3ddcea66d890330cefe2c3b0142b848e028335f0ed8d64d0806db9d7202172")):
 fixed({"path":str(p),"bytes":n,"sha256":sha})
result=load(O/"result.json");receipt=load(O/"actual-tool-return.json");launch=load(D/"root-ruff-launch.json");reservation=load(D/"root-ruff-reservation.json")
fixed(reservation["launcher"]);fixed(reservation["baseline_acceptance"])
ck(receipt["invocation"]==launch["tool_arguments"] and receipt["initial"]==receipt["actual_tool_return"] and receipt["polls"]==[] and receipt["completion"] is None and receipt["actual_tool_return"]["exit_code"]==0,"exact unique actual Ruff exit0")
ck(receipt["independent_stdout"] is None and receipt["independent_stderr"] is None,"unknown independent tool streams null")
ck((result["round"],result["command"],result["attempt"],result["retry"],result["child_exit"],result["wrapper_exit"])==("R237","ruff",1,0,0,0),"real child and wrapper Ruff0")
ck(result["accepted_command_outcome"] is True and result["timed_out"] is False and result["runner_exception"] is None and result["observation_errors"]==[],"complete successful bounded static result")
ck(result["cleanup"]=={"leader_reaped":True,"group_remaining":False,"cleanup_notes":[]},"real child reaped and process group absent")
ck(result["JUnit"] is None and result["resource_summary"] is None and result["cases"]==[] and result["prerequisite"] is None,"Ruff has no behavioral/prerequisite claims")
fixed(result["source_index_pin"]);index=load(Path(result["source_index_pin"]["path"]))
ck(result["source_index_pin"]==load(D/"root-baseline-acceptance.json")["source_index"],"same accepted current baseline")
for row in result["input_records"]+list(result["streams"].values()):fixed(row)
ck((O/"stdout.txt").read_bytes()==b"All checks passed!\n" and (O/"stderr.txt").read_bytes()==b"","actual independent Ruff streams")
ck(result["input_records"]==load(D/"script-gate.json")["commands"]["ruff"]["input_records"],"exact current-fixed Ruff gate generation")
ck(len(index["sources"])==27 and len(index["protected"])==211 and len(index["history"])==321,"same finite full baseline")
for row in index["sources"]:
 fixed(row);raw=base64.b64decode(row["base64"],validate=True);physical=Path(result["source_index_pin"]["path"]).parent/"sources"/Path(row["path"]).relative_to(R)
 ck(raw==Path(row["path"]).read_bytes()==physical.read_bytes(),"complete unchanged live/base64/physical source")
 ck(Path(row["path"]).stat().st_mode==row["mode"],"same current source mode")
for row in index["protected"]+index["scripts"]+index["history"]:fixed(row)
ck(index["resolved_history"]==load(D/"implementation/resolved-history.json") and not index["resolved_history"]["unresolved"],"frozen full finite history still applicable")
for row in index["resolved_history"]["documents"]:fixed(row)
for row in index["absent_sidecars"]:ck(row["exists"] is False and not Path(row["path"]).exists() and not Path(row["path"]).is_symlink(),"54 old sidecars remain absent")
ck(len(index["absent_sidecars"])==54,"finite54 absent sidecars")
ck(result["source_after"]["all_unchanged"] is True and result["source_after"]["protected_count"]==211 and result["source_after"]["sources"]==[ident(x) for x in index["sources"]],"full actual source-after agrees with independent bytes")
ck(load(O/"source-after.json")==result["source_after"],"raw source-after file exact")
fixed(pin(O/"source-after.json"))
inv=result["invocation"];ck(inv==load(O/"invocation.json"),"complete actual invocation")
fixed(pin(O/"invocation.json"))
plan=load(D/"plan.json");commands={x["id"]:x for x in plan["commands"]}
ck(inv["argv"]==commands["ruff"]["child_argv"] and inv["launcher_argv"]==commands["ruff"]["launcher_argv"] and inv["finite_env"]==commands["ruff"]["finite_env"] and inv["cwd"]==str(R) and inv["timeout_seconds"]==120 and inv["outer_capture"]==launch,"exact limited Ruff source/argv/env/cap")
ck(result["file_index"]==load(O/"file-index.json") and result["temp_index"]==load(O/"temp-index.json")==[],"full original metadata indexes")
for row in result["file_index"]:
 if row["kind"]=="regular" and row["sha256"] is not None:fixed(row)
for path in (O/"file-index.json",O/"temp-index.json",D/"implementation/ruff-outer-stdout.txt",D/"implementation/ruff-outer-stderr.txt"):fixed(pin(path))
ck((D/"implementation/ruff-outer-stderr.txt").read_bytes()==b"" and len((D/"implementation/ruff-outer-stdout.txt").read_bytes())<=6000,"actual outer streams boundary")
summary=load(D/"implementation/ruff-outer-stdout.txt");ck(summary["result_pin"]==pin(O/"result.json") and summary["child_exit"]==summary["wrapper_exit"]==0 and summary["accepted_command_outcome"] is True,"raw outer scalar summary agrees")
controls=inv["controls_before"];ck(len(controls)==5,"all current control originals retained")
originals={}
for row in controls:
 raw=base64.b64decode(row["base64"],validate=True);ck(pin(row["path"],raw)==ident(row),"complete actual control original bytes");originals[row["path"]]=raw
 if row["path"]!=str(D/"command-ledger.json"):fixed(row)
expected_author=json.loads(originals[str(D/"command-ledger.json")])
expected_author["commands"]["ruff"].update(state="SPENT",used=1,remaining=0,reservation_id=inv["reservation_id"])
ck((D/"command-ledger.json").read_bytes()==enc(expected_author),"one exact author Ruff consumption only")
root=load(D/"root-command-ledger.json");author=load(D/"command-ledger.json")
ck(root["commands"]["baseline"]["state"]=="SPENT_ACCEPTED_BASELINE" and root["commands"]["ruff"]["state"]=="RESERVED_BY_ROOT" and root["commands"]["ruff"]["used"]==1 and root["commands"]["ruff"]["remaining"]==0,"prior exact ROOT once accounting")
for role in (root,author):ck({k:role["commands"]["red"][k] for k in ("total","used","remaining","state")}=={"total":1,"used":0,"remaining":1,"state":"HELD"},"unused original RED slot")
stage=D/"before/root-red-reservation";ck(not stage.exists(),"exclusive new control before")
snapshots={}
for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json"):
 p=D/name;raw=p.read_bytes();q=stage/name;put(q,raw);snapshots[str(p)]={"raw":raw,"original":pin(p,raw),"archive":pin(q)}
save(stage/"index.json",{"records":[{"original":v["original"],"archive":v["archive"],"base64":base64.b64encode(v["raw"]).decode()} for v in snapshots.values()]})
guard=[]
for row in records:
 if row["path"] in snapshots:
  v=snapshots[row["path"]];ck(ident(row)==v["original"],"exact own current-before generation");guard.append(v["archive"])
 else:guard.append(ident(row))
guard += [v["archive"] for v in snapshots.values()]+[pin(stage/"index.json")]
guard=list({tuple(x[k] for k in ("path","bytes","sha256")):x for x in guard}.values())
accept={"schema_version":"bigsmall.r237.root-ruff-acceptance.v1","status":"ACCEPTED_LIMITED_SOURCE_RUFF_ONLY","checks":checks.copy(),"all_pass":all(x["pass"] for x in checks),"input_records":guard,"actual_tool":pin(O/"actual-tool-return.json"),"result":pin(O/"result.json"),"child_exit":0,"wrapper_exit":0,"source_index":result["source_index_pin"],"runtime_evidence":None,"T2_complete":False}
save(D/"root-ruff-acceptance.json",accept);guard.append(pin(D/"root-ruff-acceptance.json"))
command=commands["red"];rid="R237-R238-red-once-1"
for path in (D/"implementation/red",Path("/tmp/bigsmall-p6-r237-red"),D/"implementation/red-outer-stdout.txt",D/"implementation/red-outer-stderr.txt"):ck(not path.exists() and not path.is_symlink(),"exclusive exact RED output "+str(path))
ck(command["timeout_seconds"]==600 and command["cleanup_total_seconds"]==15,"original child600 cleanup15")
ck(sum(x=="r235_startup_prerequisite" for x in command["child_argv"])==1 and not any("r234_exception" in x for x in command["child_argv"]),"original prerequisite only; no diagnostic trace")
outer=["env","-i",*[k+"="+v for k,v in command["finite_env"].items()],"/usr/bin/timeout","--signal=TERM","--kill-after=5s","630s",*command["launcher_argv"]]
outer_stdout=D/"implementation/red-outer-stdout.txt";outer_stderr=D/"implementation/red-outer-stderr.txt"
literal="set -C\nexec "+shlex.join(outer)+" > "+shlex.quote(str(outer_stdout))+" 2> "+shlex.quote(str(outer_stderr))
tool_args={"cmd":literal,"workdir":str(R),"shell":"/bin/bash","login":False,"yield_time_ms":1000,"max_output_tokens":1500}
transport={"argv":outer,"cwd":str(R),"finite_env":command["finite_env"],"outer_stdout":str(outer_stdout),"outer_stderr":str(outer_stderr),"outer_timeout_seconds":630,"outer_kill_after_seconds":5,"literal":literal,"tool_arguments":tool_args,"independent_tool_streams":None}
save(D/"root-red-launch.json",transport)
root["commands"]["ruff"].update(state="SPENT_ACCEPTED_RUFF",actual_tool=pin(O/"actual-tool-return.json"),result=pin(O/"result.json"),root_acceptance=pin(D/"root-ruff-acceptance.json"))
root["commands"]["red"].update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=rid,source_index_pin=result["source_index_pin"],transport=transport)
gate=load(D/"script-gate.json")
gate["commands"]["red"]={"state":"APPROVED","full_source_reviewed":True,"reservation_id":rid,"source":pin(D/"implementation/run-command.py"),"input_records":guard,"argv":command["child_argv"],"launcher_argv":command["launcher_argv"],"cwd":str(R),"finite_env":command["finite_env"],"timeout_seconds":600,"cleanup_total_seconds":15,"transport":transport,"source_index_pin":result["source_index_pin"],"resolved_history_pin":pin(D/"implementation/resolved-history.json"),"prerequisite_source":ident(index["scripts"][-1])}
source_gate=load(D/"source-gate.json");source_gate.update(status="RUFF_ACCEPTED_RECOVERY_RED_ONLY",input_records=guard,ruff_acceptance=pin(D/"root-ruff-acceptance.json"))
activation=load(D/"root-activation.json");activation.update(status="RECOVERY_RED_RESERVED_ONLY",ruff_acceptance=pin(D/"root-ruff-acceptance.json"),reservation_id=rid,execution_released="recovery RED3 once only")
for name,value in (("root-command-ledger.json",root),("script-gate.json",gate),("source-gate.json",source_gate),("root-activation.json",activation)):
 path=D/name;ck(path.read_bytes()==snapshots[str(path)]["raw"],"immediate own CAS "+name);raw=enc(value);ck(path.write_bytes(raw)==len(raw) and path.read_bytes()==raw,"exact own transition "+name)
ck((D/"command-ledger.json").read_bytes()==enc(expected_author),"author RED still HELD0/1")
save(D/"root-red-reservation.json",{"reservation_id":rid,"ruff_acceptance":pin(D/"root-ruff-acceptance.json"),"launcher":pin(D/"root-red-launch.json"),"current_controls":[pin(D/name) for name in ("root-command-ledger.json","script-gate.json","source-gate.json","root-activation.json","command-ledger.json")],"legal_RED_requires_actual_ROOT_acceptance":True,"T2_complete":False})
print(json.dumps({"status":"RUFF_ACCEPTED_RECOVERY_RED_RESERVED","checks":len(checks),"all_pass":all(x["pass"] for x in checks),"fixed_inputs":len(guard),"acceptance":pin(D/"root-ruff-acceptance.json"),"reservation":pin(D/"root-red-reservation.json"),"launcher":pin(D/"root-red-launch.json"),"event3_Green9_parentGreen7_review12_Git0":"HELD"},ensure_ascii=False))
