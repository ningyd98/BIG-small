from pathlib import Path
import base64,copy,difflib,hashlib,json,shlex
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round239-p6-t2-writer-release-barrier-progress-capture-20261015"
I=D/"implementation";checks=[];records=[]
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
for name,n,h in (("plan.json",37961,"cab00e935387d94adfc79c4827df1a187af4045954253a46cddda7ba903e02cb"),("plan.md",3473,"102ab5e0c122046a69bbe8b3823e5a445f04d4cecbf4c46220a03a2ac34b3e7a"),("input-observation.json",74434,"3cf0cf5b7b603f705fe6a913d1c070580a908fdf368b6b7113fdc3014abb0569"),("implementation/source-preparation-report.json",153070,"dad3236aa73ce4d9500bcae761b4d77ac2d2a1d9995c63bea366986e19e23af9"),("implementation/limited.diff",62701,"c9a068cab8756241ba3ff0e60740c2d9899e3bece2809332afc14aad9254851c")):fixed({"path":str(D/name),"bytes":n,"sha256":h})
p=load(D/"plan.json");report=load(I/"source-preparation-report.json");gate=load(D/"script-gate.json");source_gate=load(D/"source-gate.json")
ck(p["actual_model"]=="gpt-6-astra" and report["plan"]==pin(D/"plan.json") and report["product_test_old_script_edits"]==[] and report["new_execution_count"]==0,"genuine plan and source-only scope")
ck(report["status"]=="SOURCE_READY_PENDING_ROOT_FULL_GATE" and len(report["scripts"])==2 and [x["path"] for x in report["scripts"]]==p["scope"]["author_sources"],"exact two new sources")
for row in source_gate["input_records"]:fixed(row)
ck(gate["commands"]["capture"]["input_records"]==source_gate["input_records"] and len(source_gate["input_records"])==408,"same initial finite408 inputs")
baseline=load(report["accepted_baseline"]["path"]);fixed(report["accepted_baseline"])
ck(report["current_sources"]==[ident(x) for x in baseline["sources"]] and report["protected"]==baseline["protected"] and len(report["current_sources"])==27 and len(report["protected"])==211,"complete current27/protected211 preparation claims")
for row in report["scripts"]:
 fixed(row);b=base64.b64decode(row["base64"],validate=True)
 ck(pin(row["path"],b)==ident(row) and Path(row["path"]).read_bytes()==b and len(b.splitlines())==row["lines"],"full new source bytes/base64/linecount")
ck([(x["bytes"],x["sha256"],x["lines"]) for x in report["scripts"]]==[(17092,"7b3080db3f38b311b32ff91e03c45896bec579f9dc8dfa4956a5fd9f4285e36c",335),(47445,"9bcd169e9e45c05a71dd813b67ea122452ccb663ab71e2c795ef17771dfebc40",761)],"same fully ROOT-read source generations")
def native(v):
 fixed(v);x=load(v["path"]);ck(x["actual_tool_return"]=={} and x["numeric_exit"] is None and x["independent_stdout"] is None and x["independent_stderr"] is None,"raw native unknown numeric/streams retained");return x["tool_arguments"]
patches=[native(v) for v in report["raw_native_receipts"]];ck(len(patches)==4,"four complete native records")
def reconstruct(add,update,path):
 a=add.splitlines();ck(a[:2]==["*** Begin Patch","*** Add File: "+path] and a[-1]=="*** End Patch" and all(x.startswith("+") for x in a[2:-1]),"exact AddFile sole path")
 text="".join(x[1:]+"\n" for x in a[2:-1])
 u=update.splitlines();ck(u[:2]==["*** Begin Patch","*** Update File: "+path] and u[-1]=="*** End Patch","exact UpdateFile sole path")
 hunks=[];current=[]
 for line in u[2:-1]:
  if line.startswith("@@"):
   if current:hunks.append(current)
   current=[]
  else:current.append(line)
 if current:hunks.append(current)
 for hunk in hunks:
  ck(all(x and x[0] in " +-" for x in hunk),"literal native hunk syntax")
  before="".join(x[1:]+"\n" for x in hunk if x[0] in " -");after="".join(x[1:]+"\n" for x in hunk if x[0] in " +")
  ck(before and text.count(before)==1,"unique original native hunk");text=text.replace(before,after,1)
 ck(text.encode()==Path(path).read_bytes(),"complete native generations reconstruct exact frozen source")
for i in range(2):reconstruct(patches[i*2],patches[i*2+1],report["scripts"][i]["path"])
old=next(x for x in p["inputs"] if x["path"].endswith("/round237-p6-t2-original-verification-budget-intersection-20261015/implementation/run-command.py"));fixed(old)
observer,runner=[Path(x["path"]) for x in report["scripts"]]
diff="".join(difflib.unified_diff([],observer.read_text().splitlines(keepends=True),fromfile="/dev/null",tofile=str(observer)))
diff+="".join(difflib.unified_diff(Path(old["path"]).read_text().splitlines(keepends=True),runner.read_text().splitlines(keepends=True),fromfile=old["path"],tofile=str(runner)))
ck(diff.encode()==(I/"limited.diff").read_bytes(),"full exact limited diff from immutable old runner")
prep=load(I/"actual-source-preparation-tool-return.json");fixed(pin(I/"actual-source-preparation-tool-return.json"))
ck(prep["actual_tool_return"]["chunk_id"]=="a1029c" and prep["actual_tool_return"]["exit_code"]==0 and prep["product_execution"] is False,"actual metadata-only source preparation")
prep_summary=json.loads(prep["actual_tool_return"]["output"]);ck(prep_summary["source_preparation_report"]==pin(I/"source-preparation-report.json") and prep_summary["new_execution_count"]==0,"actual preparation binds exact full report")
ck(len(report["roles"])==2,"full two role originals")
for row in report["roles"]:
 fixed(row);b=base64.b64decode(row["base64"],validate=True);ck(pin(row["path"],b)==ident(row),"full original role bytes")
for row in baseline["sources"]:
 fixed(row);raw=base64.b64decode(row["base64"],validate=True)
 ck(raw==Path(row["path"]).read_bytes() and Path(row["path"]).stat().st_mode==row["mode"],"full current source/base64/mode")
 q=Path(report["accepted_baseline"]["path"]).parent/"sources"/Path(row["path"]).relative_to(R);ck(not q.is_symlink() and q.read_bytes()==raw,"complete current physical source")
 old_row=row["physical_original"];fixed(old_row["archive"]);ck(old_row["original"]["path"]==row["path"] and all(old_row["original"][k]==old_row["archive"][k] for k in ("bytes","sha256")),"explicit historical original generation")
resolved=baseline["resolved_history"];ck(len(resolved["entries"])==321 and resolved["unresolved"]==[],"complete321 historical map")
for row in resolved["documents"]:fixed(row)
mapped=[]
for entry in resolved["entries"]:
 v=entry["resolution"];ck(v["kind"] in ("EXACT_PHYSICAL_BEFORE","CURRENT_EXACT_BYTES") and all(entry["original"][k]==v["pin"][k] for k in ("bytes","sha256")),"exact old generation mapping");fixed(v["pin"]);mapped.append(ident(v["pin"]))
ck(mapped==[ident(x) for x in baseline["history"]],"same accepted history321 order/content identities")
oldobs=load(next(x["path"] for x in resolved["documents"] if x["path"].endswith("/round237-p6-t2-original-verification-budget-intersection-20261015/input-observation.json")))
dbs=oldobs["retained_databases"]+p["input_generations"]["new_retained_databases"];ck(len(dbs)==24,"24 old DB records")
absences=[]
for row in dbs:
 fixed(row["pin"]);ck(len(row["sidecars"])==3,"three sidecars per old DB")
 for side in row["sidecars"]:
  q=Path(side["path"]);ck(side["exists"] is False and not q.exists() and not q.is_symlink(),"old DB sidecar absent");absences.append(side)
ck(len(absences)==72 and absences[:54]==baseline["absent_sidecars"],"exact72 old sidecar generations")
controls={str(D/name):(D/name).read_bytes() for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json")}
root=json.loads(controls[str(D/"root-command-ledger.json")]);author=json.loads(controls[str(D/"command-ledger.json")])
for ledger in (root,author):
 slot=ledger["commands"]["capture"];ck((slot["total"],slot["used"],slot["remaining"],slot["state"])==(1,0,1,"HELD"),"original unique slot unused")
ck(not (I/"capture").exists() and not Path("/tmp/bigsmall-p6-r239-capture").exists(),"fresh capture/basetemp absent")
outer_stdout=I/"capture-outer-stdout.txt";outer_stderr=I/"capture-outer-stderr.txt"
ck(not outer_stdout.exists() and not outer_stderr.exists(),"exclusive independent outer streams")
stage=D/"before/root-capture-reservation";ck(not stage.exists(),"exclusive control before generation")
for path,b in controls.items():put(stage/Path(path).name,b)
save(stage/"index.json",{"records":[{"original":pin(path,b),"archive":pin(stage/Path(path).name),"base64":base64.b64encode(b).decode()} for path,b in controls.items()]})
records.append(pin(stage/"index.json"))
fixed_inputs=list({tuple(ident(x).values()):ident(x) for x in records if x["path"] not in controls}.values())
review={"schema_version":"bigsmall.r239.root-full-source-review.v1","status":"APPROVED_DIAGNOSTIC_SOURCES_ONLY","source_lines_fully_read":{"observer":335,"runner":761},"checks":checks.copy(),"all_pass":all(x["pass"] for x in checks),"input_records_as_of_before":fixed_inputs,"source_preparation_report":pin(I/"source-preparation-report.json"),"before_controls":pin(stage/"index.json"),"review":{"mechanism":"Only pinned real frame/primitive/Event native bool observation; no hooks/product/barrier edits.","resources":"Actual independent Thread/Event partial and full lifecycle retained; finally own stop/join<=2s. Inherited hooks and real source/resource receipts checked independently.","limits":"One integrated600 noncleanup invocation, cleanup9 process group plus6 sampler reserve, finite stacks/ticks/records/8MiB; raw before classify.","acceptance":"Diagnostic completeness only; non-atomic stack location is not a proved cause. No legalRED/GREEN/T2/native/formal acceptance."},"full_display_boundary":"Original plan aggregate display capped only small scope segment, independently fully reread scope/observer. Runner two halves completely displayed; small preparation schema tail capped then completely reread. No full aggregate display claim.","product_execution":False,"fresh_T2_review_slots_used":0,"T2_complete":False}
save(D/"root-full-source-review.json",review);fixed_inputs.append(pin(D/"root-full-source-review.json"))
c=p["command"];argv=["env","-i"]+[k+"="+v for k,v in c["finite_env"].items()]+["/usr/bin/timeout","--signal=TERM","--kill-after=5s","630s"]+c["launcher_argv"]
literal="set -C\nexec "+shlex.join(argv)+" > "+shlex.quote(str(outer_stdout))+" 2> "+shlex.quote(str(outer_stderr))
ck(shlex.split(literal.split("\n",1)[1].split(" > ",1)[0])[1:]==argv,"literal exact argv roundtrip")
transport={"argv":argv,"cwd":c["cwd"],"finite_env":c["finite_env"],"outer_stdout":str(outer_stdout),"outer_stderr":str(outer_stderr),"outer_timeout_seconds":630,"outer_kill_after_seconds":5,"literal":literal,"tool_arguments":{"cmd":literal,"workdir":c["cwd"],"shell":"/bin/bash","login":False,"yield_time_ms":1000,"max_output_tokens":1500},"independent_tool_streams":None}
save(D/"root-capture-launch.json",transport)
reservation_id="R239-capture-once-1"
root["commands"]["capture"].update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=reservation_id)
gate["commands"]["capture"].update(state="APPROVED",full_source_reviewed=True,reservation_id=reservation_id,source=ident(report["scripts"][1]),observer_source=ident(report["scripts"][0]),prerequisite_source=next(ident(x) for x in p["inputs"] if x["path"].endswith("/implementation/r235_startup_prerequisite.py")),source_index_pin=ident(report["accepted_baseline"]),input_records=fixed_inputs,transport=transport)
source_gate.update(status="ONE_CAPTURE_ONLY_RESERVED",source_preparation_authorized=False,execution_released=False,source_review=pin(D/"root-full-source-review.json"),historical_control_resolution=pin(stage/"index.json"))
for name,value in (("root-command-ledger.json",root),("source-gate.json",source_gate),("script-gate.json",gate)):
 path=D/name;ck(path.read_bytes()==controls[str(path)],"immediate control CAS");b=enc(value);ck(path.write_bytes(b)==len(b) and path.read_bytes()==b,"exact capture reservation write")
activation=json.loads(controls[str(D/"root-activation.json")]);activation.update(status="CAPTURE_RESERVED_ONLY",execution_released="capture once only",source_gate=pin(D/"source-gate.json"),script_gate=pin(D/"script-gate.json"),source_review=pin(D/"root-full-source-review.json"),root_ledger=pin(D/"root-command-ledger.json"),historical_control_resolution=pin(stage/"index.json"))
path=D/"root-activation.json";ck(path.read_bytes()==controls[str(path)],"immediate activation CAS");b=enc(activation);ck(path.write_bytes(b)==len(b) and path.read_bytes()==b,"exact activation reservation")
save(D/"root-capture-reservation.json",{"round":"R239","reservation_id":reservation_id,"status":"ROOT_RESERVED_CAPTURE_ONCE","launcher":pin(D/"root-capture-launch.json"),"source_review":pin(D/"root-full-source-review.json"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json"),"old_slots_reset":False,"T2_complete":False})
print(json.dumps({"status":"ROOT_RESERVED_CAPTURE_ONCE","checks":len(checks),"fixed_inputs":len(fixed_inputs),"all_pass":all(x["pass"] for x in checks),"source_review":pin(D/"root-full-source-review.json"),"launcher":pin(D/"root-capture-launch.json"),"reservation":pin(D/"root-capture-reservation.json"),"root_ledger":pin(D/"root-command-ledger.json"),"author_ledger":pin(D/"command-ledger.json")},ensure_ascii=False))
