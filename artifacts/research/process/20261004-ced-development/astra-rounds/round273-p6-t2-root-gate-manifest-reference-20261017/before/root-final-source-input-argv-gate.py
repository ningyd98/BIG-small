"""R268 ROOT finite metadata/source/native/argv gate; no imports of reviewed sources."""
from pathlib import Path
import base64, hashlib, json, shlex, stat
ROOT=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
B=ROOT/"artifacts/research/process/20261004-ced-development/astra-rounds"
D=B/"round268-p6-t2-targeted-failure-evidence-20261017"
D272=B/"round272-p6-t2-plugin-timeout-ini-normalization-20261017"
REPORT={"path":str(D/"implementation/change-report.json"),"bytes":15532,"sha256":"6eeec1ab8649f55cfe09955054625af71d5fcba49b0b8bfb54a0b722407f358d"}
checks=0
def identity(p):
 return {k:p[k] for k in ("path","bytes","sha256")}
def check(p):
 global checks
 q=Path(p["path"]); before=q.lstat()
 assert stat.S_ISREG(before.st_mode),str(q)
 raw=q.read_bytes(); after=q.lstat()
 assert (before.st_ino,before.st_mode,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_mode,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 assert len(raw)==p["bytes"] and hashlib.sha256(raw).hexdigest()==p["sha256"],str(q)
 checks+=1
 return raw
def record(q,raw):
 return {"path":str(q),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def absent(q):
 q=Path(q); assert not q.exists() and not q.is_symlink(),str(q)
def full_before(row):
 raw=base64.b64decode(row["base64"],validate=True)
 assert check(row["archive"])==raw and record(row["original"]["path"],raw)==identity(row["original"])
 return raw
r=json.loads(check(REPORT)); fixed={REPORT["path"]:REPORT}
def fixed_check(pin):
 raw=check(pin); fixed[pin["path"]]=identity(pin); return raw
for group in ("sources","candidates","before","authority","component_reports"):
 for pin in r[group].values(): fixed_check(pin)
fixed_check(r["native"]); fixed_check(r["limited_diff"])
p=json.loads(check(r["authority"]["plan"]))
assert p["round"]=="R268"
obs_pin=p["input_observation"]; o=json.loads(fixed_check(obs_pin))
context=json.loads(check(r["authority"]["context_manifest"])); mapped={}
for row in context["changes"]:
 raw=full_before(row["before"]); old=identity(row["before"]["original"])
 assert old["path"]==row["after"]["path"] and old["path"] not in mapped
 check(row["after"]); assert Path(old["path"]).lstat().st_mode==row["mode"]
 mapped[old["path"]]=(old,raw)
assert set(mapped)=={p["history_and_context"]["state_path"],p["history_and_context"]["phase_path"]}
assert len(o["inputs"])==45
for pin in o["inputs"]:
 if pin["path"] in mapped:
  old,raw=mapped[pin["path"]]; assert identity(pin)==old and record(pin["path"],raw)==old
 else: check(pin)
for key in ("whitelist_supplement","ini_normalization_plan"):
 s=json.loads(check(r["authority"][key]))
 for pin in s["inputs"]: fixed_check(pin)
 observation=s["input_observation"] if key=="whitelist_supplement" else s["observation"]
 fixed_check(observation)
p272=json.loads(check(r["authority"]["ini_normalization_plan"]))
old=check(p272["source_scope"]["old_candidate"])
a=p272["source_scope"]["old_line"].encode(); b=p272["source_scope"]["new_line"].encode()
assert old.count(a)==1
expected=old.replace(a,b,1)
assert expected==check(r["candidates"]["plugin_current"])==check(r["sources"]["plugin"])
assert len(expected)==19919 and hashlib.sha256(expected).hexdigest()=="6ab2b3ac36f511337ff740ee99866307f315c7d1ec73d0a6f204c3703f48a711"
assert check(r["sources"]["runner"])==check(r["candidates"]["runner"])
assert r["sources"]["runner"]["sha256"]=="12f00855102f3818d5abf4093041d3701ba83234cd8d1930f4633ee49043d4fd"
for key,pin in r["sources"].items(): assert Path(pin["path"]).lstat().st_mode==r["source_modes"][key]==33204
runner_report=json.loads(check(r["component_reports"]["runner"]))
for pin in runner_report["records"]: fixed_check(pin)
fixed_check(runner_report["limited_diff"])
plugin_report=json.loads(check(r["component_reports"]["plugin"]))
for key in ("plan","release","original_candidate","before","before_manifest","candidate","installed_target","native_receipt","limited_diff"):
 fixed_check(plugin_report[key])
runner_manifest=json.loads(check(r["before"]["runner_manifest"]))
full_before(runner_manifest["template"])
plugin_manifest=json.loads(check(r["before"]["plugin_manifest"]))
assert full_before(plugin_manifest)==old
assert plugin_manifest["mode"]==33204
fixed_check(plugin_manifest["original_native_receipt"])
native=json.loads(check(r["native"]))
runner_native=json.loads(check(next(pin for pin in runner_report["records"] if pin["path"].endswith("/runner-implementation-native-tool-return.json"))))
plugin_native=json.loads(check(plugin_report["native_receipt"]))
assert native["runner"]==runner_native and native["plugin"]==plugin_native
assert native["numeric_exit"] is None and native["independent_stdout"] is None and native["independent_stderr"] is None
def native_add(stage,target):
 assert stage["tool"]=="tools.apply_patch" and stage["actual_tool_return"]=={}
 assert stage["numeric_exit"] is None and stage["independent_stdout"] is None and stage["independent_stderr"] is None
 lines=stage["arguments"].splitlines()
 assert lines[0]=="*** Begin Patch" and lines[1]=="*** Add File: "+target["path"] and lines[-1]=="*** End Patch"
 assert all(line.startswith("+") for line in lines[2:-1])
 raw=("\n".join(line[1:] for line in lines[2:-1])+"\n").encode()
 assert raw==check(target)
assert len(runner_native["stages"])==2
native_add(runner_native["stages"][0],r["candidates"]["runner"])
native_add(runner_native["stages"][1],r["sources"]["runner"])
native_add(plugin_native,r["sources"]["plugin"])
native_add(native["historical_plugin_candidate"],r["candidates"]["plugin_historical"])
parent=B/"round258-p6-t2-parent-green7-continuation-20261017"
result=json.loads(check(next(pin for pin in o["inputs"] if pin["path"]==str(parent/"implementation/green/result.json"))))
si=json.loads(check(result["source_before"]))
assert len(si["sources"])==27 and len(si["protected"])==211
for row in si["sources"]:
 raw=check(row); assert raw==check(row["physical"])==base64.b64decode(row["base64"],validate=True)
 assert Path(row["path"]).lstat().st_mode==row["mode"]
for pin in si["protected"]: check(pin)
h=json.loads(check(next(pin for pin in o["inputs"] if pin["path"]==str(parent/"input-observation.json"))))
assert len(h["missing_registry35"])==35 and len(h["old_absent_sidecars90"])==90
for row in h["missing_registry35"]: absent(row["original"]["path"])
for row in h["old_absent_sidecars90"]: absent(row["path"])
for group,count in (("R242_R248",12),("R251",18)):
 assert len(h["retained_workspace_databases"][group])==count
 for row in h["retained_workspace_databases"][group]:
  check(row["pin"]); assert len(row["sidecars"])==3
  for side in row["sidecars"]:
   assert side["exists"] is False and side["is_symlink"] is False and side["pin"] is None
   absent(side["path"])
assert len(result["new_retained_databases"])==10
present=missing=0
for row in result["new_retained_databases"]:
 assert check(row["pin"])==check(row["archive"]) and len(row["sidecars"])==3
 for side in row["sidecars"]:
  if side["exists"]:
   assert side["is_symlink"] is False and check(side["pin"])==check(side["archive"]); present+=1
  else:
   assert side["is_symlink"] is False and side["pin"] is None; absent(side["path"]); missing+=1
assert (present,missing)==(2,28)
settlement=json.loads(check(next(pin for pin in o["inputs"] if pin["path"]==str(parent/"root-parent-green7-failure-settlement.json"))))
full_before(settlement["root_before"])
argv={}
assert set(p["commands"])=={"wait_memory_failure","dual_progress"}
for name,c in p["commands"].items():
 assert c["authorized"]==1 and c["used"]==0 and c["remaining"]==1 and c["node_count"]==1
 assert [a for a in c["child_argv"] if "::" in a]==[c["node"]]
 assert c["limits"]["child_wall_seconds"]==600 and c["limits"]["cleanup_total_seconds"]==15
 assert c["limits"]["faulthandler_one_shot_seconds"]==540 and c["limits"]["attempts"]==1 and c["limits"]["retries"]==0
 assert c["outputs"]==r["command_outputs"][name]
 for path in c["outputs"].values(): absent(path)
 literal="env -i "+" ".join(shlex.quote(k+"="+v) for k,v in c["launcher_env"].items())+" "+" ".join(shlex.quote(x) for x in c["launcher_argv"])
 argv[name]={"cmd":literal,"workdir":c["cwd"],"yield_time_ms":c["tool_yield_time_ms"],"max_output_tokens":c["tool_max_output_tokens"]}
for path in p["runner_contract"]["role_files"].values(): absent(path)
for path in (D/"source-gate.json",D/"script-gate.json",D/"root-reservations",D/"root-final-input-check.json"): absent(path)
out={"round":"R268","status":"ROOT_FINAL_SOURCE_NATIVE_INPUT_ARGV_VERIFIED_NO_RUNTIME","checks":checks,"sources":r["sources"],"report":REPORT,"fixed_inputs":list(fixed.values()),"context_manifest":r["authority"]["context_manifest"],"interface":r["authority"]["role_gate_interface"],"native":r["native"],"plan":r["authority"]["plan"],"observation":obs_pin,"exact_tool_arguments":argv,"T2_complete":False,"runtime_executed":False}
raw=(json.dumps(out,ensure_ascii=False,indent=2)+"\n").encode()
summary=json.dumps({"checks":checks,"input_records":45,"full_sources":27,"protected":211,"old_DB":30,"R258_DB_pairs":10,"R258_sidecars":[present,missing],"native_Add_reconstructions":4,"exact_tool_arguments":argv,"runtime_released":False},ensure_ascii=False)
assert len(summary.encode())<=6000
with (D/"root-final-input-check.json").open("xb") as handle: assert handle.write(raw)==len(raw)
print(summary)
