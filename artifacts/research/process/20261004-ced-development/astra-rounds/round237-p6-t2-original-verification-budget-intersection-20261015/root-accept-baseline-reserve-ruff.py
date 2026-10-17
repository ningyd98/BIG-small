from pathlib import Path
import base64,copy,hashlib,json,shlex
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round237-p6-t2-original-verification-budget-intersection-20261015"
O=D/"implementation/baseline"; checks=[]; records=[]
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
for p,n,sha in ((O/"result.json",1848967,"58cf32ae9866209ba4feb89a948b408ae639decd50cd7a6084930a323ccaa9d6"),(O/"source-index.json",3117352,"62fe31c677ddf88760cf450b44f09d2e30281d818a15b3450f5f68afc5effea8"),(O/"actual-tool-return.json",1607,"62aba9035ec690eff5f4d48aa89f1d39be86d737af88dcbf5653fc7f56e5dcea")):
 fixed({"path":str(p),"bytes":n,"sha256":sha})
result=load(O/"result.json");index=load(O/"source-index.json");receipt=load(O/"actual-tool-return.json")
launch=load(D/"root-baseline-launch.json");reservation=load(D/"root-baseline-reservation.json");review=load(D/"root-full-source-review.json")
fixed(reservation["source_review"]);fixed(reservation["launcher"])
ck(receipt["invocation"]==launch["tool_arguments"],"exact actual reserved transport")
ck(receipt["initial"]==receipt["actual_tool_return"] and receipt["actual_tool_return"]["exit_code"]==0 and receipt["polls"]==[] and receipt["completion"] is None,"real one baseline exit0 with no session/poll")
ck(receipt["independent_stdout"] is None and receipt["independent_stderr"] is None,"unavailable independent tool streams remain null")
ck((result["round"],result["command"],result["exit_code"],result["attempt"],result["retry"])==("R237","baseline",0,1,0),"actual baseline identity/result")
ck(result["test_execution"] is False and result["product_commands"]==0 and result["runtime_evidence"] is None and result["actual_resources"] is None,"metadata baseline only")
ck(len(result["checks"])==7670 and all(v["passed"] is True for v in result["checks"]),"all actual 7670 baseline checks true")
ck(result["candidate"]==pin(O/"source-index.json"),"actual candidate index identity")
ck(result["input_records"]==review["input_records"]==index["input_records"],"exact ROOT fixed input generation")
for row in result["input_records"]+result["outputs"]:fixed(row)
ck(len(result["outputs"])==31,"31 complete actual baseline outputs")
ck(len(index["sources"])==27 and len(index["protected"])==211 and len(index["scripts"])==3 and len(index["history"])==321,"complete baseline finite sets")
for row in index["sources"]:
 fixed(row);raw=base64.b64decode(row["base64"],validate=True);physical=O/"sources"/Path(row["path"]).relative_to(R)
 ck(raw==Path(row["path"]).read_bytes()==physical.read_bytes(),"full live/base64/physical source "+row["path"])
 ck(Path(row["path"]).stat().st_mode==row["mode"],"same source mode")
 fixed(pin(physical))
for row in index["protected"]+index["scripts"]+index["history"]:fixed(row)
for row in index["scripts"]:ck(base64.b64decode(row["base64"],validate=True)==Path(row["path"]).read_bytes(),"complete author/prerequisite source")
ck(index["resolved_history"]==load(D/"implementation/resolved-history.json") and index["resolved_history"]["unresolved"]==[],"full frozen resolved history unchanged")
for row in index["resolved_history"]["documents"]:fixed(row)
ck(len(index["absent_sidecars"])==54,"54 original absent sidecars")
for row in index["absent_sidecars"]:ck(row["exists"] is False and not Path(row["path"]).exists() and not Path(row["path"]).is_symlink(),"unchanged absent sidecar "+row["path"])
ck(index["scope_contract"]==load(D/"implementation/scope-contract.json"),"exact independently reviewed scope contract")
ck((O/"limited.diff").read_bytes()==(D/"implementation/limited.diff").read_bytes(),"exact complete reviewed product delta")
inv=result["invocation"];ck(inv==load(O/"invocation.json"),"full independent invocation bytes-equivalent value")
plan=load(D/"plan.json");commands={x["id"]:x for x in plan["commands"]}
ck(inv["argv"]==inv["launcher_argv"]==commands["baseline"]["launcher_argv"] and inv["cwd"]==str(R) and inv["finite_env"]==commands["baseline"]["finite_env"] and inv["outer_capture"]==launch,"exact actual argv/cwd/environment/transport")
controls=inv["controls_before"];ck(len(controls)==5,"full five actual control originals")
originals={}
for row in controls:
 b=base64.b64decode(row["base64"],validate=True);ck(pin(row["path"],b)==ident(row),"complete actual before control bytes")
 originals[row["path"]]=b
 if row["path"]!=str(D/"command-ledger.json"):fixed(row)
author_before=json.loads(originals[str(D/"command-ledger.json")]);expected_author=copy.deepcopy(author_before)
expected_author["commands"]["baseline"].update(state="SPENT",used=1,remaining=0,reservation_id=inv["reservation_id"])
ck((D/"command-ledger.json").read_bytes()==enc(expected_author),"sole exact author consumption and no other changes")
root=load(D/"root-command-ledger.json");author=load(D/"command-ledger.json")
ck(root["commands"]["baseline"]["state"]=="RESERVED_BY_ROOT" and root["commands"]["baseline"]["used"]==1 and root["commands"]["baseline"]["remaining"]==0,"ROOT reservation spent once")
for name in ("ruff","red"):
 for role in (root,author):ck({k:role["commands"][name][k] for k in ("total","used","remaining","state")}=={"total":1,"used":0,"remaining":1,"state":"HELD"},"unspent next original slot "+name)
for name in ("baseline-outer-stdout.txt","baseline-outer-stderr.txt"):fixed(pin(D/"implementation"/name))
ck((D/"implementation/baseline-outer-stderr.txt").read_bytes()==b"" and len((D/"implementation/baseline-outer-stdout.txt").read_bytes())<=6000,"actual baseline stream boundary")
summary=load(D/"implementation/baseline-outer-stdout.txt")
ck(summary["candidate"]==result["candidate"] and summary["result"]==pin(O/"result.json") and summary["exit_code"]==0,"raw actual outer summary agrees with stored files")
stage=D/"before/root-ruff-reservation";ck(not stage.exists(),"exclusive next complete control before")
snapshots={}
for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json"):
 p=D/name;b=p.read_bytes();q=stage/name;put(q,b);snapshots[str(p)]={"raw":b,"original":pin(p,b),"archive":pin(q)}
save(stage/"index.json",{"records":[{"original":v["original"],"archive":v["archive"],"base64":base64.b64encode(v["raw"]).decode()} for v in snapshots.values()]})
guard=[]
for row in records:
 if row["path"] in snapshots:
  v=snapshots[row["path"]];ck(ident(row)==v["original"],"exact current-before metadata resolution");guard.append(v["archive"])
 else:guard.append(ident(row))
guard += [v["archive"] for v in snapshots.values()]+[pin(stage/"index.json")]
guard=list({tuple(v[k] for k in ("path","bytes","sha256")):v for v in guard}.values())
accept={"schema_version":"bigsmall.r237.root-baseline-acceptance.v1","status":"ACCEPTED_COMPLETE_CURRENT_BASELINE_ONLY","checks":checks.copy(),"all_pass":all(x["pass"] for x in checks),"input_records":guard,"actual_tool":pin(O/"actual-tool-return.json"),"actual_exit":0,"result":pin(O/"result.json"),"source_index":result["candidate"],"source_count":27,"protected_count":211,"history_entries":321,"runtime_evidence":None,"product_commands":0,"T2_complete":False}
save(D/"root-baseline-acceptance.json",accept);guard.append(pin(D/"root-baseline-acceptance.json"))
command=commands["ruff"];rid="R237-R238-ruff-once-1"
outer_stdout=D/"implementation/ruff-outer-stdout.txt";outer_stderr=D/"implementation/ruff-outer-stderr.txt"
for p in (D/"implementation/ruff",outer_stdout,outer_stderr):ck(not p.exists() and not p.is_symlink(),"exclusive Ruff output "+str(p))
outer=["env","-i",*[k+"="+v for k,v in command["finite_env"].items()],"/usr/bin/timeout","--signal=TERM","--kill-after=5s","150s",*command["launcher_argv"]]
literal="set -C\nexec "+shlex.join(outer)+" > "+shlex.quote(str(outer_stdout))+" 2> "+shlex.quote(str(outer_stderr))
tool_args={"cmd":literal,"workdir":str(R),"shell":"/bin/bash","login":False,"yield_time_ms":1000,"max_output_tokens":1500}
transport={"argv":outer,"cwd":str(R),"finite_env":command["finite_env"],"outer_stdout":str(outer_stdout),"outer_stderr":str(outer_stderr),"outer_timeout_seconds":150,"outer_kill_after_seconds":5,"literal":literal,"tool_arguments":tool_args,"independent_tool_streams":None}
save(D/"root-ruff-launch.json",transport)
root["commands"]["baseline"].update(state="SPENT_ACCEPTED_BASELINE",actual_tool=pin(O/"actual-tool-return.json"),result=pin(O/"result.json"),root_acceptance=pin(D/"root-baseline-acceptance.json"))
root["commands"]["ruff"].update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=rid,source_index_pin=result["candidate"],transport=transport)
gate=load(D/"script-gate.json")
gate["commands"]["ruff"]={"state":"APPROVED","full_source_reviewed":True,"reservation_id":rid,"source":pin(D/"implementation/run-command.py"),"input_records":guard,"argv":command["child_argv"],"launcher_argv":command["launcher_argv"],"cwd":str(R),"finite_env":command["finite_env"],"timeout_seconds":120,"transport":transport,"source_index_pin":result["candidate"],"resolved_history_pin":pin(D/"implementation/resolved-history.json"),"prerequisite_source":ident(index["scripts"][-1])}
ck(gate["commands"]["ruff"]["prerequisite_source"]["path"].endswith("/r235_startup_prerequisite.py"),"exact already reviewed unchanged prerequisite")
source_gate=load(D/"source-gate.json");source_gate.update(status="BASELINE_ACCEPTED_RUFF_ONLY",input_records=guard,baseline_acceptance=pin(D/"root-baseline-acceptance.json"),source_index_pin=result["candidate"])
activation=load(D/"root-activation.json");activation.update(status="RUFF_RESERVED_ONLY",baseline_acceptance=pin(D/"root-baseline-acceptance.json"),reservation_id=rid,execution_released="Ruff once only")
for name,value in (("root-command-ledger.json",root),("script-gate.json",gate),("source-gate.json",source_gate),("root-activation.json",activation)):
 p=D/name;ck(p.read_bytes()==snapshots[str(p)]["raw"],"immediate own CAS "+name);b=enc(value);ck(p.write_bytes(b)==len(b) and p.read_bytes()==b,"exact own transition "+name)
ck((D/"command-ledger.json").read_bytes()==enc(expected_author),"author remains spent baseline and HELD Ruff/RED")
save(D/"root-ruff-reservation.json",{"reservation_id":rid,"baseline_acceptance":pin(D/"root-baseline-acceptance.json"),"launcher":pin(D/"root-ruff-launch.json"),"current_controls":[pin(D/name) for name in ("root-command-ledger.json","script-gate.json","source-gate.json","root-activation.json","command-ledger.json")],"T2_complete":False})
print(json.dumps({"status":"BASELINE_ACCEPTED_RUFF_RESERVED","checks":len(checks),"all_pass":all(x["pass"] for x in checks),"fixed_inputs":len(guard),"acceptance":pin(D/"root-baseline-acceptance.json"),"reservation":pin(D/"root-ruff-reservation.json"),"launcher":pin(D/"root-ruff-launch.json"),"RED":"HELD0/1"},ensure_ascii=False))
