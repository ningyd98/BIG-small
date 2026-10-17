from pathlib import Path
from collections import Counter
import base64, copy, difflib, hashlib, json, shlex

R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
A=R/"artifacts/research/process/20261004-ced-development/astra-rounds"
D=A/"round237-p6-t2-original-verification-budget-intersection-20261015"
C=A/"round238-p6-t2-pure-budget-projection-boundary-20261015"
I=D/"implementation"
checks=[]; records=[]
def enc(v): return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
def ident(v): return {k:v[k] for k in ("path","bytes","sha256")}
def key(v): return tuple(v[k] for k in ("path","bytes","sha256"))
def pin(p,raw=None):
 p=Path(p); raw=p.read_bytes() if raw is None else raw
 return {"path":str(p),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def ck(v,label):
 checks.append({"check":label,"pass":bool(v)})
 if not v: raise ValueError(label)
def fixed(v):
 p=Path(v["path"]); ck(not p.is_symlink() and pin(p)==ident(v),"fixed "+str(p)); records.append(ident(v))
def load(p): return json.loads(Path(p).read_bytes())
def put(p,raw):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f: ck(f.write(raw)==len(raw),"fullwrite "+str(p))
 ck(p.read_bytes()==raw,"readback "+str(p))
def save(p,v): put(p,enc(v))
def same_original(original,archive):
 fixed(archive); ck((original["bytes"],original["sha256"])==(archive["bytes"],archive["sha256"]),"complete physical original "+original["path"])
for name,size,sha in (
 ("change-report.json",10692,"6ab339a29be4d45a5d4a4c6ede0c06db93f3cb86d0950866978322b74aff57dd"),
 ("source-preparation-index.json",2229122,"2d03ad7c044742366142cee42080e583f080bfb8316d451d95c888551e089799"),
 ("resolved-history.json",640525,"51510bb777504203a4845f7112861554fed2e98576a8a5e3221c0cc982e2db56"),
 ("before/manifest.json",96743,"1115d0de7d352dfbecae9b74ddc9ce62ef9534efb57c5503944ad21dd626eb99")):
 fixed({"path":str(I/name),"bytes":size,"sha256":sha})
report=load(I/"change-report.json"); index=load(I/"source-preparation-index.json")
plan=load(D/"plan.json"); obs=load(D/"input-observation.json")
fixed({"path":str(D/"plan.json"),"bytes":26101,"sha256":"aedf64900ea6a9e3d67c1a7af45edb7c950dfe1acda3f698fe48641c3e1ff08f"})
fixed({"path":str(C/"plan.json"),"bytes":15484,"sha256":"ccf4fe0a79963cad9b99e6ce6946c6c02536809b5dcc7dd46e8bd546d8491e30"})
for p,size,sha in ((D/"plan.md",3574,"fd59baa018799a1c89f74241a23ca4d5b2fae479c11f3a7793d5243c34816a6d"),(D/"metadata-schema-supplement.md",1346,"4b520714d43fce5f12be50d411f3a61d12bb00b14c42854f47f4dc04b17f3666"),(C/"plan.md",2913,"31340433698fb28f1f2207ca5e838809a2d14ceea25043ceb7ee73142fad2ec0"),(C/"input-check.json",192152,"f241120bf2c97114a5e77ffaa686f07ef4cd4e0d89a51ca86763d4b1a6733912"),(C/"source-continuation-gate.json",6996,"61470432a9dee67a5801c50266910b1d4f2f9c3209fae37035660421426fc407"),(C/"root-activation.json",3420,"cbecaaffed5987d813a37c8837b8b3938afd327fb3c69f3bf0507254f1f1e67e")):
 fixed({"path":str(p),"bytes":size,"sha256":sha})
for item in report["outputs"]+report["native_receipts"]+[report["source_index"],report["history"]["manifest"],index["physical_before_manifest"],index["scope_contract"],index["resolved_history"]]:
 fixed(item)
scope=load(I/"scope-contract.json"); before=load(I/"before/manifest.json")
old=Path(scope["before"]["path"]).read_bytes(); raw=Path(scope["after"]["path"]).read_bytes()
fixed(scope["before"]); fixed(scope["after"])
ck(pin(R/"src/cloud_edge_robot_arm/vision/worker_runtime.py",old)==ident(scope["original_identity"])==ident(report["before"]),"original runtime full identity")
ck(raw==(I/"after/worker_runtime.py").read_bytes(),"candidate complete physical after")
helper=base64.b64decode(scope["helper"],validate=True).decode()
text=raw.decode(); ck(text.count(helper)==1,"one exact complete helper"); text=text.replace(helper,"",1)
names=["_initialize_local","_validate_role_sources","check_active","_check_optional_sources","route"]
ck([x["name"] for x in scope["regions"]]==names,"five exact allowed regions")
regions={}
for row in scope["regions"]:
 b=base64.b64decode(row["before"],validate=True).decode(); a=base64.b64decode(row["after"],validate=True).decode()
 ck(text.count(a)==1 and old.decode().count(b)==1,"unique full literal "+row["name"])
 ck(b.startswith("    def "+row["name"]+"(") and a.startswith("    def "+row["name"]+"("),"actual function region "+row["name"])
 text=text.replace(a,b,1); regions[row["name"]]=(b,a)
for line in scope["added_imports"]:
 ck(text.count(line)==1,"exact necessary import "+line.strip()); text=text.replace(line,"",1)
ck(text.encode()==old,"every byte outside allowed regions/helper/imports unchanged")
for name,oldcall,newcall in (
 ("check_active","self._validate_role_sources(record.definition.verification_limits)","self._validate_role_sources(record.definition.verification_limits, local_definition=self._local_mode)"),
 ("_check_optional_sources","self._validate_role_sources(bootstrap.definition.verification_limits)","self._validate_role_sources(bootstrap.definition.verification_limits, local_definition=self._local_mode)"),
 ("route","self._validate_role_sources(self.bootstrap.definition.verification_limits)","self._validate_role_sources(self.bootstrap.definition.verification_limits, local_definition=self._local_mode)")):
 b,a=regions[name]; ck(b.count(oldcall)==1 and b.replace(oldcall,newcall)==a,"one keyword only "+name)
b,a=regions["_initialize_local"]
for token in ("owner.export_record(owner.task_window)","owner._clock.domain","owner.task_origin_token.event_identity"):
 ck(b.count(token)==a.count(token)==1,"no additional source lookup "+token)
ck(a.index("effective =")<a.index("definition_body =")<a.index("bootstrap_source_commitment(definition_body)"),"effective definition before immutable commitment")
for token in ("self.","owner.","_LOCAL_ORIGINALS","_OWNERS","export_record","get_job","read_current","Path(","open(","_read_lease"):
 ck(token not in helper,"pure helper has no lookup "+token)
for token in ("export_record","get_job","read_current","_check_live(","_check_app_live(","_clock."):
 ck(token not in regions["_validate_role_sources"][1],"later provenance branch no additional live lookup "+token)
tail="        if (\n            configuration_hash(policy)"
b,a=regions["_validate_role_sources"]; ck(b[b.index(tail):]==a[a.index(tail):],"full original policy/source validation tail unchanged")
native=load(I/"actual-product-patch-tool-return.json")
ck(native["actual_tool_return"]=={} and native["numeric_exit"] is None and native["independent_stdout"] is None and native["independent_stderr"] is None,"true product native receipt")
lines=native["patch"].splitlines(); ck(lines[:2]==["*** Begin Patch","*** Update File: "+str(R/"src/cloud_edge_robot_arm/vision/worker_runtime.py")],"single exact product patch target")
chunks=[]; chunk=[]
for line in lines[2:]:
 if line=="*** End Patch": break
 if line.startswith("@@"):
  if chunk: chunks.append(chunk)
  chunk=[]
 else: chunk.append(line)
if chunk: chunks.append(chunk)
built=old.decode(); cursor=0
for chunk in chunks:
 ck(all(x[:1] in (" ","+","-") for x in chunk),"exact product patch syntax")
 previous="\n".join(x[1:] for x in chunk if x[:1] in (" ","-"))+"\n"
 current="\n".join(x[1:] for x in chunk if x[:1] in (" ","+"))+"\n"
 position=built.find(previous,cursor); ck(position>=0,"original product hunk exists")
 built=built[:position]+current+built[position+len(previous):]; cursor=position+len(current)
ck(built.encode()==raw,"complete actual native product patch reconstructs candidate")
for name,field,newname in (("actual-prepare-patch-tool-return.json","patch","prepare-evidence.py"),("actual-runner-patch-tool-return.json","tool_arguments","run-command.py")):
 value=load(I/name); patch=value[field].splitlines()
 ck(value["actual_tool_return"]=={} and value["numeric_exit"] is None,"true author native receipt "+newname)
 ck(patch[:2]==["*** Begin Patch","*** Add File: "+str(I/newname)] and patch[-1]=="*** End Patch" and all(x.startswith("+") for x in patch[2:-1]),"one new author file "+newname)
 ck(("\n".join(x[1:] for x in patch[2:-1])+"\n").encode()==(I/newname).read_bytes(),"full AddFile reconstruction "+newname)
for path,b,a in ((I/"limited.diff",old,raw),):
 value=path.read_text(); header=value.splitlines()[:2]
 ck(len(header)==2 and header[0].startswith("--- ") and header[1].startswith("+++ "),"complete product diff headers")
 ck(value=="".join(difflib.unified_diff(b.decode().splitlines(keepends=True),a.decode().splitlines(keepends=True),fromfile=header[0][4:],tofile=header[1][4:])),"exact complete product diff bytes")
delta=(I/"scripts-limited.diff").read_text(); starts=[x for x in delta.splitlines() if x.startswith("--- ")]; ends=[x for x in delta.splitlines() if x.startswith("+++ ")]
ck(len(starts)==len(ends)==2,"two complete author source deltas")
previous=A/"round235-p6-t2-bootstrap-json-and-startup-prerequisites-20261015/implementation"
expected_delta=""
for n,name in enumerate(("prepare-evidence.py","run-command.py")):
 fixed(pin(previous/name)); expected_delta+="".join(difflib.unified_diff((previous/name).read_text().splitlines(keepends=True),(I/name).read_text().splitlines(keepends=True),fromfile=starts[n][4:],tofile=ends[n][4:]))
ck(delta==expected_delta,"complete two author source delta bytes")
ck(len(index["sources"])==27 and len(index["protected"])==211 and len(index["scripts"])==2,"full current finite source sets")
originals={x["original"]["path"]:x for x in before["source_archives27"]}
original_obs={x["path"]:ident(x) for x in obs["current_sources"]}
for row in index["sources"]:
 fixed(row); b=base64.b64decode(row["base64"],validate=True); ck(b==Path(row["path"]).read_bytes(),"complete candidate source "+row["path"])
 origin=originals[row["path"]]; same_original(origin["original"],origin["archive"])
 ck(ident(origin["original"])==original_obs[row["path"]]==ident(row["original"]["original"]),"applicable original source "+row["path"])
 ck(ident(row["original"]["archive"])==ident(origin["archive"]) and row["original"]["mode"]==origin["mode"],"complete original archive descriptor "+row["path"])
 if row["path"]!=scope["after"]["path"]: ck(b==Path(origin["archive"]["path"]).read_bytes(),"other26 complete source unchanged "+row["path"])
 ck(Path(row["path"]).stat().st_mode==row["mode"]==origin["mode"],"unchanged source mode")
for row in index["protected"]+index["scripts"]:
 fixed(row)
 if "base64" in row: ck(base64.b64decode(row["base64"],validate=True)==Path(row["path"]).read_bytes(),"full author source bytes")
for row in index["roles"]:
 fixed(row); ck(base64.b64decode(row["base64"],validate=True)==Path(row["path"]).read_bytes(),"complete unspent role snapshot")
h=load(I/"resolved-history.json"); ck(len(h["documents"])==7 and len(h["entries"])==321 and h["unresolved"]==[],"finite explicit history")
for row in h["documents"]: fixed(row)
expected=Counter(); actual=Counter()
def origins(document,rows,prefix):
 for n,row in enumerate(rows): expected[(key(row),key(pin(document)),prefix+"/"+str(n))]+=1
origins(D/"input-observation.json",obs["inputs"],"inputs")
for name in ("current_sources","protected","trace_pins"): origins(D/"input-observation.json",obs[name],name)
origins(D/"input-observation.json",[x["pin"] for x in obs["retained_databases"]],"databases")
origins(D/"metadata-schema-supplement.json",load(D/"metadata-schema-supplement.json")["inputs"],"inputs")
origins(C/"input-observation.json",load(C/"input-observation.json")["inputs"],"inputs")
for document in (C/"before/metadata/source-gate.json",I/"before/controls"/D.name/"source-gate.json"):
 origins(document,load(document)["input_records"],"input_records")
archive_choices={}
def choice(original,archive):
 same_original(original,archive); archive_choices.setdefault(key(original),set()).add(key(archive))
choice(before["runtime"],before["physical_runtime"])
for row in before["controls"]:
 fixed(row["original"]); choice(row["original"],row["archive"])
for row in load(C/"before/metadata/index.json")["records"]:
 choice(row["original"],row["archive"]); ck(base64.b64decode(row["base64"],validate=True)==Path(row["archive"]["path"]).read_bytes(),"complete ROOT control original bytes")
physical_count=0
for item in h["entries"]:
 original=item["original"]; resolution=item["resolution"]; target=resolution["pin"]; fixed(target)
 ck((original["bytes"],original["sha256"])==(target["bytes"],target["sha256"]),"historical original exact bytes")
 if resolution["kind"]=="CURRENT_EXACT_BYTES": ck(ident(original)==ident(target),"current resolution same path and identity")
 else:
  physical_count+=1; ck(resolution["kind"]=="EXACT_PHYSICAL_BEFORE" and key(target) in archive_choices.get(key(original),set()),"independently proven physical historical mapping")
 for origin in item["origins"]: actual[(key(original),key(origin["document"]),origin["origin"])]+=1
ck(expected==actual and len({x[0] for x in expected})==321 and physical_count==6,"independent exact complete history identity/origin Counter")
for row in obs["retained_databases"]:
 fixed(row["pin"])
 for side in row["sidecars"]: ck(side["exists"] is False and not Path(side["path"]).exists() and not Path(side["path"]).is_symlink(),"54 retained absent sidecars")
prerequisite={"path":str(previous/"r235_startup_prerequisite.py"),"bytes":5022,"sha256":"e46122f6ce00f9c5d0e13be33301b8861b567cb3f25c33d41447f1ea68880e0d"}
fixed(prerequisite); fixed({"path":str(R/"tests/test_operational_time_v1.py"),"bytes":24211,"sha256":"ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f"})
commands={x["id"]:x for x in plan["commands"]}; root_raw=(D/"root-command-ledger.json").read_bytes(); author_raw=(D/"command-ledger.json").read_bytes()
root=json.loads(root_raw); author=json.loads(author_raw)
for role in (root,author):
 ck(set(role["commands"])==set(commands),"same three original slots")
 for name,item in role["commands"].items():
  ck({k:item[k] for k in ("total","used","remaining","state")}=={"total":1,"used":0,"remaining":1,"state":"HELD"},"unspent original "+name)
  ck(item["launcher_argv"]==commands[name]["launcher_argv"] and item.get("child_argv")==commands[name].get("child_argv"),"original command definitions "+name)
for path in [D/"implementation"/x for x in ("baseline","ruff","red")]+[Path("/tmp/bigsmall-p6-r237-red")]+[D/"implementation"/(x+"-outer-"+stream+".txt") for x in ("baseline","ruff","red") for stream in ("stdout","stderr")]:
 ck(not path.exists() and not path.is_symlink(),"exclusive future output "+str(path))
stage=D/"before/root-baseline-reservation"; ck(not stage.exists(),"new current control archive")
mutable={str(D/name) for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json")}
snapshots={}
for name in ("source-gate.json","script-gate.json","root-activation.json","root-command-ledger.json","command-ledger.json"):
 p=D/name; b=p.read_bytes(); archive=stage/name; put(archive,b); snapshots[str(p)]={"raw":b,"original":pin(p,b),"archive":pin(archive)}
save(stage/"index.json",{"schema_version":"bigsmall.r237.root-reservation-before.v1","records":[{"original":v["original"],"archive":v["archive"],"base64":base64.b64encode(v["raw"]).decode()} for v in snapshots.values()]})
guard_records=[]
for row in records:
 if row["path"] in mutable:
  snapshot=snapshots[row["path"]]; ck(ident(row)==snapshot["original"],"exact authorized current-before transition "+row["path"]); guard_records.append(snapshot["archive"])
 else: guard_records.append(ident(row))
guard_records += [pin(stage/"index.json")]+[v["archive"] for v in snapshots.values()]
guard_records=list({key(x):x for x in guard_records}.values())
review={"schema_version":"bigsmall.r237.root-full-source-review.v1","status":"APPROVED_SOURCE_BASELINE_ONLY","checks":checks.copy(),"all_pass":all(x["pass"] for x in checks),"input_records":guard_records,"candidate":ident(scope["after"]),"full_text_chunks":["5e0e4f","894e3e","6364dd","f4e429","d47da4","247db3","9c00f8","64f4f6"],"independent_history_entries":321,"independent_origin_records":sum(expected.values()),"physical_original_mappings":6,"other26_and_protected211_unchanged":True,"runtime_verified":False,"T2_complete":False}
save(D/"root-full-source-review.json",review)
command=commands["baseline"]; reservation_id="R237-R238-baseline-once-1"
outer_stdout=D/"implementation/baseline-outer-stdout.txt"; outer_stderr=D/"implementation/baseline-outer-stderr.txt"
outer=["env","-i",*[k+"="+v for k,v in command["finite_env"].items()],"/usr/bin/timeout","--signal=TERM","--kill-after=5s","150s",*command["launcher_argv"]]
literal="set -C\nexec "+shlex.join(outer)+" > "+shlex.quote(str(outer_stdout))+" 2> "+shlex.quote(str(outer_stderr))
tool_args={"cmd":literal,"workdir":str(R),"shell":"/bin/bash","login":False,"yield_time_ms":1000,"max_output_tokens":1500}
transport={"argv":outer,"cwd":str(R),"finite_env":command["finite_env"],"outer_stdout":str(outer_stdout),"outer_stderr":str(outer_stderr),"outer_timeout_seconds":150,"outer_kill_after_seconds":5,"literal":literal,"tool_arguments":tool_args,"independent_tool_streams":None}
save(D/"root-baseline-launch.json",transport)
gate=load(D/"script-gate.json"); ck(gate["commands"]=={},"empty pre-run script gate")
gate["commands"]["baseline"]={"state":"APPROVED","full_source_reviewed":True,"reservation_id":reservation_id,"source":ident(report["scripts"][0]),"input_records":guard_records,"argv":command["launcher_argv"],"launcher_argv":command["launcher_argv"],"cwd":str(R),"finite_env":command["finite_env"],"timeout_seconds":120,"transport":transport,"resolved_history_pin":index["resolved_history"],"before_manifest_pin":index["physical_before_manifest"],"scope_contract_pin":index["scope_contract"],"scripts":[ident(x) for x in report["scripts"]],"prerequisite_source":prerequisite}
source_gate=load(D/"source-gate.json"); source_gate.update(status="FULL_SOURCE_REVIEWED_BASELINE_ONLY",input_records=guard_records,source_review=pin(D/"root-full-source-review.json"),candidate=ident(scope["after"]))
root["commands"]["baseline"].update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=reservation_id,source_review=pin(D/"root-full-source-review.json"),transport=transport)
activation=load(D/"root-activation.json"); activation.update(status="BASELINE_RESERVED_ONLY",source_review=pin(D/"root-full-source-review.json"),reservation_id=reservation_id,execution_released="baseline once only")
for name,value in (("source-gate.json",source_gate),("script-gate.json",gate),("root-command-ledger.json",root),("root-activation.json",activation)):
 path=D/name; ck(path.read_bytes()==snapshots[str(path)]["raw"],"immediate own metadata CAS "+name)
 b=enc(value); ck(path.write_bytes(b)==len(b) and path.read_bytes()==b,"exact own metadata transition "+name)
ck((D/"command-ledger.json").read_bytes()==author_raw,"sole author still HELD0/1")
save(D/"root-baseline-reservation.json",{"schema_version":"bigsmall.r237.root-baseline-reservation.v1","reservation_id":reservation_id,"source_review":pin(D/"root-full-source-review.json"),"current_controls":[pin(D/name) for name in ("source-gate.json","script-gate.json","root-command-ledger.json","root-activation.json","command-ledger.json")],"launcher":pin(D/"root-baseline-launch.json"),"author_released":"one exact literal baseline only","ruff_red":"HELD","T2_complete":False})
print(json.dumps({"round":"R237/R238","status":"FULL_SOURCE_REVIEWED_BASELINE_RESERVED","checks":len(checks),"all_pass":all(x["pass"] for x in checks),"fixed_inputs":len(guard_records),"history_entries":321,"history_origins":sum(expected.values()),"source_review":pin(D/"root-full-source-review.json"),"reservation":pin(D/"root-baseline-reservation.json"),"launcher":pin(D/"root-baseline-launch.json"),"next":"Send existing literal baseline once; no helper; Ruff/RED HELD"},ensure_ascii=False))
